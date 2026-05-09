"""
批量任务规划器 — 通用工作流解释器架构

核心设计：
1. 单轮 LLM 一次性输出单一工作流 JSON（全局过滤 + 统一工作流 + 导出字段）
2. 后端变成通用工作流解释器：完全根据 LLM 返回的 workflow JSON 自动执行
3. 废弃所有硬编码 if/elif 策略分支，新增工具/流程不用改调度代码
4. 每条达人任务独立维护 param_pool，工具返回自动回填，下一个工具自动喂入参
5. 执行策略：参数不足 → 跳过继续下一步；API 失败 → 记日志跳过继续下一步
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from openai import AsyncOpenAI

from config import settings
from models.schemas import ToolCall, LLMWorkflowPlan, GlobalFilter
from agent import executor

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# 任务状态缓存与取消控制（完全保留原有逻辑）
# ------------------------------------------------------------------------------

task_cache: dict[str, dict[str, Any]] = {}
task_cancel_events: dict[str, asyncio.Event] = {}
task_locks: dict[str, asyncio.Lock] = {}

MAX_CACHE_TASKS = 100
CACHE_TTL_SECONDS = 300


def get_task_status(task_id: str) -> dict[str, Any] | None:
    return task_cache.get(task_id)


def _get_task_lock(task_id: str) -> asyncio.Lock:
    if task_id not in task_locks:
        task_locks[task_id] = asyncio.Lock()
    return task_locks[task_id]


def _enforce_cache_limit() -> None:
    if len(task_cache) <= MAX_CACHE_TASKS:
        return
    finished = [
        (tid, info.get("started_at", ""))
        for tid, info in task_cache.items()
        if info.get("status") in ("completed", "cancelled", "error")
    ]
    finished.sort(key=lambda x: x[1])
    to_remove = len(task_cache) - MAX_CACHE_TASKS
    for tid, _ in finished[:to_remove]:
        task_cache.pop(tid, None)
        task_locks.pop(tid, None)
        logger.info(f"[CacheLimit] 缓存超限，自动移除旧任务 {tid}")


async def _update_task_cache(task_id: str, **kwargs) -> None:
    async with _get_task_lock(task_id):
        if task_id not in task_cache:
            task_cache[task_id] = {
                "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "completed": 0,
                "total": 0,
                "matched_so_far": 0,
                "videos": [],
            }
        task_cache[task_id].update(kwargs)
        _enforce_cache_limit()


def _cleanup_cancel_event(task_id: str) -> None:
    task_cancel_events.pop(task_id, None)


def _schedule_task_cleanup(task_id: str, delay: int = CACHE_TTL_SECONDS) -> None:
    async def _cleanup() -> None:
        await asyncio.sleep(delay)
        async with _get_task_lock(task_id):
            if task_id in task_cache:
                task_cache.pop(task_id, None)
                logger.info(f"[Cleanup] 任务 {task_id} 缓存已清理（TTL 到期）")
            task_locks.pop(task_id, None)
            task_cancel_events.pop(task_id, None)
    asyncio.create_task(_cleanup())


def cancel_task(task_id: str) -> bool:
    if task_id in task_cancel_events:
        task_cancel_events[task_id].set()
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon(asyncio.create_task, _update_task_cache(task_id, status="cancelled"))
        except RuntimeError:
            if task_id in task_cache:
                task_cache[task_id]["status"] = "cancelled"
        logger.info(f"[Task] 任务 {task_id} 已标记取消")
        return True
    return False


async def _watch_cancel(task_id: str, cancel_event: asyncio.Event, tasks: list[asyncio.Task]) -> None:
    try:
        await cancel_event.wait()
        logger.info(f"[CancelWatcher][{task_id}] 检测到取消信号，开始清理 {len([t for t in tasks if not t.done()])} 个未完成的子任务")
        for t in tasks:
            if not t.done():
                t.cancel()
    except asyncio.CancelledError:
        pass


async def _continue_in_background(
    tasks: list[asyncio.Task],
    task_id: str,
    all_matched_videos: list[dict],
    completed_so_far: int,
    cancel_event: asyncio.Event,
    total: int,
) -> None:
    """SSE 断开后，在后台继续等待剩余 asyncio.Task 完成并更新任务缓存。"""
    logger.info(f"[Background] 接管任务 {task_id}，继续后台运行（已完成 {completed_so_far}/{total}）")
    completed = completed_so_far
    pending_tasks = [t for t in tasks if not t.done()]
    logger.info(f"[Background] 剩余未完成 task 数: {len(pending_tasks)}/{total}")

    # 关键修复：无论哪种退出路径，都必须触发 TTL 清理，防止 task_cache / task_locks 永久残留
    def _finish(status: str) -> None:
        if task_id in task_cancel_events:
            del task_cancel_events[task_id]
        asyncio.create_task(_update_task_cache(
            task_id,
            status=status,
            completed=completed,
            matched_so_far=len(all_matched_videos),
            videos=all_matched_videos,
        ))
        _schedule_task_cleanup(task_id)
        logger.info(f"[Background] 任务 {task_id} 后台完成，状态={status}，共匹配 {len(all_matched_videos)} 条")

    if not pending_tasks:
        status = "cancelled" if cancel_event.is_set() else "completed"
        _finish(status)
        return

    try:
        for coro in asyncio.as_completed(pending_tasks):
            if cancel_event.is_set():
                logger.info(f"[Background] 任务 {task_id} 被取消，停止后台采集")
                for t in pending_tasks:
                    t.cancel()
                await asyncio.gather(*pending_tasks, return_exceptions=True)
                _finish("cancelled")
                return
            try:
                matched = await coro
            except asyncio.CancelledError:
                continue
            except Exception as exc:
                logger.warning(f"[Background] 达人任务异常: {exc}")
                continue
            all_matched_videos.extend(matched)
            completed += 1
            await _update_task_cache(
                task_id,
                completed=completed,
                matched_so_far=len(all_matched_videos),
                videos=all_matched_videos,
            )
            logger.info(f"[Background] 进度: {completed}/{total}, 累计匹配: {len(all_matched_videos)}")
    except Exception as exc:
        logger.error(f"[Background] 后台任务异常: {exc}")
        _finish("error")
        return

    status = "cancelled" if cancel_event.is_set() else "completed"
    _finish(status)


# ------------------------------------------------------------------------------
# 全局 LLM 客户端
# ------------------------------------------------------------------------------

_openai_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        logger.info(f"[LLM] 初始化客户端: base_url={settings.LLM_BASE_URL}, model={settings.LLM_MODEL}")
        _openai_client = AsyncOpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
        )
    return _openai_client


# ------------------------------------------------------------------------------
# System Prompt（单一工作流，不再区分 space/video/short）
# ------------------------------------------------------------------------------

_TOOLS_DESC = executor.build_tools_prompt()

_SYSTEM_PROMPT = (
    "你是一个数据接口调度专家。你的唯一任务是根据用户需求、Excel 中已有的数据字段和可用的数据接口列表，"
    "生成一个单一的工作流规划 JSON。所有达人都会执行同一套工作流，后端会根据每个达人已有的数据自适应执行。\n\n"
    "## 系统背景\n"
    "用户上传的 Excel 中，每一行可能包含以下信息（不是全部都有）：\n"
    "- upper_mid：UP主ID（可从 space.bilibili.com/{mid} 或独立 mid 列提取）\n"
    "- bvid：视频BV号（可从 bilibili.com/video/BVxxx 链接中提取）\n"
    "- avid：视频AV号（可从 bilibili.com/video/avxxx 链接中提取）\n"
    "- short_code：短链接代码（可从 b23.tv/xxxx 链接中提取，需要用 resolve_short_url 解析为真实URL）\n"
    "- nickname：UP主昵称\n"
    "- 各种 URL（主页链接、视频链接、短链接）\n\n"
    "你的任务是编排一套通用工作流：参数足的步骤就执行，参数不足的步骤自动跳过，"
    "后续步骤可以继续利用前面步骤回填的参数继续执行。\n\n"
    f"{_TOOLS_DESC}\n\n"
    "## 输出格式（必须严格按此 JSON 格式输出，不要任何其他文字）\n\n"
    "{\n"
    '  "global_filter": {\n'
    '    "topic": "话题关键词，没有就留空字符串",\n'
    '    "start_date": "开始日期 YYYY-MM-DD，没有就留空",\n'
    '    "end_date": "结束日期 YYYY-MM-DD，没有就留空"\n'
    "  },\n"
    '  "export_fields": ["字段1", "字段2", ...],\n'
    '  "workflow": {\n'
    '    "tool_sequence": [\n'
    '      {"tool_name": "工具名", "reason": "为什么需要这步，及前置依赖关系"}\n'
    "    ],\n"
    '    "page_rule": {\n'
    '      "enable_page": true,\n'
    '      "max_page": 10,\n'
    '      "page_size": 50\n'
    "    },\n"
    '    "each_detail": {\n'
    '      "need_query": true,\n'
    '      "tool_name": "get_video_detail"\n'
    "    }\n"
    "  },\n"
    '  "reasoning": "你的思考过程，用中文简述"\n'
    "}\n\n"
    "## 工作流编排指南（必须遵守）\n"
    "1. **按需编排，不要画蛇添足**。tool_sequence 里只放真正需要的步骤：\n"
    "   - 如果用户只要'这些视频的数据'（输入是 bvid/视频链接），直接调 get_video_data 即可，不需要 get_video_list。\n"
    "   - 如果用户要'UP主全部视频'或'按时间筛选近期作品'，才需要 get_video_list。\n"
    "   - 如果用户要'话题/标签'，才需要 get_video_detail。\n"
    "   - 如果用户要'粉丝数'，才需要 get_up_follower。\n"
    "   - 绝不要'为了保险'而多加步骤。每一步都应该是用户需求直接驱动的。\n"
    "2. **短链接 vs 普通链接**（**极其重要**）：\n"
    "   - **判断方式**：根据下面的【Excel 数据特征】判断。如果有 creator 的 link_type='short' 或 short_code 有值，说明存在短链接。\n"
    "   - **只要有短链接**，tool_sequence 里**必须**前置 resolve_short_url（放在第一个），把 b23.tv/xxxx 解析为真实 bvid/avid/mid。\n"
    "   - resolve_short_url 返回的 bvid 会自动流入后续步骤（如 get_video_data），**不要**跳过它。\n"
    "   - 如果输入已经是 bilibili.com/video/BVxxx 或 bilibili.com/video/avxxx 格式的**普通视频链接**，"
    "     bvid/avid 已经可以直接提取，**不要**编排 resolve_short_url，直接调 get_video_data 即可。\n"
    "   - **绝对禁止**'以防万一'给没有短链接的任务编排 resolve_short_url。\n"
    "   - **也绝对禁止**在有短链接时跳过 resolve_short_url，否则所有短链接都会因缺少 bvid 而参数不足。\n"
    "3. **参数推导**：tool_sequence 按依赖顺序排列，但只放必要步骤。\n"
    "   - 参数不足的步骤后端会自动跳过，不会报错。\n"
    "   - **关键规则**：先看 Excel 数据特征（含 mid / bvid / short 的比例）。\n"
    "     - 如果**大部分** creator 已有 upper_mid（如 space 主页链接）：\n"
    "       直接编排 get_video_list 等需要 mid 的工具，**不需要**前置 get_video_data。\n"
    "       只有 bvid/short 的少数 creator 会因参数不足自动跳过，这是正常行为。\n"
    "     - 如果**大部分** creator 只有 bvid/avid 没有 mid：\n"
    "       才需要在 tool_sequence 里前置 get_video_data，通过 bvid 反查 owner.mid，\n"
    "       为后续 get_video_list 提供参数。\n"
    "     - 绝不要'以防万一'给所有 creator 都加 get_video_data 前置。\n"
    "       编排应该基于**主流数据特征**，而不是极端情况。\n"
    "4. page_rule 仅对 tool_sequence 最后一步返回列表的工具有效：\n"
    "   - enable_page=true 时，后端会自动翻页采集，直到 max_page 或数据采完。\n"
    "   - 只有返回列表的工具（如 get_video_list）才需要 enable_page=true。\n"
    "5. each_detail 用于列表采完后是否逐条查详情：\n"
    "   - 如果用户需要标签/话题匹配，need_query=true，tool_name=get_video_detail。\n"
    "   - 如果只需要基础数据，need_query=false。\n"
    "6. topic/start_date/end_date 必须从用户需求中提取。没有提到就留空字符串（\"\"），严禁臆测。\n"
    "7. **export_fields 必须完整**：根据用户需求，列出所有需要导出的字段名，不能遗漏。\n"
    "   - **绝对禁止**只返回 [\"bvid\",\"mid\"] 或 [\"bvid\",\"title\",\"creator_nickname\"] 这种只有标识字段的列表。\n"
    "   - 用户要的是视频数据，必须包含**内容字段**和**统计字段**，缺一不可。\n"
    "   - 常用字段参考（按场景必选）：\n"
    "     · 内容字段（必选）：title(标题), pubdate(发布时间), duration(时长秒数), desc(描述), pic(封面图)\n"
    "     · 统计字段（必选）：view(播放量), danmaku(弹幕), reply(评论), favorite(收藏), coin(投币), share(分享), like(点赞)\n"
    "     · 标识字段：bvid(BV号), creator_nickname(UP主昵称), creator_mid(UP主MID)\n"
    "     · 标签字段：tags(标签数组), participle(话题数组)\n"
    "     · 作者字段：follower(粉丝数), following(关注数)\n"
    "   - 字段名必须是反参中实际存在的字段名，后端会从接口返回中自动提取映射。\n"
    "   - **强制模板**：只要用户提到'视频'、'数据'、'统计'、'播放量'、'点赞'等词，export_fields 必须至少包含：\n"
    "     [\"bvid\",\"title\",\"pubdate\",\"duration\",\"view\",\"like\",\"reply\",\"favorite\",\"coin\",\"share\",\"danmaku\",\"creator_nickname\",\"creator_mid\",\"url\"]\n"
    "   - 示例：用户要'视频数据和播放统计' → export_fields=[\"bvid\",\"title\",\"pubdate\",\"duration\",\"view\",\"like\",\"reply\",\"favorite\",\"coin\",\"share\",\"danmaku\",\"url\",\"creator_nickname\",\"creator_mid\"]\n"
    "   - 示例：用户要'UP主粉丝数' → export_fields=[\"creator_nickname\",\"creator_mid\",\"follower\",\"following\"]\n"
    "   - **再次强调**：只返回标识字段会被视为严重错误。\n"
    "8. 只输出 JSON，不要任何 markdown 代码块标记，不要任何解释性文字。"
)


# ------------------------------------------------------------------------------
# Plan 生成
# ------------------------------------------------------------------------------

def _build_creator_summary(creators: list[dict]) -> str:
    if not creators:
        return "未提供任何达人数据。"
    total = len(creators)
    link_types: dict[str, int] = {}
    has_mid = 0
    has_bvid = 0
    has_avid = 0
    has_short = 0
    for c in creators:
        lt = c.get("link_type", "unknown")
        link_types[lt] = link_types.get(lt, 0) + 1
        if c.get("upper_mid"):
            has_mid += 1
        if c.get("bvid"):
            has_bvid += 1
        if c.get("avid"):
            has_avid += 1
        if c.get("short_code"):
            has_short += 1
    lines = [f"共 {total} 条记录："]
    for lt, count in sorted(link_types.items(), key=lambda x: -x[1]):
        lines.append(f"  - link_type='{lt}': {count} 条")
    if has_mid:
        lines.append(f"  - 含 mid (upper_mid): {has_mid} 条")
    if has_bvid:
        lines.append(f"  - 含 bvid: {has_bvid} 条")
    if has_avid:
        lines.append(f"  - 含 avid: {has_avid} 条")
    if has_short:
        lines.append(f"  - 含 short_code（短链接 b23.tv）: {has_short} 条 ⚠️ 这些必须编排 resolve_short_url")

    # 给 LLM 多个示例，优先覆盖不同 link_type，避免 LLM 根据单个样本推断
    samples: list[str] = []
    seen_types: set[str] = set()
    # 第一轮：优先取不同 link_type 的样本
    for c in creators:
        if len(samples) >= 3:
            break
        lt = c.get("link_type", "unknown")
        if lt in seen_types:
            continue
        fields = []
        for key in ("nickname", "link_type", "upper_mid", "bvid", "avid", "short_code"):
            val = c.get(key)
            if val is not None:
                fields.append(f"{key}={val!r}")
        sample_str = f"{{{', '.join(fields)}}}"
        if sample_str:
            samples.append(sample_str)
            seen_types.add(lt)
    # 第二轮：补充不同字段特征的样本
    for c in creators:
        if len(samples) >= 3:
            break
        fields = []
        for key in ("nickname", "link_type", "upper_mid", "bvid", "avid", "short_code"):
            val = c.get(key)
            if val is not None:
                fields.append(f"{key}={val!r}")
        sample_str = f"{{{', '.join(fields)}}}"
        if sample_str and sample_str not in samples:
            samples.append(sample_str)
    lines.append(f"  - 示例记录: {' | '.join(samples)}")
    return "\n".join(lines)


async def generate_plan(
    question: str,
    tools: list[dict],
    user_filters: dict[str, Any],
    creators: list[dict] | None = None,
) -> dict[str, Any]:
    logger.info(f"[Plan] 开始工作流规划，需求: {question}")

    tools_summary = []
    for t in tools:
        func = t.get("function", {})
        tools_summary.append(f"- {func.get('name', '未知')}: {func.get('description', '无描述')}")
    tools_desc = "\n".join(tools_summary)

    creator_summary = _build_creator_summary(creators or [])

    prompt = (
        f"【用户需求】\n{question}\n\n"
        f"【Excel 中已有的数据字段】\n{creator_summary}\n\n"
        f"【可用工具列表】\n{tools_desc}\n\n"
        "请根据用户需求和 Excel 中已有的数据字段，生成单一的工作流规划 JSON。"
        "注意：只输出一套工作流，所有达人统一执行。参数不足的步骤会自动跳过。"
    )

    client = _get_client()
    max_attempts = 2
    timeout_seconds = 600
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            logger.info(f"[Plan] 调用 LLM ({settings.LLM_MODEL})... (attempt {attempt}/{max_attempts})")
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=settings.LLM_MAX_TOKENS,
                    temperature=1.0,
                ),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            last_error = f"LLM 工作流规划超时（{timeout_seconds}秒）"
            if attempt < max_attempts:
                continue
            raise RuntimeError(last_error)
        except Exception as exc:
            last_error = f"LLM 工作流规划失败: {exc}"
            if attempt < max_attempts:
                continue
            raise RuntimeError(last_error)

        choice = response.choices[0]
        msg = choice.message
        content = msg.content or ""

        if not content.strip():
            last_error = f"LLM 返回空内容 (finish_reason={choice.finish_reason})"
            if attempt < max_attempts:
                continue
            raise RuntimeError(last_error)

        try:
            raw_plan = json.loads(content)
        except json.JSONDecodeError as exc:
            last_error = f"LLM 返回格式错误: {exc}"
            if attempt < max_attempts:
                continue
            raise RuntimeError(last_error)

        if isinstance(raw_plan, str):
            try:
                raw_plan = json.loads(raw_plan)
            except json.JSONDecodeError as exc:
                last_error = f"LLM 返回双重序列化 JSON 解析失败: {exc}"
                if attempt < max_attempts:
                    continue
                raise RuntimeError(last_error)

        if not isinstance(raw_plan, dict):
            last_error = f"LLM 返回格式错误（不是 dict 而是 {type(raw_plan).__name__}）"
            if attempt < max_attempts:
                continue
            raise RuntimeError(last_error)

        # 用 Pydantic 强校验
        try:
            workflow_plan = LLMWorkflowPlan(**raw_plan)
        except Exception as exc:
            last_error = f"LLM 返回工作流结构校验失败: {exc}"
            if attempt < max_attempts:
                continue
            raise RuntimeError(last_error)

        # 白名单校验：tool_sequence 中的工具必须在注册表中
        invalid_tools = set()
        valid_tool_names = set(executor.get_tool_names())
        wf = workflow_plan.workflow
        for step in wf.tool_sequence:
            if step.tool_name not in valid_tool_names:
                invalid_tools.add(step.tool_name)
        if wf.each_detail.need_query and wf.each_detail.tool_name not in valid_tool_names:
            invalid_tools.add(wf.each_detail.tool_name)

        if invalid_tools:
            last_error = f"LLM 返回了未知工具: {invalid_tools}"
            if attempt < max_attempts:
                continue
            raise RuntimeError(last_error)

        logger.info(f"[Plan] attempt {attempt} 验证通过")
        break

    if "workflow_plan" not in locals() or workflow_plan is None:
        raise RuntimeError(last_error or "LLM 工作流规划未知错误")

    # 合并用户传入的兜底过滤条件
    gf = workflow_plan.global_filter
    if not gf.topic and user_filters.get("topic"):
        gf.topic = user_filters["topic"]
    if not gf.start_date and user_filters.get("start_date"):
        gf.start_date = user_filters["start_date"]
    if not gf.end_date and user_filters.get("end_date"):
        gf.end_date = user_filters["end_date"]

    # 转回 dict 保持与原有接口兼容
    plan = workflow_plan.model_dump()
    logger.info(
        f"[Plan] 工作流规划成功: "
        f"tool_sequence={[s['tool_name'] for s in plan['workflow']['tool_sequence']]}, "
        f"filters={plan['global_filter']}"
    )
    return plan


# ------------------------------------------------------------------------------
# 数据提取辅助（复用已有逻辑，从 executor 引入）
# ------------------------------------------------------------------------------

_safe_get = executor._safe_get
_extract_vlist = executor._extract_vlist
_extract_page_info = executor._extract_page_info
_extract_video_detail = executor._extract_video_detail
_extract_timestamp = executor._extract_timestamp


# ------------------------------------------------------------------------------
# 通用工作流解释器 — 核心执行逻辑
# ------------------------------------------------------------------------------

def _dedup_video_list(video_list: list[dict]) -> list[dict]:
    """按 bvid 去重。"""
    seen: set[str] = set()
    deduped: list[dict] = []
    for v in video_list:
        if not isinstance(v, dict):
            continue
        bvid = v.get("bvid")
        if bvid and bvid not in seen:
            seen.add(bvid)
            deduped.append(v)
    return deduped


async def _query_each_detail(
    param_pool: dict[str, Any],
    workflow: Any,
    task_id: str,
    nickname: str,
) -> None:
    """对 video_list 中每条记录逐条调用详情工具。

    合并策略：get_video_detail 返回的 View 对象比 get_video_list 更完整，
    因此 View 中的字段优先覆盖 item 中的同名字段（但 item 中已有的有效值保留作为 fallback）。
    同时把 View 对象中的 stat（播放量/点赞/评论等统计）和 tags/participle 一并合并。
    """
    detail_tool = workflow.each_detail.tool_name
    video_list = param_pool.get("video_list", [])

    if not video_list or detail_tool not in executor.get_tool_names():
        return

    detailed: list[dict] = []
    for item in video_list:
        if task_id and task_id in task_cancel_events and task_cancel_events[task_id].is_set():
            break

        if not isinstance(item, dict):
            continue

        bvid = item.get("bvid")
        if bvid:
            param_pool["bvid"] = bvid

        # 关键：清空上一轮循环可能残留的详情字段，避免交叉污染
        # extract_tool_output 只在 API 返回了字段时才更新 param_pool；
        # 如果当前视频 API 没返回 Tags/View，param_pool 中就会残留上一条视频的数据
        for _stale_key in ("view", "tags", "participle", "card"):
            param_pool.pop(_stale_key, None)

        args = executor.build_args_from_pool(detail_tool, param_pool)
        if args is None:
            detailed.append(item)
            continue

        result = await executor.execute_tool_call(ToolCall(tool_name=detail_tool, arguments=args))
        if not result.success:
            detailed.append(item)
            continue

        # 提取详情数据到 param_pool
        executor.extract_tool_output(detail_tool, result.data, param_pool)

        merged = dict(item)
        view = param_pool.get("view", {})

        if view and isinstance(view, dict):
            # 直接覆盖合并：View 中的基础字段（get_video_detail 的数据比 get_video_list 更完整）
            for key in ("title", "pubdate", "duration", "desc", "dynamic", "pic", "bvid", "aid"):
                val = view.get(key)
                if val is not None and val != "":
                    merged[key] = val

            # stat 统计对象：直接覆盖（get_video_list 通常没有 stat，get_video_detail 才有）
            stat = view.get("stat")
            if isinstance(stat, dict) and stat:
                merged["stat"] = stat
                # 同时把 stat 中的核心统计字段扁平化到 merged，方便 _build_export_record 查找
                for stat_key in ("view", "danmaku", "reply", "favorite", "coin", "share", "like"):
                    if stat_key in stat:
                        merged[stat_key] = stat[stat_key]

            # owner 信息（UP主数据）
            owner = view.get("owner")
            if isinstance(owner, dict) and owner:
                if owner.get("mid"):
                    merged["owner_mid"] = owner["mid"]
                if owner.get("name"):
                    merged["owner_name"] = owner["name"]

        # tags / participle（话题标签）
        tags = param_pool.get("tags", [])
        if tags and isinstance(tags, list):
            merged["tags"] = tags
        participle = param_pool.get("participle", [])
        if participle and isinstance(participle, list):
            merged["participle"] = participle

        detailed.append(merged)

    param_pool["video_list"] = detailed


def _apply_global_filter(video_list: list[dict], global_filter: GlobalFilter) -> list[dict]:
    """按全局过滤条件筛选视频列表。"""
    topic = global_filter.topic.lstrip("#").strip() if global_filter.topic else ""
    start_date = global_filter.start_date
    end_date = global_filter.end_date

    start_ts = None
    end_ts = None
    if start_date:
        try:
            start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
        except ValueError:
            pass
    if end_date:
        try:
            end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp()) + 86399
        except ValueError:
            pass

    filtered: list[dict] = []
    for v in video_list:
        if not isinstance(v, dict):
            continue

        # 时间过滤
        ts = _extract_timestamp(v)
        if start_ts and ts > 0 and ts < start_ts:
            continue
        if end_ts and ts > 0 and ts > end_ts:
            continue

        # 话题过滤
        if topic:
            title = str(v.get("title", ""))
            desc = str(v.get("desc", "")) if v.get("desc") else str(v.get("description", ""))
            dynamic = str(v.get("dynamic", ""))
            tags = v.get("tags", [])
            tags_text = " ".join(str(t.get("tag_name", t)) if isinstance(t, dict) else str(t) for t in tags)
            participle = v.get("participle", [])
            participle_text = " ".join(str(p) for p in participle if isinstance(p, str))
            combined = f"{title} {desc} {dynamic} {tags_text} {participle_text}"
            if topic.lower() not in combined.lower():
                continue

        filtered.append(v)

    return filtered


def _build_export_record(
    item: dict,
    param_pool: dict[str, Any],
    export_fields: list[str],
    nickname: str,
) -> dict[str, Any] | None:
    """根据 export_fields 从 item 和 param_pool 中组装最终导出记录。

    字段来源优先级：
    1. item 中直接匹配的字段
    2. get_video_list 返回的 vlist 字段别名映射（play→view, comment→reply, created→pubdate, length→duration）
    3. param_pool 中的字段
    4. stat 对象中的统计字段
    5. get_video_detail 返回的 View 对象中的字段
    """
    record: dict[str, Any] = {}

    # get_video_list 返回的 vlist 字段名与标准字段名的映射
    _LIST_FIELD_ALIASES: dict[str, str] = {
        "play": "view",
        "comment": "reply",
        "created": "pubdate",
        "length": "duration",
        "description": "desc",
    }

    def _parse_duration(val: Any) -> int | None:
        """解析 get_video_list 返回的 length 字段（如 '3:45'）为秒数。"""
        if isinstance(val, int):
            return val
        if isinstance(val, str):
            parts = val.split(":")
            try:
                if len(parts) == 2:
                    return int(parts[0]) * 60 + int(parts[1])
                if len(parts) == 3:
                    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            except (ValueError, TypeError):
                pass
        return None

    def _get_field(field: str) -> Any:
        # 1. item 中直接匹配
        if field in item and item[field] is not None:
            return item[field]

        # 2. get_video_list 字段别名映射（vlist 中的 play/comment/created/length/description）
        for src_key, dst_key in _LIST_FIELD_ALIASES.items():
            if dst_key == field and src_key in item and item[src_key] is not None:
                if field == "duration":
                    parsed = _parse_duration(item[src_key])
                    if parsed is not None:
                        return parsed
                elif field == "view" or field == "reply":
                    # play/comment 是整数，直接返回
                    val = item[src_key]
                    if isinstance(val, int) and val >= 0:
                        return val
                else:
                    return item[src_key]

        # 3. param_pool 中直接匹配
        if field in param_pool and param_pool[field] is not None:
            return param_pool[field]

        # 4. 特殊字段映射
        if field == "description":
            return item.get("desc") or param_pool.get("desc")
        if field == "creator_nickname":
            return nickname or item.get("creator_nickname") or param_pool.get("owner_name") or param_pool.get("nickname")
        if field == "creator_mid":
            return item.get("creator_mid") or param_pool.get("upper_mid") or param_pool.get("owner_mid")
        if field == "url":
            bvid = item.get("bvid") or param_pool.get("bvid")
            if bvid:
                return f"https://www.bilibili.com/video/{bvid}"

        # 5. stat 对象中的统计字段（get_video_data / get_video_detail 返回的 stat.view 等）
        if field in ("view", "danmaku", "reply", "favorite", "coin", "share", "like"):
            # 5a. item.stat（可能来自 _query_each_detail 合并后的数据）
            stat = item.get("stat")
            if isinstance(stat, dict) and field in stat:
                return stat[field]
            # 5b. param_pool.stat（可能来自 get_video_data）
            stat = param_pool.get("stat")
            if isinstance(stat, dict) and field in stat:
                return stat[field]

        # 6. get_video_detail 返回的 View 对象中的字段
        view = item.get("view") or param_pool.get("view")
        if isinstance(view, dict):
            # 6a. View 对象直接包含的字段（title, pubdate, duration, desc, pic 等）
            if field in view and view[field] is not None:
                return view[field]
            # 6b. View.stat 中的统计字段
            if field in ("view", "danmaku", "reply", "favorite", "coin", "share", "like"):
                vstat = view.get("stat")
                if isinstance(vstat, dict) and field in vstat:
                    return vstat[field]

        # 7. get_video_detail 返回的 Card 对象中的字段
        card = item.get("card") or param_pool.get("card")
        if isinstance(card, dict) and field in card:
            return card[field]

        return None

    for field in export_fields:
        val = _get_field(field)
        if val is not None:
            record[field] = val

    # 兜底：确保 url / creator_nickname / creator_mid 始终存在
    if "url" not in record:
        bvid = item.get("bvid") or param_pool.get("bvid")
        if bvid:
            record["url"] = f"https://www.bilibili.com/video/{bvid}"
    if "creator_nickname" not in record:
        record["creator_nickname"] = nickname or item.get("creator_nickname") or param_pool.get("owner_name") or param_pool.get("nickname", "未知")
    if "creator_mid" not in record:
        record["creator_mid"] = item.get("creator_mid") or param_pool.get("upper_mid") or param_pool.get("owner_mid")

    return record if record else None


async def process_one_creator(
    creator: dict,
    idx: int,
    workflow_plan: LLMWorkflowPlan,
    task_id: str = "",
) -> list[dict]:
    """通用工作流解释器：所有 creator 执行同一套 workflow，参数不足/失败时跳过继续。

    核心流程：
    1. 初始化 param_pool（从 creator 自带字段填充）
    2. 按 workflow.tool_sequence 顺序逐步执行工具
    3. 参数不足 → 跳过该步骤，继续下一步
    4. API 调用失败 → 记日志，跳过该步骤，继续下一步
    5. 最后一步若 page_rule.enable_page=true，自动翻页采集
    6. 若 each_detail.need_query=true，对列表逐条查详情
    7. 按 global_filter 过滤
    8. 按 export_fields 组装最终记录
    """
    nickname = creator.get("nickname", "未知")
    workflow = workflow_plan.workflow

    # 初始化参数池
    param_pool: dict[str, Any] = {
        "upper_mid": creator.get("upper_mid"),
        "bvid": creator.get("bvid"),
        "avid": creator.get("avid"),
        "short_code": creator.get("short_code"),
        "nickname": nickname,
        "link_type": creator.get("link_type", "unknown"),
        "pn": 1,
    }

    # 兜底：如果 param_pool 里有 short_code 但没有 bvid，且 tool_sequence 中没有 resolve_short_url，
    # 自动在最前面执行 resolve_short_url，防止 LLM 漏编排导致所有短链接参数不足
    if (
        param_pool.get("short_code")
        and not param_pool.get("bvid")
        and not any(s.tool_name == "resolve_short_url" for s in workflow.tool_sequence)
    ):
        logger.info(f"[Batch][{task_id}] {nickname} 检测到短链接但未编排 resolve_short_url，自动执行")
        args = executor.build_args_from_pool("resolve_short_url", param_pool)
        if args:
            result = await executor.execute_tool_call(ToolCall(tool_name="resolve_short_url", arguments=args))
            if result.success:
                executor.extract_tool_output("resolve_short_url", result.data, param_pool)
                logger.info(f"[Batch][{task_id}] {nickname} 短链接解析成功: bvid={param_pool.get('bvid')}, mid={param_pool.get('upper_mid')}")
            else:
                logger.warning(f"[Batch][{task_id}] {nickname} 短链接解析失败: {result.error}")

    logger.info(f"[Batch][{task_id}] {nickname} 开始执行工作流")

    # 按 tool_sequence 顺序执行（参数不足或失败时跳过，继续下一步）
    for step_idx, step in enumerate(workflow.tool_sequence):
        tool_name = step.tool_name

        if task_id and task_id in task_cancel_events and task_cancel_events[task_id].is_set():
            break

        if tool_name not in executor.get_tool_names():
            logger.warning(f"[Batch][{task_id}] {nickname} 未知工具 {tool_name}，跳过")
            continue  # 跳过，继续下一步

        is_last_step = step_idx == len(workflow.tool_sequence) - 1
        enable_page = is_last_step and workflow.page_rule.enable_page

        if enable_page:
            all_items: list[dict] = []
            max_page = workflow.page_rule.max_page
            page_size = workflow.page_rule.page_size

            for pn in range(1, max_page + 1):
                if task_id and task_id in task_cancel_events and task_cancel_events[task_id].is_set():
                    break

                param_pool["pn"] = pn
                args = executor.build_args_from_pool(tool_name, param_pool)
                if args is None:
                    logger.info(f"[Batch][{task_id}] {nickname} {tool_name} 参数不足，跳过翻页")
                    break  # 参数不足，停止翻页（但继续 workflow 后续步骤）

                result = await executor.execute_tool_call(ToolCall(tool_name=tool_name, arguments=args))
                if not result.success:
                    logger.warning(f"[Batch][{task_id}] {nickname} {tool_name} 第{pn}页失败: {result.error}")
                    break  # 失败停止翻页，继续 workflow 后续步骤

                executor.extract_tool_output(tool_name, result.data, param_pool)

                items = param_pool.get("video_list", [])
                if not items:
                    break

                all_items.extend(items)

                page_info = param_pool.get("page_info", {})
                total_count = page_info.get("count", 0)
                if pn * page_size >= total_count:
                    break

            param_pool["video_list"] = _dedup_video_list(all_items)
            logger.info(f"[Batch][{task_id}] {nickname} {tool_name} 分页采集完成，共 {len(param_pool['video_list'])} 条")

        else:
            args = executor.build_args_from_pool(tool_name, param_pool)
            if args is None:
                logger.info(f"[Batch][{task_id}] {nickname} {tool_name} 参数不足，跳过")
                continue  # 跳过该步骤，继续下一步

            result = await executor.execute_tool_call(ToolCall(tool_name=tool_name, arguments=args))
            if not result.success:
                logger.warning(f"[Batch][{task_id}] {nickname} {tool_name} 失败: {result.error}，跳过")
                continue  # 失败跳过，继续下一步

            executor.extract_tool_output(tool_name, result.data, param_pool)
            logger.info(f"[Batch][{task_id}] {nickname} {tool_name} 执行成功")

    # each_detail 处理
    if workflow.each_detail.need_query and workflow.each_detail.tool_name:
        await _query_each_detail(param_pool, workflow, task_id, nickname)

    # 构造 video_list
    video_list = param_pool.get("video_list", [])
    if not video_list:
        single = {k: v for k, v in param_pool.items() if k not in ("video_list", "page_info", "pn", "view", "tags", "participle", "card", "stat")}
        for key in ("bvid", "aid", "title", "pubdate", "desc", "dynamic", "duration", "pic", "stat"):
            if key in param_pool and param_pool[key] is not None:
                single[key] = param_pool[key]
        if single.get("bvid") or single.get("title"):
            video_list = [single]

    # 全局过滤
    filtered = _apply_global_filter(video_list, workflow_plan.global_filter)

    # 组装导出
    export_fields = workflow_plan.export_fields
    matched: list[dict] = []
    for item in filtered:
        if not isinstance(item, dict):
            continue
        record = _build_export_record(item, param_pool, export_fields, nickname)
        if record:
            matched.append(record)

    logger.info(f"[Batch][{task_id}] {nickname} 工作流执行完成，匹配 {len(matched)} 条")
    return matched


# ------------------------------------------------------------------------------
# 批量执行引擎
# ------------------------------------------------------------------------------

async def run_batch_task(
    question: str,
    creators: list[dict],
    plan: dict[str, Any],
    task_id: str = "",
) -> AsyncGenerator[str, None]:
    logger.info(f"[Batch][{task_id}] 开始批量任务，达人: {len(creators)}")

    cancel_event = asyncio.Event()
    if task_id:
        task_cancel_events[task_id] = cancel_event
        await _update_task_cache(task_id, total=len(creators), status="running")

    yield _sse_event("start", {
        "message": "开始批量抓取任务",
        "total_creators": len(creators),
        "task_id": task_id,
    })

    try:
        workflow_plan = LLMWorkflowPlan(**plan)
    except Exception as exc:
        logger.error(f"[Batch][{task_id}] 工作流规划解析失败: {exc}")
        yield _sse_event("error", {"message": f"工作流规划解析失败: {exc}"})
        yield _sse_event("done", {})
        return

    logger.info(
        f"[Batch][{task_id}] 过滤条件: {workflow_plan.global_filter.model_dump()}, "
        f"tool_sequence={[s.tool_name for s in workflow_plan.workflow.tool_sequence]}"
    )

    all_matched_videos: list[dict] = []
    semaphore = asyncio.Semaphore(settings.BATCH_CONCURRENCY)

    async def _process(creator: dict, idx: int) -> list[dict]:
        async with semaphore:
            if cancel_event.is_set():
                return []
            return await process_one_creator(creator, idx, workflow_plan, task_id)

    tasks = [asyncio.create_task(_process(c, i)) for i, c in enumerate(creators)]
    cancel_watcher = asyncio.create_task(_watch_cancel(task_id, cancel_event, tasks))

    completed = 0
    background_continued = False
    try:
        for coro in asyncio.as_completed(tasks):
            matched = await coro
            if cancel_event.is_set():
                break
            all_matched_videos.extend(matched)
            completed += 1
            if task_id:
                await _update_task_cache(
                    task_id,
                    completed=completed,
                    matched_so_far=len(all_matched_videos),
                    videos=all_matched_videos,
                )
            logger.info(f"[Batch][{task_id}] 进度: {completed}/{len(creators)}, 累计匹配: {len(all_matched_videos)}")
            yield _sse_event("progress", {
                "completed": completed,
                "total": len(creators),
                "matched_so_far": len(all_matched_videos),
            })
    except asyncio.CancelledError:
        logger.info(f"[Batch][{task_id}] SSE 连接断开，任务继续在后台运行")
        if cancel_event.is_set():
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if task_id:
                await _update_task_cache(task_id, status="cancelled")
        else:
            background_continued = True
            asyncio.ensure_future(_continue_in_background(
                tasks, task_id, all_matched_videos, completed, cancel_event, len(creators)
            ))
        return
    finally:
        if not cancel_watcher.done():
            cancel_watcher.cancel()
        try:
            await cancel_watcher
        except asyncio.CancelledError:
            pass
        # 只有在不是转移到后台继续的情况下，才在这里取消 pending tasks
        # 否则 _continue_in_background 会自己管理这些 tasks
        if not background_continued:
            pending = [t for t in tasks if not t.done()]
            if pending:
                for t in pending:
                    t.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

    if task_id:
        _cleanup_cancel_event(task_id)

    status = "cancelled" if cancel_event.is_set() else "completed"
    logger.info(f"[Batch][{task_id}] 任务结束，状态={status}, 共匹配 {len(all_matched_videos)} 条视频")

    if task_id:
        await _update_task_cache(
            task_id,
            status=status,
            completed=completed,
            matched_so_far=len(all_matched_videos),
            videos=all_matched_videos,
        )
        _schedule_task_cleanup(task_id)

    yield _sse_event("final", {
        "total_creators": len(creators),
        "matched_videos": len(all_matched_videos),
        "videos": all_matched_videos,
        "export_fields": workflow_plan.export_fields,
    })
    yield _sse_event("done", {})


def _sse_event(event: str, data: dict) -> str:
    payload = {
        "event": event,
        "content": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
