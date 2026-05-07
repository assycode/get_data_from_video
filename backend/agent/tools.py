"""
工具定义模块

从 docs/api_schema.json 动态加载接口文档，转换为 OpenAI Function Calling 所需的格式。

设计原则：
1. 接口文档完全外置（JSON 文件），替换接口文档 = 替换 JSON 文件 + 重写 api/data_apis.py。
2. 系统启动时自动加载 api_schema.json，构建 tools schema。
3. 新增/修改接口只需改 JSON，无需改动 agent 核心代码。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.schemas import ToolDefinition, ToolParameter


# ------------------------------------------------------------------------------
# Schema 加载器
# ------------------------------------------------------------------------------

# 接口文档路径（相对于 backend 目录）
SCHEMA_PATH = Path(__file__).parent.parent / "docs" / "api_schema.json"


def load_api_schema() -> dict[str, Any]:
    """加载接口文档 JSON。

    Returns:
        解析后的 dict，包含 _meta 和 tools 数组。

    Raises:
        FileNotFoundError: 如果 api_schema.json 不存在。
        json.JSONDecodeError: 如果 JSON 格式错误。
    """
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def build_tools_from_schema(schema: dict[str, Any] | None = None) -> list[ToolDefinition]:
    """将接口文档中的 tools 数组转换为内部 ToolDefinition 列表。

    Args:
        schema: 已加载的 api_schema dict；为 None 时自动从文件加载。

    Returns:
        ToolDefinition 列表。
    """
    if schema is None:
        schema = load_api_schema()

    tools: list[ToolDefinition] = []
    for tool in schema.get("tools", []):
        params = []
        for p in tool.get("parameters", []):
            params.append(
                ToolParameter(
                    name=p["name"],
                    type=p["type"],
                    description=p["description"],
                    required=p.get("required", True),
                    enum=p.get("enum"),
                )
            )
        tools.append(
            ToolDefinition(
                name=tool["name"],
                description=tool["description"],
                parameters=params,
            )
        )
    return tools


# ------------------------------------------------------------------------------
# OpenAI Function Calling 格式转换器
# ------------------------------------------------------------------------------


def build_openai_functions(schema: dict[str, Any] | None = None) -> list[dict]:
    """将接口文档转换为 OpenAI API 要求的 functions 格式。

    OpenAI 格式：
        {
            "type": "function",
            "function": {
                "name": "get_video_list",
                "description": "...",
                "parameters": {
                    "type": "object",
                    "properties": {...},
                    "required": [...]
                }
            }
        }

    Args:
        schema: 已加载的 api_schema dict；为 None 时自动加载。

    Returns:
        可直接传入 openai.chat.completions.create(..., tools=...) 的列表。
    """
    if schema is None:
        schema = load_api_schema()

    openai_tools = []
    for tool in schema.get("tools", []):
        properties = {}
        required_params = []
        for p in tool.get("parameters", []):
            prop = {"type": p["type"], "description": p["description"]}
            if p.get("enum") is not None:
                prop["enum"] = p["enum"]
            properties[p["name"]] = prop
            if p.get("required", True):
                required_params.append(p["name"])

        openai_tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required_params,
                    },
                },
            }
        )
    return openai_tools


# ------------------------------------------------------------------------------
# 工具名列表
# ------------------------------------------------------------------------------


def get_tool_names(schema: dict[str, Any] | None = None) -> list[str]:
    """返回所有已注册工具的名称列表。"""
    if schema is None:
        schema = load_api_schema()
    return [t["name"] for t in schema.get("tools", [])]
