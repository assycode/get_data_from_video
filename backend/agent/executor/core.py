"""
工具执行核心调度层。

唯一对外入口：execute_tool_call(tool_call) → ToolResult。
负责参数校验、类型转换、实际调用、错误处理、结果截断。
"""
from __future__ import annotations

import logging

from pydantic import ValidationError

from models.schemas import ToolCall, ToolResult

from .extractors import extract_tool_output
from .registry import TOOL_REGISTRY
from .trim import _trim_result

logger = logging.getLogger(__name__)


async def execute_tool_call(tool_call: ToolCall) -> ToolResult:
    """执行单个工具调用，返回标准化结果。

    执行链路：
        1. 校验工具名是否在注册中心
        2. Pydantic 参数校验（类型、必填字段）
        3. 参数类型转换（LLM 有时把 int 传成 string）
        4. 执行函数
        5. 接口错误结构检测
        6. 结果截断（避免超长返回撑爆上下文）

    Args:
        tool_call: LLM 生成的调用指令，包含 tool_name 和 arguments。

    Returns:
        ToolResult：始终返回结构化对象，不会抛出异常。
                     success=False 时，error 字段携带失败原因。
    """
    tool_name = tool_call.tool_name
    arguments = tool_call.arguments

    # 1. 校验工具是否存在
    entry = TOOL_REGISTRY.get(tool_name)
    if entry is None:
        available = ", ".join(TOOL_REGISTRY.keys())
        return ToolResult(
            tool_name=tool_name,
            success=False,
            error=f"未知工具 '{tool_name}'。可用工具：{available}",
        )

    func = entry["func"]
    args_model = entry["args_model"]

    # 2. 参数类型转换（在 Pydantic 校验前先做常见类型修复）
    converted_args = _convert_argument_types(tool_name, arguments)

    # 3. Pydantic 参数校验
    try:
        validated = args_model(**converted_args)
        validated_args = validated.model_dump()
    except ValidationError as exc:
        errors = "; ".join(
            f"{e['loc']}: {e['msg']}" for e in exc.errors()
        )
        return ToolResult(
            tool_name=tool_name,
            success=False,
            error=f"参数校验失败：{errors}",
        )
    except Exception as exc:
        return ToolResult(
            tool_name=tool_name,
            success=False,
            error=f"参数处理异常：{type(exc).__name__}: {exc}",
        )

    # 4. 执行调用（data_apis.py 中的函数均为 async）
    logger.info(f"[ToolExecute] 调用工具: {tool_name} | 参数: {validated_args}")
    try:
        raw_data = await func(**validated_args)
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

    # 5. 如果接口本身返回了错误结构（如 {"error": "..."}）
    if isinstance(raw_data, dict) and "error" in raw_data:
        return ToolResult(
            tool_name=tool_name,
            success=False,
            error=raw_data.get("error", "接口返回错误"),
            data=raw_data.get("detail") or raw_data.get("raw"),
        )

    # 6. 后处理：截断过长结果
    # 关键修复：dict 是 API 结构化响应，截断会破坏 _extract_vlist / _extract_page_info 等提取函数。
    # 只对 list 做截断；dict 保持原样。
    if isinstance(raw_data, list):
        trimmed_data = _trim_result(raw_data)
    else:
        trimmed_data = raw_data

    return ToolResult(
        tool_name=tool_name,
        success=True,
        data=trimmed_data,
    )


def _convert_argument_types(tool_name: str, arguments: dict) -> dict:
    """根据常见参数名进行类型转换，减少 LLM 传参类型错误。

    例如：LLM 可能把 upper_mid=472954189 传成 upper_mid="472954189"，
    这里自动识别并转为 int。
    """
    converted = dict(arguments)
    # upper_mid / pn / count / limit / cursor 等应转为 int
    int_fields = ["upper_mid", "pn", "count", "limit", "page", "ps", "cursor"]
    for field in int_fields:
        if field in converted and not isinstance(converted[field], int):
            try:
                converted[field] = int(converted[field])
            except (ValueError, TypeError):
                pass
    return converted
