"""
批量任务规划器包（batch_planner package）。

对外统一入口。所有原有导入路径保持不变：
    from agent.batch_planner import generate_plan, run_batch_task, get_task_status, cancel_task
"""
from __future__ import annotations

# 任务缓存与生命周期
from .cache import (
    task_cache,
    get_task_status,
    cancel_task,
    _update_task_cache,
    _get_task_lock,
    _schedule_task_cleanup,
)

# LLM 规划
from .llm import generate_plan

# 批量并发引擎
from .engine import run_batch_task

# 单达人工作流（如需外部直接调用）
from .workflow import process_one_creator

__all__ = [
    "task_cache",
    "get_task_status",
    "cancel_task",
    "_update_task_cache",
    "_get_task_lock",
    "_schedule_task_cleanup",
    "generate_plan",
    "run_batch_task",
    "process_one_creator",
]
