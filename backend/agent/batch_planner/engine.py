"""
批量并发引擎。

负责并发调度多个达人的工作流执行、SSE 流式输出、
取消控制、以及 SSE 断开后的后台延续。
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from config import settings
from models.schemas import LLMWorkflowPlan

from .cache import (
    task_cancel_events,
    _update_task_cache,
    _cleanup_cancel_event,
    _schedule_task_cleanup,
    _watch_cancel,
    _continue_in_background,
)
from .workflow import process_one_creator

logger = logging.getLogger(__name__)


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

    # 日志：输出每个平台的工作流
    wf_summary = []
    for plat, wf in (workflow_plan.workflows or {}).items():
        wf_summary.append(f"{plat}: {[s.tool_name for s in wf.tool_sequence]}")
    logger.info(
        f"[Batch][{task_id}] 过滤条件: {workflow_plan.global_filter.model_dump()}, "
        f"workflows={' | '.join(wf_summary)}"
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
