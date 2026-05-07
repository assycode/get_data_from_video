"""
Pydantic 数据模型定义

本模块负责声明所有进出接口的数据结构，FastAPI 会自动基于这些模型
生成请求校验、序列化及 Swagger 文档。
"""

from typing import Any

from pydantic import BaseModel, Field


# =============================================================================
# 通用基类
# =============================================================================

class BaseResponse(BaseModel):
    """统一响应基类，便于前端做标准化处理。"""

    code: int = Field(default=0, description="业务状态码：0 表示成功，非 0 表示异常")
    message: str = Field(default="success", description="人类可读的状态描述")
    data: Any = Field(default=None, description="实际业务数据")


# =============================================================================
# Chat / Agent 流式模块
# =============================================================================

class ChatRequest(BaseModel):
    """用户发起对话的请求体。"""

    question: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="用户输入的自然语言需求，例如：查一下这些达人发布的带星布谷地话题的视频",
    )
    session_id: str | None = Field(
        default=None,
        description="会话 ID，用于多轮对话上下文关联；首次请求可不传",
    )


class PlanTaskRequest(BaseModel):
    """LLM 接口选型请求体（同步接口，不携带达人列表）。"""

    question: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="用户的抓取需求描述",
    )
    topic: str | None = Field(
        default=None,
        description="话题关键词兜底，如 '星布谷地'",
    )
    start_date: str | None = Field(
        default=None,
        description="开始日期兜底，格式 YYYY-MM-DD，如 '2026-04-21'",
    )


class BatchTaskRequest(BaseModel):
    """批量任务请求体（携带 Excel 解析结果）。"""

    question: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="用户的抓取需求描述",
    )
    creators: list[dict[str, Any]] = Field(
        ...,
        description="从 Excel 解析出的达人列表，每项含 nickname / upper_mid / space_url",
    )
    filters: dict[str, Any] | None = Field(
        default=None,
        description="额外过滤条件，如 {\"topic\": \"星布谷地\", \"start_date\": \"2026-04-21\"}",
    )


class ChatStreamEvent(BaseModel):
    """SSE 流式事件的标准格式。

    前端通过 event 字段区分消息类型，按顺序渲染即可。
    """

    event: str = Field(
        ...,
        description="事件类型：start | thought | tool_call | tool_result | progress | final | error | done",
    )
    content: Any = Field(default=None, description="事件载荷，随 event 类型变化")
    timestamp: str | None = Field(default=None, description="ISO 格式时间戳，便于前端排序")


# =============================================================================
# Agent 内部模型
# =============================================================================

class ToolParameter(BaseModel):
    """单个工具参数的 Schema 描述，遵循 JSON Schema 子集。"""

    name: str = Field(..., description="参数名")
    type: str = Field(..., description="参数类型：string / integer / number / boolean / array / object")
    description: str = Field(..., description="参数含义与取值说明")
    required: bool = Field(default=True, description="是否必填")
    enum: list[Any] | None = Field(default=None, description="枚举值")


class ToolDefinition(BaseModel):
    """单个工具（数据接口）的完整定义。"""

    name: str = Field(..., description="工具唯一标识，使用 snake_case")
    description: str = Field(..., description="工具功能描述，直接决定 LLM 的选型准确率")
    parameters: list[ToolParameter] = Field(default_factory=list, description="参数列表")


class ToolCall(BaseModel):
    """LLM 决定调用某个工具时生成的调用指令。"""

    tool_name: str = Field(..., description="被调用工具的名称")
    arguments: dict[str, Any] = Field(default_factory=dict, description="解析后的参数键值对")


class ToolResult(BaseModel):
    """工具执行后的结果，将被回传给 LLM 以支撑后续推理。"""

    tool_name: str = Field(..., description="执行的是哪个工具")
    success: bool = Field(..., description="是否执行成功")
    data: Any = Field(default=None, description="成功时的返回数据")
    error: str | None = Field(default=None, description="失败时的错误信息")


# =============================================================================
# Excel 上传模块
# =============================================================================

class ExcelParseResult(BaseModel):
    """Excel 解析结果。"""

    total: int = Field(..., description="成功解析的达人数")
    creators: list[dict[str, Any]] = Field(..., description="达人列表")
    skipped: int = Field(default=0, description="无法解析 mid 而被跳过的行数")
