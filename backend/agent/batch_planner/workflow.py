"""
单达人工作流执行模块。

负责根据 creator 的 platform 匹配对应工作流，
按 tool_sequence 顺序执行工具、分页采集、逐条查详情、过滤、组装导出。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from agent.executor import (
    execute_tool_call,
    build_args_from_pool,
    extract_tool_output,
    get_tool_names,
)
from models.schemas import ToolCall, LLMWorkflowPlan

from .cache import task_cancel_events
from .filters import _dedup_video_list, _apply_global_filter, _build_export_record

logger = logging.getLogger(__name__)


# 详情查询并发控制
_EACH_DETAIL_CONCURRENCY = 2  # 同时查询 2 条视频（降低并发避免限流）
_EACH_DETAIL_DELAY = 0.5  # 每条视频查询间隔 0.5 秒


# ------------------------------------------------------------------------------
# 逐条查详情
# ------------------------------------------------------------------------------


async def _fetch_single_detail(
    item: dict,
    idx: int,
    detail_tool: str,
    param_pool: dict[str, Any],
    task_id: str,
    nickname: str,
) -> dict:
    """查询单条视频的详情，用于并发控制。"""
    if not isinstance(item, dict):
        return item

    # 检查取消状态
    if task_id and task_id in task_cancel_events and task_cancel_events[task_id].is_set():
        return item

    # 根据平台设置当前视频的标识字段
    local_pool = dict(param_pool)  # 复制一份，避免并发冲突
    bvid = item.get("bvid")
    if bvid:
        local_pool["bvid"] = bvid
    aweme_id = item.get("aweme_id")
    if aweme_id:
        local_pool["aweme_id"] = aweme_id
    # 小红书 note_id（列表返回的是 noteId，需要映射为 note_id）
    note_id = item.get("note_id") or item.get("noteId")
    if note_id:
        local_pool["note_id"] = note_id
    # 快手 photo_id
    photo_id = item.get("photo_id")
    if photo_id:
        local_pool["photo_id"] = photo_id

    args = build_args_from_pool(detail_tool, local_pool)
    if args is None:
        logger.warning(f"[Batch][{task_id}] {nickname} 第{idx}条视频参数不足，跳过详情查询")
        return item

    logger.debug(f"[Batch][{task_id}] {nickname} 第{idx}条视频调用 {detail_tool}")
    import time
    start_time = time.time()
    result = await execute_tool_call(ToolCall(tool_name=detail_tool, arguments=args))
    elapsed = time.time() - start_time
    logger.debug(f"[Batch][{task_id}] {nickname} 第{idx}条视频 {detail_tool} 调用完成，耗时{elapsed:.2f}秒")
    
    if not result.success:
        logger.warning(f"[Batch][{task_id}] {nickname} 第{idx}条视频详情查询失败: {result.error}")
        return item

    # 提取详情数据
    extract_tool_output(detail_tool, result.data, local_pool)

    # 合并数据
    merged = dict(item)

    # B站 View 对象合并
    view = local_pool.get("view", {})
    if view and isinstance(view, dict):
        for key in ("title", "pubdate", "duration", "desc", "dynamic", "pic", "bvid", "aid"):
            val = view.get(key)
            if val is not None and val != "":
                merged[key] = val
        stat = view.get("stat")
        if isinstance(stat, dict) and stat:
            merged["stat"] = stat
            for stat_key in ("view", "danmaku", "reply", "favorite", "coin", "share", "like"):
                if stat_key in stat:
                    merged[stat_key] = stat[stat_key]
        owner = view.get("owner")
        if isinstance(owner, dict) and owner:
            if owner.get("mid"):
                merged["owner_mid"] = owner["mid"]
            if owner.get("name"):
                merged["owner_name"] = owner["name"]

    # B站 tags / participle
    tags = local_pool.get("tags", [])
    if tags and isinstance(tags, list):
        merged["tags"] = tags
    participle = local_pool.get("participle", [])
    if participle and isinstance(participle, list):
        merged["participle"] = participle

    # 抖音详情合并
    statistics = local_pool.get("statistics")
    if isinstance(statistics, dict) and statistics:
        merged["statistics"] = statistics
        for skey in ("play_count", "digg_count", "comment_count", "share_count"):
            if skey in statistics:
                merged[skey] = statistics[skey]
    text_extra = local_pool.get("text_extra")
    if isinstance(text_extra, list) and text_extra:
        merged["text_extra"] = text_extra
    author = local_pool.get("author")
    if isinstance(author, dict) and author:
        merged["author"] = author
        if author.get("uid"):
            merged["author_uid"] = author["uid"]
        if author.get("nickname"):
            merged["author_nickname"] = author["nickname"]
        if author.get("unique_id"):
            merged["author_unique_id"] = author["unique_id"]
    share_url = local_pool.get("share_url")
    if share_url:
        merged["share_url"] = share_url
    duration = local_pool.get("duration")
    if duration is not None:
        merged["duration"] = duration

    # 小红书详情合并
    content_tags = local_pool.get("contentTags")
    if isinstance(content_tags, list) and content_tags:
        merged["contentTags"] = content_tags
    note_title = local_pool.get("title")
    if note_title:
        merged["title"] = note_title
    note_content = local_pool.get("content")
    if note_content:
        merged["content"] = note_content
        # 合并 content 到 desc 用于话题过滤
        merged["desc"] = note_content
    # 小红书统计字段
    for skey in ("like_num", "fav_num", "cmt_num", "read_num", "share_num", "follow_cnt"):
        val = local_pool.get(skey)
        if val is not None:
            merged[skey] = val

    # 快手详情合并
    ks_title = local_pool.get("title")
    if ks_title:
        merged["title"] = ks_title
    ks_caption = local_pool.get("caption")
    if ks_caption:
        merged["caption"] = ks_caption
        merged["desc"] = ks_caption  # 合并 caption 到 desc 用于话题过滤
    ks_tags = local_pool.get("tags")
    if isinstance(ks_tags, list) and ks_tags:
        merged["tags"] = ks_tags
    # 快手统计字段
    for ks_key in ("view_count", "like_count", "comment_count"):
        val = local_pool.get(ks_key)
        if val is not None:
            merged[ks_key] = val
    ks_create_time = local_pool.get("create_time")
    if ks_create_time:
        merged["create_time"] = ks_create_time

    return merged


async def _query_each_detail(
    param_pool: dict[str, Any],
    workflow: Any,
    task_id: str,
    nickname: str,
) -> None:
    """对 video_list 中每条记录调用详情工具（支持并发）。

    合并策略：get_video_detail 返回的 View 对象比 get_video_list 更完整，
    因此 View 中的字段优先覆盖 item 中的同名字段（但 item 中已有的有效值保留作为 fallback）。
    同时把 View 对象中的 stat（播放量/点赞/评论等统计）和 tags/participle 一并合并。
    """
    detail_tool = workflow.each_detail.tool_name
    video_list = param_pool.get("video_list", [])

    if not video_list or detail_tool not in get_tool_names():
        return

    total = len(video_list)
    logger.info(f"[Batch][{task_id}] {nickname} 开始 each_detail，共 {total} 条视频需要查详情，并发数={_EACH_DETAIL_CONCURRENCY}")

    # 使用信号量控制并发
    semaphore = asyncio.Semaphore(_EACH_DETAIL_CONCURRENCY)

    async def _fetch_with_limit(item: dict, idx: int) -> dict:
        async with semaphore:
            # 添加延迟避免触发 API 限流
            if _EACH_DETAIL_DELAY > 0:
                await asyncio.sleep(_EACH_DETAIL_DELAY)
            return await _fetch_single_detail(item, idx, detail_tool, param_pool, task_id, nickname)

    # 并发执行所有详情查询
    tasks = [_fetch_with_limit(item, idx) for idx, item in enumerate(video_list)]
    detailed = await asyncio.gather(*tasks, return_exceptions=True)

    # 处理异常结果
    final_results: list[dict] = []
    for idx, result in enumerate(detailed):
        if isinstance(result, Exception):
            logger.error(f"[Batch][{task_id}] {nickname} 第{idx}条视频详情查询异常: {result}")
            final_results.append(video_list[idx])  # 使用原始数据
        else:
            final_results.append(result)

    logger.info(f"[Batch][{task_id}] {nickname} each_detail 完成，成功 {len([r for r in detailed if not isinstance(r, Exception)])}/{total}")
    param_pool["video_list"] = final_results


# ------------------------------------------------------------------------------
# 单达人工作流执行
# ------------------------------------------------------------------------------


async def process_one_creator(
    creator: dict,
    idx: int,
    workflow_plan: LLMWorkflowPlan,
    task_id: str = "",
) -> list[dict]:
    """通用工作流解释器：根据 creator 的 platform 自动匹配对应 workflow，参数不足/失败时跳过继续。

    核心流程：
    1. 根据 creator['platform'] 从 workflow_plan.workflows 中匹配对应平台的工作流
    2. 初始化 param_pool（从 creator 自带字段填充）
    3. 按 workflow.tool_sequence 顺序逐步执行工具
    4. 参数不足 → 跳过该步骤，继续下一步
    5. API 调用失败 → 记日志，跳过该步骤，继续下一步
    6. 最后一步若 page_rule.enable_page=true，自动翻页采集
    7. 若 each_detail.need_query=true，对列表逐条查详情
    8. 按 global_filter 过滤
    9. 按 export_fields 组装最终记录
    """
    nickname = creator.get("nickname", "未知")
    platform = creator.get("platform", "unknown")

    # 多平台匹配：根据 creator 的 platform 字段获取对应工作流
    workflows = workflow_plan.workflows or {}
    workflow = workflows.get(platform)
    if workflow is None:
        logger.warning(
            f"[Batch][{task_id}] {nickname} (platform={platform}) 在 workflows 中没有对应的工作流，"
            f"可用平台={list(workflows.keys())}，跳过"
        )
        return []

    logger.info(f"[Batch][{task_id}] {nickname} 匹配到 {platform} 平台工作流，tool_sequence={[s.tool_name for s in workflow.tool_sequence]}")
    
    # 兜底：如果用户指定了 topic 过滤，但 LLM 没有设置 each_detail，自动修正
    if workflow_plan.global_filter.topic and not workflow.each_detail.need_query:
        logger.warning(f"[Batch][{task_id}] {nickname} 检测到话题过滤需求但 each_detail.need_query=false，自动修正为 true")
        workflow.each_detail.need_query = True
        # 根据平台设置默认的详情工具
        if platform == "bilibili" and not workflow.each_detail.tool_name:
            workflow.each_detail.tool_name = "get_video_detail"
        elif platform == "douyin" and not workflow.each_detail.tool_name:
            workflow.each_detail.tool_name = "get_douyin_video_detail"
        elif platform == "kuaishou" and not workflow.each_detail.tool_name:
            workflow.each_detail.tool_name = "get_ks_video_detail"
    
    logger.info(f"[Batch][{task_id}] {nickname} each_detail: need_query={workflow.each_detail.need_query}, tool_name={workflow.each_detail.tool_name}")

    # 初始化参数池（多平台字段）
    param_pool: dict[str, Any] = {
        "upper_mid": creator.get("upper_mid"),
        "bvid": creator.get("bvid"),
        "avid": creator.get("avid"),
        "short_code": creator.get("short_code"),
        "nickname": nickname,
        "link_type": creator.get("link_type", "unknown"),
        "pn": 1,
        # 抖音字段
        "sec_uid": creator.get("sec_uid"),
        "aweme_id": creator.get("aweme_id"),
        "uid": creator.get("uid"),
        # 小红书字段
        "user_id": creator.get("user_id"),
        "note_id": creator.get("note_id"),
        # 快手字段
        "ks_uid": creator.get("ks_uid") or creator.get("uid"),
        "photo_id": creator.get("photo_id"),
    }
    logger.info(f"[Batch][{task_id}] {nickname} 初始 param_pool: user_id={param_pool.get('user_id')}, note_id={param_pool.get('note_id')}, aweme_id={param_pool.get('aweme_id')}, sec_uid={param_pool.get('sec_uid')}, uid={param_pool.get('uid')}")

    # 兜底：如果 param_pool 里有 short_code 但没有 bvid，且 tool_sequence 中没有 resolve_short_url，
    # 自动在最前面执行 resolve_short_url，防止 LLM 漏编排导致所有短链接参数不足
    if (
        param_pool.get("short_code")
        and not param_pool.get("bvid")
        and not any(s.tool_name == "resolve_short_url" for s in workflow.tool_sequence)
    ):
        logger.info(f"[Batch][{task_id}] {nickname} 检测到短链接但未编排 resolve_short_url，自动执行")
        args = build_args_from_pool("resolve_short_url", param_pool)
        if args:
            result = await execute_tool_call(ToolCall(tool_name="resolve_short_url", arguments=args))
            if result.success:
                extract_tool_output("resolve_short_url", result.data, param_pool)
                logger.info(f"[Batch][{task_id}] {nickname} 短链接解析成功: bvid={param_pool.get('bvid')}, mid={param_pool.get('upper_mid')}")
            else:
                logger.warning(f"[Batch][{task_id}] {nickname} 短链接解析失败: {result.error}")

    logger.info(f"[Batch][{task_id}] {nickname} 开始执行工作流")

    # 按 tool_sequence 顺序执行（参数不足或失败时跳过，继续下一步）
    for step_idx, step in enumerate(workflow.tool_sequence):
        tool_name = step.tool_name

        if task_id and task_id in task_cancel_events and task_cancel_events[task_id].is_set():
            break

        if tool_name not in get_tool_names():
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
                args = build_args_from_pool(tool_name, param_pool)
                if args is None:
                    logger.info(f"[Batch][{task_id}] {nickname} {tool_name} 参数不足，跳过翻页")
                    break  # 参数不足，停止翻页（但继续 workflow 后续步骤）

                result = await execute_tool_call(ToolCall(tool_name=tool_name, arguments=args))
                if not result.success:
                    logger.warning(f"[Batch][{task_id}] {nickname} {tool_name} 第{pn}页失败: {result.error}")
                    break  # 失败停止翻页，继续 workflow 后续步骤

                # 调试：提取前查看 param_pool
                logger.info(f"[Batch][{task_id}] {nickname} {tool_name} 提取前 video_list 长度={len(param_pool.get('video_list', []))}")
                extract_tool_output(tool_name, result.data, param_pool)
                # 调试：查看提取后的 param_pool
                logger.info(f"[Batch][{task_id}] {nickname} {tool_name} 提取后 video_list 长度={len(param_pool.get('video_list', []))}")
                
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
            args = build_args_from_pool(tool_name, param_pool)
            if args is None:
                logger.info(f"[Batch][{task_id}] {nickname} {tool_name} 参数不足，跳过")
                continue  # 跳过该步骤，继续下一步

            result = await execute_tool_call(ToolCall(tool_name=tool_name, arguments=args))
            if not result.success:
                logger.warning(f"[Batch][{task_id}] {nickname} {tool_name} 失败: {result.error}，跳过")
                continue  # 失败跳过，继续下一步

            extract_tool_output(tool_name, result.data, param_pool)
            video_list_len = len(param_pool.get("video_list", []))
            logger.info(f"[Batch][{task_id}] {nickname} {tool_name} 执行成功，当前 video_list 长度: {video_list_len}")
            # 调试：打印 result.data 的结构
            if isinstance(result.data, dict):
                logger.info(f"[Batch][{task_id}] {nickname} {tool_name} result.data.keys={list(result.data.keys())}")
            elif isinstance(result.data, list):
                logger.info(f"[Batch][{task_id}] {nickname} {tool_name} result.data 是 list，长度={len(result.data)}")

    # each_detail 处理
    logger.debug(f"[Batch][{task_id}] {nickname} 检查 each_detail: need_query={workflow.each_detail.need_query}, tool_name={workflow.each_detail.tool_name}")
    if workflow.each_detail.need_query and workflow.each_detail.tool_name:
        logger.info(f"[Batch][{task_id}] {nickname} 开始执行 each_detail，工具: {workflow.each_detail.tool_name}")
        await _query_each_detail(param_pool, workflow, task_id, nickname)
        video_list_len = len(param_pool.get("video_list", []))
        logger.info(f"[Batch][{task_id}] {nickname} each_detail 完成，video_list 长度: {video_list_len}")
    else:
        logger.info(f"[Batch][{task_id}] {nickname} 跳过 each_detail (need_query={workflow.each_detail.need_query})")

    # 构造 video_list
    video_list = param_pool.get("video_list", [])
    if not video_list:
        single = {k: v for k, v in param_pool.items() if k not in ("video_list", "page_info", "pn", "view", "tags", "participle", "card", "stat", "statistics", "text_extra", "author")}
        for key in ("bvid", "aid", "title", "pubdate", "desc", "dynamic", "duration", "pic", "stat",
                    "aweme_id", "share_url", "statistics", "text_extra", "author"):
            if key in param_pool and param_pool[key] is not None:
                single[key] = param_pool[key]
        if single.get("bvid") or single.get("title") or single.get("aweme_id") or single.get("desc"):
            video_list = [single]

    # 全局过滤
    logger.info(f"[Batch][{task_id}] {nickname} 全局过滤前视频数: {len(video_list)}, topic={workflow_plan.global_filter.topic}")
    
    # 打印前几条视频的话题信息（用于调试）
    for i, v in enumerate(video_list[:3]):
        text_extra = v.get("text_extra", [])
        hashtags = [t.get("hashtag_name", "") for t in text_extra if isinstance(t, dict)]
        logger.debug(f"[Batch][{task_id}] {nickname} 视频{i}: aweme_id={v.get('aweme_id')}, desc={v.get('desc', '')[:50]}..., hashtags={hashtags}")
    
    filtered = _apply_global_filter(video_list, workflow_plan.global_filter)
    logger.info(f"[Batch][{task_id}] {nickname} 全局过滤后视频数: {len(filtered)}")

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
