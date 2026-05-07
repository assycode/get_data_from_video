"""
批量任务规划器

核心设计变更：
1. LLM 的任务是"接口选型"——根据需求 + 接口文档，决定调用哪些工具、传什么参数。
2. LLM 的输出是一个可直接执行的调用链（tool_calls），而非抽象的计划描述。
3. LLM 同时决定最终需要从结果中提取哪些字段（extract_fields）。
4. 如果 LLM 失败，直接抛异常报错，绝不降级——因为错误的计划会导致抓不到数据。
5. 前端传入的过滤条件（topic / start_date）作为强制兜底，LLM 没提取到就用前端的值。
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from openai import AsyncOpenAI

from config import settings
from agent.executor import execute_tool_call
from api.data_apis import get_video_list, get_video_detail
from models.schemas import ToolCall

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# 全局 LLM 客户端
# ------------------------------------------------------------------------------

_openai_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    """延迟初始化 OpenAI 异步客户端。"""
    global _openai_client
    if _openai_client is None:
        logger.info(f"[LLM] 初始化客户端: base_url={settings.LLM_BASE_URL}, model={settings.LLM_MODEL}")
        _openai_client = AsyncOpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
        )
    return _openai_client


# ------------------------------------------------------------------------------
# System Prompt（直接、明确、无歧义）
# ------------------------------------------------------------------------------

_SYSTEM_PROMPT = ("""
    你是一个数据接口调度专家。你的唯一任务是根据用户需求和可用的数据接口列表，
    生成一个可直接执行的工具调用序列（tool_calls），以及最终需要从结果中提取的字段列表。\n\n
    ## 输出格式（必须严格按此 JSON 格式输出，不要任何其他文字）\n
    {\n
      "tool_calls": [\n
       {\n
          "tool": "工具名称",\n
          "arguments": {"参数名": "参数值"},\n
          "purpose": "这步的目的，用一句话说明"\n
       }\n
      ],\n
      "filters": {\n
        "topic": "话题关键词，如'星布谷地'，没有就留空字符串",\n
        "start_date": "开始日期，格式YYYY-MM-DD，如2026-04-21，没有就留空字符串"\n
      },\n
      "extract_fields": [\n
        "字段1", "字段2", ...\n
      ],\n
      "reasoning": "你的思考过程，用中文简述"\n
    }\n\n
    ## 关键规则（必须遵守）\n
    1. tool_calls 中的工具名必须是下面列出的可用工具之一，严禁编造。\n
    2. 如果需求涉及话题/标签筛选，必须调用 get_video_detail（唯一返回 Tags 和 participle 的接口）。\n
    3. 如果需要获取视频列表，必须先调 get_video_list。\n
    4. topic 和 start_date 必须从用户需求中提取，不能遗漏。\n
    5. extract_fields 列出用户最终想要看到的数据字段名（如 title, pubdate, stat.view, tags 等）。\n
    6. 只输出 JSON，不要任何 markdown 代码块标记（如 ```json），不要任何解释性文字。
    """
)


# ------------------------------------------------------------------------------
# Plan 生成（LLM 做接口选型）
# ------------------------------------------------------------------------------

async def generate_plan(
    question: str,
    tools: list[dict],
    user_filters: dict[str, Any],
) -> dict[str, Any]:
    """让 LLM 根据需求选择接口并生成调用序列。

    LLM 只做"接口选型"——根据需求描述和可用工具列表，决定调用哪些接口、
    提取什么过滤条件。完全不关心具体有多少个达人，那是执行阶段的事。

    Args:
        question: 用户的自然语言需求。
        tools: 可用工具定义列表（OpenAI format）。
        user_filters: 前端传入的过滤条件（topic / start_date），作为兜底。

    Returns:
        解析后的计划 dict，包含 tool_calls / filters / extract_fields 等。

    Raises:
        RuntimeError: LLM 调用失败或输出格式错误时直接报错，绝不降级。
    """
    logger.info(f"[Plan] 开始接口选型，需求: {question}")

    # 构造精简的工具描述（只给名称和描述，不给完整 JSON Schema，减少 token）
    tools_summary = []
    for t in tools:
        func = t.get("function", {})
        tools_summary.append(f"- {func.get('name', '未知')}: {func.get('description', '无描述')}")
    tools_desc = "\n".join(tools_summary)

    # 构造 prompt（需求 + 工具列表）
    prompt = (
        f"【用户需求】\n{question}\n\n"
        f"【可用工具列表】\n{tools_desc}\n\n"
        "请根据用户需求，生成工具调用序列和过滤条件。"
    )

    client = _get_client()

    # kimi-k2.6 响应慢，重试 2 次，单次超时 300 秒
    max_attempts = 2
    timeout_seconds = 300
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            logger.info(f"[Plan] 调用 LLM ({settings.LLM_MODEL}) 进行接口选型... (attempt {attempt}/{max_attempts})")
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=settings.LLM_MAX_TOKENS,
                    temperature=1.0,  # kimi-k2.6 只支持 1.0
                ),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning(f"[Plan] LLM 调用超时（{timeout_seconds}秒），attempt {attempt}/{max_attempts}")
            last_error = f"LLM 接口选型超时（{timeout_seconds}秒）"
            if attempt < max_attempts:
                continue
            raise RuntimeError(last_error)
        except Exception as exc:
            logger.error(f"[Plan] LLM 调用异常: {exc}")
            last_error = f"LLM 接口选型失败: {exc}"
            if attempt < max_attempts:
                continue
            raise RuntimeError(last_error)

        # 解析响应
        choice = response.choices[0]
        msg = choice.message
        content = msg.content or ""

        logger.info(f"[Plan] LLM 响应 finish_reason={choice.finish_reason}, content_len={len(content)}")
        if response.usage:
            logger.info(
                f"[Plan] LLM usage: prompt={response.usage.prompt_tokens}, "
                f"completion={response.usage.completion_tokens}, total={response.usage.total_tokens}"
            )

        if not content.strip():
            refusal = getattr(msg, "refusal", "N/A")
            logger.error(
                f"[Plan] LLM 返回空内容 — finish_reason={choice.finish_reason}, "
                f"role={msg.role}, refusal={refusal}"
            )
            last_error = (
                f"LLM 返回空内容 (finish_reason={choice.finish_reason}, "
                f"refusal={refusal})"
            )
            if attempt < max_attempts:
                logger.info("[Plan] 检测到空内容，自动重试...")
                continue
            raise RuntimeError(last_error)

        try:
            plan = json.loads(content)
        except json.JSONDecodeError as exc:
            logger.error(f"[Plan] LLM 返回非 JSON: {content[:500]}")
            last_error = f"LLM 返回格式错误（非 JSON）: {exc}"
            if attempt < max_attempts:
                continue
            raise RuntimeError(last_error)

        # 校验必要字段
        if "tool_calls" not in plan:
            last_error = "LLM 输出缺少 tool_calls 字段"
            if attempt < max_attempts:
                logger.warning(f"[Plan] {last_error}，自动重试...")
                continue
            raise RuntimeError(last_error)

    # 强制兜底：如果 LLM 没提取到过滤条件，用前端传入的值
    filters = plan.get("filters", {})
    if not filters.get("topic") and user_filters.get("topic"):
        filters["topic"] = user_filters["topic"]
        logger.info(f"[Plan] topic 使用前端兜底值: {filters['topic']}")
    if not filters.get("start_date") and user_filters.get("start_date"):
        filters["start_date"] = user_filters["start_date"]
        logger.info(f"[Plan] start_date 使用前端兜底值: {filters['start_date']}")
    plan["filters"] = filters

    logger.info(f"[Plan] 接口选型成功: {plan.get('reasoning', '无')}")
    logger.info(f"[Plan] 调用链: {[tc['tool'] for tc in plan['tool_calls']]}")
    logger.info(f"[Plan] 过滤条件: {filters}")
    logger.info(f"[Plan] 提取字段: {plan.get('extract_fields', [])}")

    return plan


# ------------------------------------------------------------------------------
# 数据提取辅助（兼容观星 API 两种返回结构：直接返回 vs data 嵌套）
# ------------------------------------------------------------------------------

def _safe_get(obj: Any, *keys: str, default: Any = None) -> Any:
    """安全地从嵌套 dict 中按顺序取字段，遇到非 dict 或缺失时返回 default。

    示例：_safe_get(resp, "data", "list", "vlist", default=[])
    """
    if not isinstance(obj, dict):
        return default
    for key in keys:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(key, default)
    return obj


def _find_list_field(data: dict, *field_names: str) -> list[dict]:
    """在 dict 中按顺序查找第一个存在且为 list 的字段。"""
    for name in field_names:
        val = data.get(name)
        if isinstance(val, list):
            return val
    return []


def _extract_vlist(data: Any) -> list[dict]:
    """从 get_video_list 返回的数据中提取视频列表，兼容多种字段名和嵌套结构。"""
    if not isinstance(data, dict):
        return []

    # 常见视频列表字段名（按优先级排序）
    list_fields = ("vlist", "archives", "list", "videos", "items", "records")

    # 路径 1: {data: {list: {vlist: [...]}}}
    inner = _safe_get(data, "data", "list", default={})
    if isinstance(inner, dict):
        videos = _find_list_field(inner, *list_fields)
        if videos:
            return videos

    # 路径 2: {data: {vlist: [...]}}
    inner = _safe_get(data, "data", default={})
    if isinstance(inner, dict):
        videos = _find_list_field(inner, *list_fields)
        if videos:
            return videos

    # 路径 3: 顶层直接 {vlist: [...]}
    videos = _find_list_field(data, *list_fields)
    if videos:
        return videos

    # 兜底：如果 data 本身就是 list（极少数情况）
    if isinstance(data, list):
        return data

    return []


def _extract_page_info(data: Any) -> dict:
    """从 get_video_list 返回的数据中提取分页信息。"""
    if not isinstance(data, dict):
        return {}
    # 路径 1: {data: {list: {page: {...}}}}
    page = _safe_get(data, "data", "list", "page", default={})
    if isinstance(page, dict) and page:
        return page
    # 路径 2: {data: {page: {...}}}
    page = _safe_get(data, "data", "page", default={})
    if isinstance(page, dict) and page:
        return page
    # 路径 3: 顶层 {page: {...}}
    page = data.get("page", {})
    if isinstance(page, dict) and page:
        return page
    return {}


def _extract_video_detail(detail: Any) -> tuple[dict, list, list]:
    """从 get_video_detail 返回的数据中提取 View、Tags、participle，兼容多种结构。

    Returns:
        (view_dict, tags_list, participle_list)
    """
    if not isinstance(detail, dict):
        return {}, [], []

    # 路径 1: {data: {View, Tags, participle}}
    view = _safe_get(detail, "data", "View", default={})
    tags = _safe_get(detail, "data", "Tags", default=[])
    participle = _safe_get(detail, "data", "participle", default=[])

    # 路径 2: 直接 {View, Tags, participle}
    if not view:
        view = detail.get("View", {})
    if not tags:
        tags = detail.get("Tags", [])
    if not participle:
        participle = detail.get("participle", [])

    # 路径 3: Tags 可能是 dict 包裹的数组，如 {"Tags": {"tag": [...]}}
    if isinstance(tags, dict):
        tags = tags.get("tag", [])

    return view, tags, participle


def _extract_timestamp(video: dict) -> int:
    """从视频 dict 中提取发布时间戳，兼容多种字段名。"""
    for key in ("created", "pubdate", "ctime", "timestamp", "publish_time", "addtime"):
        val = video.get(key)
        if isinstance(val, int) and val > 0:
            return val
        if isinstance(val, str):
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
    return 0


# ------------------------------------------------------------------------------
# 批量执行引擎
# ------------------------------------------------------------------------------

async def run_batch_task(
    question: str,
    creators: list[dict],
    plan: dict[str, Any],
) -> AsyncGenerator[str, None]:
    """执行批量抓取任务，通过 SSE 流式返回进度。
    AsyncGenerator[str, None]:异步生成器
    """
    logger.info(f"[Batch] 开始批量任务，达人: {len(creators)}")
    yield _sse_event("start", {"message": "开始批量抓取任务", "total_creators": len(creators)})

    filters = plan.get("filters", {})
    topic = filters.get("topic", "")
    start_date = filters.get("start_date", "")

    logger.info(f"[Batch] 最终过滤条件: topic={topic!r}, start_date={start_date!r}")

    # 如果 topic 为空，直接报错——说明 LLM 没提取到，前端也没兜底
    if not topic:
        logger.error("[Batch] topic 为空！LLM 未提取到话题关键词，且前端未传入")
        yield _sse_event("error", {"message": "未识别到话题关键词，请在「话题关键词」输入框中填写"})
        yield _sse_event("done", {})
        return

    # 解析 start_date 为时间戳
    start_timestamp = None
    if start_date:
        try:
            start_timestamp = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
            logger.info(f"[Batch] 时间戳过滤: >= {start_timestamp} ({start_date})")
        except ValueError:
            logger.warning(f"[Batch] start_date 格式错误: {start_date}")

    all_matched_videos: list[dict] = []

    # 限定最大并发次数
    semaphore = asyncio.Semaphore(settings.BATCH_CONCURRENCY)

    async def process_one_creator(creator: dict, idx: int) -> list[dict]:
        upper_mid = creator.get("upper_mid")
        nickname = creator.get("nickname", f"UP主_{upper_mid}")
        logger.info(f"[Batch] 处理达人 {idx+1}/{len(creators)}: {nickname} (mid={upper_mid})")
        matched: list[dict] = []

        async with semaphore:
            # 1. 翻页获取视频列表
            all_videos: list[dict] = []
            for pn in range(1, settings.MAX_PAGE_PER_UP + 1):
                logger.info(f"[Batch]   {nickname} - 获取视频列表 page={pn}")
                data = await get_video_list(upper_mid=upper_mid, pn=pn)

                # 如果 API 返回错误结构
                if isinstance(data, dict) and "error" in data:
                    logger.warning(f"[Batch]   {nickname} - page={pn} API 错误: {data.get('error')}")
                    break

                # DEBUG: 打印 API 返回的原始结构 keys
                data_keys = list(data.keys()) if isinstance(data, dict) else type(data).__name__
                logger.info(f"[Batch]   {nickname} - API 返回顶层 keys: {data_keys}")

                # 使用兼容函数提取视频列表
                vlist = _extract_vlist(data)
                if not vlist:
                    logger.info(f"[Batch]   {nickname} - page={pn} 无视频，结束翻页")
                    break

                all_videos.extend(vlist)
                logger.info(f"[Batch]   {nickname} - page={pn} 获取 {len(vlist)} 条视频")

                page_info = _extract_page_info(data)
                total_count = page_info.get("count", 0)
                ps = page_info.get("ps", 50)
                if pn * ps >= total_count:
                    logger.info(f"[Batch]   {nickname} - 已到达最后一页")
                    break

            logger.info(f"[Batch]   {nickname} - 共获取 {len(all_videos)} 条视频")

            # 2. 按发布时间过滤（兼容 created / pubdate / ctime 等多种字段名）
            candidate_videos = []
            for v in all_videos:
                ts = _extract_timestamp(v)
                if start_timestamp and ts > 0 and ts < start_timestamp:
                    continue
                candidate_videos.append(v)
            logger.info(f"[Batch]   {nickname} - 时间过滤后剩余 {len(candidate_videos)} 条")

            # 3. 获取视频详情（含标签）并做话题过滤
            for v in candidate_videos:
                bvid = v.get("bvid")
                if not bvid:
                    continue

                detail = await get_video_detail(id=bvid)
                if isinstance(detail, dict) and "error" in detail:
                    logger.warning(f"[Batch]   {nickname} - {bvid} detail API 错误: {detail.get('error')}")
                    continue

                view, tags, participle = _extract_video_detail(detail)

                # 话题过滤（在标题、描述、动态、标签、分词中全文匹配）
                tag_names = [t.get("tag_name", "") for t in tags if isinstance(t, dict)]
                all_tags_text = " ".join(tag_names + participle)
                title = view.get("title", "")
                desc = view.get("desc", "")
                dynamic = view.get("dynamic", "")
                combined_text = f"{title} {desc} {dynamic} {all_tags_text}"

                # 支持 #话题 和 话题 互相匹配：统一去掉 # 号后比较
                search_topic = topic.lstrip("#").strip()
                if not search_topic:
                    continue
                if search_topic.lower() not in combined_text.lower():
                    continue

                matched.append(
                    {
                        "creator_nickname": nickname,
                        "creator_mid": upper_mid,
                        "bvid": bvid,
                        "aid": v.get("aid"),
                        "title": view.get("title", v.get("title", "")),
                        "pubdate": view.get("pubdate", v.get("created", 0)),
                        "description": view.get("desc", ""),
                        "dynamic": view.get("dynamic", ""),
                        "duration": view.get("duration", 0),
                        "pic": view.get("pic", v.get("pic", "")),
                        "tags": tag_names,
                        "participle": participle,
                        "stat": view.get("stat", {}),
                        "url": f"https://www.bilibili.com/video/{bvid}",
                    }
                )

            logger.info(f"[Batch]   {nickname} - 匹配 {len(matched)} 条视频")

        return matched

    # 并发执行所有达人
    tasks = [process_one_creator(c, i) for i, c in enumerate(creators)]

    completed = 0
    for coro in asyncio.as_completed(tasks):
        matched = await coro
        all_matched_videos.extend(matched)
        completed += 1
        logger.info(f"[Batch] 进度: {completed}/{len(creators)}, 累计匹配: {len(all_matched_videos)}")
        yield _sse_event(
            "progress",
            {
                "completed": completed,
                "total": len(creators),
                "matched_so_far": len(all_matched_videos),
            },
        )

    logger.info(f"[Batch] 任务完成，共匹配 {len(all_matched_videos)} 条视频")
    yield _sse_event(
        "final",
        {
            "total_creators": len(creators),
            "matched_videos": len(all_matched_videos),
            "videos": all_matched_videos,
        },
    )
    yield _sse_event("done", {})



def _sse_event(event: str, data: dict) -> str:
    """将事件打包为 SSE 标准格式字符串。"""
    payload = {
        "event": event,
        "content": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
