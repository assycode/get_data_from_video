"""
工具执行器模块

负责将 LLM 生成的 tool_call 映射到实际的数据接口函数并执行。
通过 api_schema.json 中的 tool.name 与 api/data_apis.py 中 API_REGISTRY 的 key 做映射。

执行流程：
    tool_call (name + arguments)
        │
        ▼
    从 API_REGISTRY 查找对应异步函数
        │
        ▼
    执行函数（await），拿到原始数据
        │
        ▼
    截断超长结果、包装为 ToolResult
        │
        ▼
    回传给 Planner
"""

from __future__ import annotations

import json

from config import settings
from models.schemas import ToolCall, ToolResult

# 引入真实数据接口注册表
from api.data_apis import API_REGISTRY


# ------------------------------------------------------------------------------
# 主执行入口
# ------------------------------------------------------------------------------


async def execute_tool_call(tool_call: ToolCall) -> ToolResult:
    """执行单个工具调用，返回标准化结果。

    Args:
        tool_call: LLM 生成的调用指令，包含 tool_name 和 arguments。

    Returns:
        ToolResult：始终返回结构化对象，不会抛出异常。
                     success=False 时，error 字段携带失败原因。
    """
    tool_name = tool_call.tool_name
    arguments = tool_call.arguments

    # 1. 校验工具是否存在
    func = API_REGISTRY.get(tool_name)
    if func is None:
        available = ", ".join(API_REGISTRY.keys())
        return ToolResult(
            tool_name=tool_name,
            success=False,
            error=f"未知工具 '{tool_name}'。可用工具：{available}",
        )

    # 2. 参数类型转换（LLM 有时会把 int 参数传成 string）
    converted_args = _convert_argument_types(tool_name, arguments)

    # 3. 执行调用（data_apis.py 中的函数均为 async）
    try:
        raw_data = await func(**converted_args)
    except TypeError as exc:
        return ToolResult(
            tool_name=tool_name,
            success=False,
            error=f"参数错误：{exc}",
        )
    except Exception as exc:
        return ToolResult(
            tool_name=tool_name,
            success=False,
            error=f"执行异常：{type(exc).__name__}: {exc}",
        )

    # 4. 如果接口本身返回了错误结构（如 {"error": "..."}）
    if isinstance(raw_data, dict) and "error" in raw_data:
        return ToolResult(
            tool_name=tool_name,
            success=False,
            error=raw_data.get("error", "接口返回错误"),
            data=raw_data.get("detail") or raw_data.get("raw"),
        )

    # 5. 后处理：截断过长结果
    trimmed_data = _trim_result(raw_data)

    return ToolResult(
        tool_name=tool_name,
        success=True,
        data=trimmed_data,
    )


# ------------------------------------------------------------------------------
# 参数类型转换
# ------------------------------------------------------------------------------


def _convert_argument_types(tool_name: str, arguments: dict) -> dict:
    """根据常见参数名进行类型转换，减少 LLM 传参类型错误。

    例如：LLM 可能把 upper_mid=472954189 传成 upper_mid="472954189"，
    这里自动识别并转为 int。
    """
    converted = dict(arguments)
    # upper_mid / pn / count / limit 等应转为 int
    int_fields = ["upper_mid", "pn", "count", "limit", "page", "ps"]
    for field in int_fields:
        if field in converted and not isinstance(converted[field], int):
            try:
                converted[field] = int(converted[field])
            except (ValueError, TypeError):
                pass
    return converted


# ------------------------------------------------------------------------------
# 结果截断
# ------------------------------------------------------------------------------


def _trim_result(data, max_length: int | None = None) -> dict | list | str:
    """对工具返回结果进行截断，确保不会超过 LLM 上下文承载能力。

    策略：
    - 若为 list 且超长，保留头部 + 尾部 + 省略提示。
    - 若为 dict 且序列化后超长，整体转为字符串后截断。
    """
    limit = max_length or settings.MAX_TOOL_RESULT_LENGTH

    try:
        json_str = json.dumps(data, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        json_str = str(data)

    if len(json_str) <= limit:
        return data

    # list 类型做智能截断
    if isinstance(data, list) and len(data) > 2:
        head_count = max(1, len(data) // 4)
        tail_count = max(1, len(data) // 4)
        trimmed = (
            data[:head_count]
            + [{"_note": f"中间省略 {len(data) - head_count - tail_count} 条数据，共 {len(data)} 条"}]
            + data[-tail_count:]
        )
        trimmed_str = json.dumps(trimmed, ensure_ascii=False, default=str)
        if len(trimmed_str) <= limit:
            return trimmed

    # 兜底：字符串截断
    truncated = json_str[:limit]
    truncated = truncated.rsplit("}", 1)[0] + "}"
    return {
        "_truncated": True,
        "_note": f"结果超长已截断，原长度 {len(json_str)} 字符",
        "preview": truncated,
    }
