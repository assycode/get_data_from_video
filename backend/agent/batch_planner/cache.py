"""
任务状态缓存与生命周期管理。

负责维护任务缓存、取消控制、并发锁、TTL 自动清理。
所有与任务状态存储相关的逻辑集中在此模块。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# 全局状态
# ------------------------------------------------------------------------------

task_cache: dict[str, dict[str, Any]] = {}
task_cancel_events: dict[str, asyncio.Event] = {}
task_locks: dict[str, asyncio.Lock] = {}

MAX_CACHE_TASKS = 100
CACHE_TTL_SECONDS = 300


# ------------------------------------------------------------------------------
# 基础操作
# ------------------------------------------------------------------------------


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


# ------------------------------------------------------------------------------
# 后台延续（SSE 断开后继续执行）
# ------------------------------------------------------------------------------


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
