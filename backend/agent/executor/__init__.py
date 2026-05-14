"""
工具执行器包（executor package）。

对外统一入口。所有原有导入路径保持不变：
    from agent.executor import execute_tool_call, build_args_from_pool, ...
"""
from __future__ import annotations

# 数据提取辅助
from .extractors import (
    _safe_get,
    _extract_vlist,
    _extract_page_info,
    _extract_video_detail,
    _extract_timestamp,
    extract_tool_output,
    TOOL_OUTPUT_EXTRACTORS,
)

# 工具注册
from .registry import (
    TOOL_REGISTRY,
    TOOL_META,
    PARAM_ALIASES,
    get_tool_names,
    build_tools_prompt,
    build_args_from_pool,
)

# 核心执行
from .core import execute_tool_call

__all__ = [
    # 提取辅助
    "_safe_get",
    "_extract_vlist",
    "_extract_page_info",
    "_extract_video_detail",
    "_extract_timestamp",
    "extract_tool_output",
    "TOOL_OUTPUT_EXTRACTORS",
    # 注册
    "TOOL_REGISTRY",
    "TOOL_META",
    "PARAM_ALIASES",
    "get_tool_names",
    "build_tools_prompt",
    "build_args_from_pool",
    # 核心
    "execute_tool_call",
]
