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
    """LLM 接口选型请求体（同步接口，可携带达人列表）。"""

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
    creators: list[dict[str, Any]] | None = Field(
        default=None,
        description="从 Excel 解析出的达人列表，用于让 LLM 做更精准的接口选型",
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
# 工作流规划模型（通用工作流解释器架构）
# =============================================================================

class GlobalFilter(BaseModel):
    """全局过滤条件。"""

    topic: str = Field(default="", description="话题关键词，没有就留空字符串")
    start_date: str = Field(default="", description="开始日期，格式 YYYY-MM-DD")
    end_date: str = Field(default="", description="结束日期，格式 YYYY-MM-DD")


class PageRule(BaseModel):
    """分页采集规则。"""

    enable_page: bool = Field(default=False, description="是否启用分页采集")
    max_page: int = Field(default=1, description="最大翻页数")
    page_size: int = Field(default=50, description="每页条数（用于判断是否翻页结束）")


class ToolStep(BaseModel):
    """工作流中的单个工具调用步骤。"""

    tool_name: str = Field(..., description="工具名称，必须在可用工具白名单中")
    reason: str = Field(default="", description="为什么需要这步，用一句话说明")


class EachDetailRule(BaseModel):
    """逐条查详情规则。"""

    need_query: bool = Field(default=False, description="是否需要对列表中每条记录逐条查详情")
    tool_name: str = Field(default="", description="详情查询工具名，如 get_video_detail")


class Workflow(BaseModel):
    """LLM 编排的单一工作流定义。所有 creator 都执行同一套 workflow。"""

    tool_sequence: list[ToolStep] = Field(default_factory=list, description="工具调用顺序列表")
    page_rule: PageRule = Field(default_factory=PageRule, description="分页规则（仅对最后一步返回列表的工具生效）")
    each_detail: EachDetailRule = Field(default_factory=EachDetailRule, description="逐条详情规则")


class LLMWorkflowPlan(BaseModel):
    """LLM 一次性输出的完整工作流规划。"""

    global_filter: GlobalFilter = Field(default_factory=GlobalFilter, description="全局过滤条件")
    export_fields: list[str] = Field(default_factory=list, description="最终需要导出的字段列表")
    workflow: Workflow = Field(default_factory=Workflow, description="工作流定义，所有 creator 统一执行")
    reasoning: str = Field(default="", description="LLM 的推理过程，用中文简述")


# =============================================================================
# Excel 上传模块
# =============================================================================

class ExcelParseResult(BaseModel):
    """Excel 解析结果。"""

    total: int = Field(..., description="成功解析的达人数")
    creators: list[dict[str, Any]] = Field(..., description="达人列表")
    skipped: int = Field(default=0, description="无法解析 mid 而被跳过的行数")
