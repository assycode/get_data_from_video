"""
工具执行器模块

负责将 LLM 生成的 tool_call 映射到实际的数据接口函数并执行。
通过 api_schema.json 中的 tool.name 与 api/data_apis.py 中 API_REGISTRY 的 key 做映射。

执行流程（统一入口）：
    tool_call (name + arguments)
        │
        ▼
    从 TOOL_REGISTRY 查找对应函数 + 参数模型
        │
        ▼
    Pydantic 参数校验
        │
        ▼
    参数类型转换（LLM 常把 int 传成 string）
        │
        ▼
    执行函数（await），拿到原始数据
        │
        ▼
    截断超长结果、包装为 ToolResult
        │
        ▼
    回传给 Planner

新增能力（通用工作流解释器架构）：
- 参数池（param_pool）：每条达人任务独立维护，自动从接口返回回填关键字段
- 参数别名映射：解决不同工具参数名不一致问题（如 id → bvid）
- 工具输出提取器：每个工具定义返回字段如何回填到 param_pool
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from pydantic import BaseModel, Field, ValidationError

from config import settings
from models.schemas import ToolCall, ToolResult

# 引入真实数据接口注册表
from api.data_apis import (
    API_REGISTRY,
    get_up_info,
    get_up_follower,
    get_video_list,
    get_video_data,
    get_video_detail,
    resolve_short_url,
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# 1. 参数 Pydantic 模型（每个工具一套，用于运行时校验）
# ------------------------------------------------------------------------------


class GetUpInfoArgs(BaseModel):
    """获取 UP 主基本信息参数"""
    upper_mid: int = Field(..., description="UP主ID（mid）")


class GetUpFollowerArgs(BaseModel):
    """获取 UP 主粉丝数据参数"""
    upper_mid: int = Field(..., description="UP主ID（mid）")


class GetVideoListArgs(BaseModel):
    """获取视频列表参数"""
    upper_mid: int = Field(..., description="UP主ID（mid）")
    pn: int = Field(default=1, description="页码，从1开始")


class GetVideoDataArgs(BaseModel):
    """获取单个视频基础数据参数"""
    id: str = Field(..., description="视频ID，bvid或aid均可，如 BV1iq4y1o7BS")


class GetVideoDetailArgs(BaseModel):
    """获取视频完整数据（含标签）参数"""
    id: str = Field(..., description="视频ID，bvid或aid均可")


class ResolveShortUrlArgs(BaseModel):
    """解析B站短链接参数"""
    short_code: str = Field(..., description="短链接代码，如 b23.tv/xxxx 中的 xxxx 部分")


# ------------------------------------------------------------------------------
# 2. 通用数据提取辅助（从 batch_planner 复用并扩展）
# ------------------------------------------------------------------------------


def _safe_get(obj: Any, *keys: str, default: Any = None) -> Any:
    """安全嵌套 dict 取值。"""
    if not isinstance(obj, dict):
        return default
    for key in keys:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(key, default)
    return obj


def _find_list_field(data: dict, *field_names: str) -> list[dict]:
    """从 dict 中查找第一个存在的列表字段。"""
    for name in field_names:
        val = data.get(name)
        if isinstance(val, list):
            return val
    return []


def _extract_vlist(data: Any) -> list[dict]:
    """从接口返回数据中提取视频列表。"""
    # 兜底：如果数据被 _trim_result 截断成了包装对象，尝试从 preview 字符串中重新解析
    if isinstance(data, dict) and data.get("_truncated") and isinstance(data.get("preview"), str):
        try:
            parsed = json.loads(data["preview"])
            if isinstance(parsed, dict):
                data = parsed
                logger.warning(f"[_extract_vlist] 从截断包装中恢复数据成功")
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"[_extract_vlist] 截断包装解析失败")
            pass

    if not isinstance(data, dict):
        return []
    list_fields = ("vlist", "archives", "list", "videos", "items", "records")
    inner = _safe_get(data, "data", "list", default={})
    if isinstance(inner, dict):
        videos = _find_list_field(inner, *list_fields)
        if videos:
            sample = videos[0] if videos else {}
            logger.info(f"[_extract_vlist] 从 data.list 提取到 {len(videos)} 条视频，首条字段={list(sample.keys())[:8]}")
            return videos
    inner = _safe_get(data, "data", default={})
    if isinstance(inner, dict):
        videos = _find_list_field(inner, *list_fields)
        if videos:
            sample = videos[0] if videos else {}
            logger.info(f"[_extract_vlist] 从 data 提取到 {len(videos)} 条视频，首条字段={list(sample.keys())[:8]}")
            return videos
    videos = _find_list_field(data, *list_fields)
    if videos:
        sample = videos[0] if videos else {}
        logger.info(f"[_extract_vlist] 从根级提取到 {len(videos)} 条视频，首条字段={list(sample.keys())[:8]}")
        return videos
    if isinstance(data, list):
        logger.info(f"[_extract_vlist] data 本身是 list，共 {len(data)} 条")
        return data
    logger.warning(f"[_extract_vlist] 未能从数据中提取视频列表，data 类型={type(data).__name__}")
    return []


def _extract_page_info(data: Any) -> dict:
    """从接口返回数据中提取分页信息。"""
    # 兜底：如果数据被 _trim_result 截断成了包装对象，尝试从 preview 字符串中重新解析
    if isinstance(data, dict) and data.get("_truncated") and isinstance(data.get("preview"), str):
        try:
            parsed = json.loads(data["preview"])
            if isinstance(parsed, dict):
                data = parsed
        except (json.JSONDecodeError, TypeError):
            pass

    if not isinstance(data, dict):
        return {}
    page = _safe_get(data, "data", "list", "page", default={})
    if isinstance(page, dict) and page:
        return page
    page = _safe_get(data, "data", "page", default={})
    if isinstance(page, dict) and page:
        return page
    page = data.get("page", {})
    if isinstance(page, dict) and page:
        return page
    return {}


def _extract_video_detail(detail: Any) -> tuple[dict, list, list]:
    """从 get_video_detail 返回中提取 View、Tags、participle。"""
    if not isinstance(detail, dict):
        return {}, [], []
    view = _safe_get(detail, "data", "View", default={})
    tags = _safe_get(detail, "data", "Tags", default=[])
    participle = _safe_get(detail, "data", "participle", default=[])
    if not view:
        view = detail.get("View", {})
    if not tags:
        tags = detail.get("Tags", [])
    if not participle:
        participle = detail.get("participle", [])
    if isinstance(tags, dict):
        tags = tags.get("tag", [])
    return view, tags, participle


def _extract_timestamp(video: dict) -> int:
    """从视频数据中提取发布时间戳。"""
    for key in ("created", "pubdate", "ctime", "timestamp", "publish_time", "addtime"):
        val = video.get(key)
        if isinstance(val, int) and val > 0:
            return val
        if isinstance(val, str):
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
    return 0


# ------------------------------------------------------------------------------
# 3. 工具注册中心（核心）：tool_name → {func, args_model, description}
# ------------------------------------------------------------------------------


type ToolEntry = dict[str, Any]

# 每个工具的详细描述：包含入参、反参关键字段，供 LLM 理解工具能力
TOOL_META: dict[str, dict[str, Any]] = {
    "get_up_info": {
        "description": "获取UP主基本信息（昵称、头像、签名等）",
        "input_params": ["upper_mid"],
        "return_fields": ["mid", "name(昵称)", "sex", "face", "sign(签名)", "level"],
    },
    "get_up_follower": {
        "description": "获取UP主粉丝统计数据",
        "input_params": ["upper_mid"],
        "return_fields": ["mid", "follower(粉丝数)", "following(关注数)"],
    },
    "get_video_list": {
        "description": "获取UP主视频列表（分页返回多条视频概要）",
        "input_params": ["upper_mid", "pn(页码,从1开始)"],
        "return_fields": [
            "vlist(视频列表数组, 每条含bvid/aid/title/play/comment/created等)",
            "page(分页信息: pn/ps/count)",
        ],
    },
    "get_video_data": {
        "description": "获取单个视频基础数据（不含标签，适合仅需播放量/点赞/时长等统计量）",
        "input_params": ["id(视频ID,支持bvid或avid)"],
        "return_fields": [
            "bvid", "aid", "title(标题)", "pubdate(发布时间戳)", "duration(时长秒)",
            "desc(描述)", "dynamic(动态文案)", "pic(封面图)",
            "stat(统计对象: view/danmaku/reply/favorite/coin/share/like)",
            "owner(作者信息: mid/name)",
        ],
    },
    "get_video_detail": {
        "description": "获取视频完整数据（含标签Tags和分词participle），是唯一返回话题标签的接口",
        "input_params": ["id(视频ID,支持bvid或 avid)"],
        "return_fields": [
            "View(视频基础信息,同get_video_data)",
            "Tags(标签数组,每项含tag_name)",
            "participle(分词/话题标签字符串数组)",
            "Card(UP主卡片信息)",
        ],
    },
    "resolve_short_url": {
        "description": "解析B站短链接(b23.tv/xxxx)为真实URL，提取bvid/avid/mid",
        "input_params": ["short_code(短链接代码,如b23.tv/xxxx中的xxxx)"],
        "return_fields": [
            "bvid(解析出的BV号)",
            "avid(解析出的AV号)",
            "mid(解析出的UP主MID)",
            "resolved_url(跳转后的真实URL)",
        ],
    },
}


TOOL_REGISTRY: dict[str, ToolEntry] = {
    "get_up_info": {
        "func": get_up_info,
        "args_model": GetUpInfoArgs,
        "description": "获取UP主基本信息",
    },
    "get_up_follower": {
        "func": get_up_follower,
        "args_model": GetUpFollowerArgs,
        "description": "获取UP主粉丝数据",
    },
    "get_video_list": {
        "func": get_video_list,
        "args_model": GetVideoListArgs,
        "description": "获取UP主视频列表（分页）",
    },
    "get_video_data": {
        "func": get_video_data,
        "args_model": GetVideoDataArgs,
        "description": "获取单个视频基础数据（不含标签）",
    },
    "get_video_detail": {
        "func": get_video_detail,
        "args_model": GetVideoDetailArgs,
        "description": "获取视频完整数据（含标签Tags和分词participle）",
    },
    "resolve_short_url": {
        "func": resolve_short_url,
        "args_model": ResolveShortUrlArgs,
        "description": "解析B站短链接为真实URL",
    },
}


# ------------------------------------------------------------------------------
# 4. 参数池机制（新增）
# ------------------------------------------------------------------------------

# 参数别名映射：当工具参数名在 param_pool 中找不到时，尝试这些别名
PARAM_ALIASES: dict[str, list[str]] = {
    "id": ["bvid", "avid"],  # short_code 必须通过 resolve_short_url 解析为 bvid 后才能使用
    "upper_mid": ["upper_mid", "owner_mid", "mid"],
}


def get_tool_names() -> list[str]:
    """返回所有已注册工具的名称列表（白名单）。"""
    return list(TOOL_REGISTRY.keys())


def build_tools_prompt() -> str:
    """从 TOOL_META 生成给 LLM 的工具描述文本（含入参+反参）。"""
    lines = ["## 可用工具（工具名必须严格匹配，严禁编造）\n"]
    for tool_name, meta in TOOL_META.items():
        lines.append(f"- {tool_name}：{meta['description']}")
        lines.append(f"  · 入参：{', '.join(meta['input_params'])}")
        lines.append(f"  · 反参：{', '.join(meta['return_fields'])}")
    return "\n".join(lines)


def build_args_from_pool(tool_name: str, param_pool: dict[str, Any]) -> dict[str, Any] | None:
    """根据 param_pool 自动构建指定工具的入参。

    匹配规则：
    1. 从 TOOL_REGISTRY 获取 args_model，遍历其字段名
    2. 每个字段先从 param_pool 中直接查找同名字段
    3. 找不到时，查 PARAM_ALIASES 尝试别名映射
    4. 还找不到且字段有默认值，则用默认值
    5. 必填字段找不到值 → 返回 None（参数不足）
    """
    entry = TOOL_REGISTRY.get(tool_name)
    if entry is None:
        return None

    args_model: type[BaseModel] = entry["args_model"]
    args: dict[str, Any] = {}

    # 遍历 Pydantic 模型字段
    for field_name, field_info in args_model.model_fields.items():
        val = param_pool.get(field_name)

        # 直接匹配失败 → 尝试别名
        if val is None and field_name in PARAM_ALIASES:
            for alias in PARAM_ALIASES[field_name]:
                if alias in param_pool and param_pool[alias] is not None:
                    val = param_pool[alias]
                    break

        # 分页字段特殊处理
        if field_name == "pn" and val is None:
            val = param_pool.get("pn", 1)

        if val is not None:
            args[field_name] = val
        elif field_info.is_required():
            # 必填但 param_pool 里没有
            logger.debug(f"[ParamPool] 工具 {tool_name} 必填字段 {field_name} 缺失")
            return None
        # 非必填缺失 → 交给 Pydantic 默认值

    return args


# 工具输出提取器：每个工具执行完后，把关键字段回填到 param_pool
TOOL_OUTPUT_EXTRACTORS: dict[str, Callable[[Any], dict[str, Any]]] = {
    "get_video_list": lambda data: {
        "video_list": _extract_vlist(data),
        "page_info": _extract_page_info(data),
    },
    "get_video_data": lambda data: {
        "bvid": _safe_get(data, "data", "bvid"),
        "aid": _safe_get(data, "data", "aid"),
        "title": _safe_get(data, "data", "title"),
        "pubdate": _safe_get(data, "data", "pubdate"),
        "duration": _safe_get(data, "data", "duration"),
        "desc": _safe_get(data, "data", "desc"),
        "dynamic": _safe_get(data, "data", "dynamic"),
        "pic": _safe_get(data, "data", "pic"),
        "stat": _safe_get(data, "data", "stat"),
        "owner_mid": _safe_get(data, "data", "owner", "mid"),
        "owner_name": _safe_get(data, "data", "owner", "name"),
    },
    "get_video_detail": lambda data: {
        "view": _safe_get(data, "data", "View"),
        "tags": _safe_get(data, "data", "Tags"),
        "participle": _safe_get(data, "data", "participle"),
        "card": _safe_get(data, "data", "Card"),
    },
    "get_up_info": lambda data: {
        "upper_mid": _safe_get(data, "data", "mid"),
        "nickname": _safe_get(data, "data", "name"),
        "sign": _safe_get(data, "data", "sign"),
        "face": _safe_get(data, "data", "face"),
        "level": _safe_get(data, "data", "level"),
    },
    "get_up_follower": lambda data: {
        "follower": _safe_get(data, "data", "follower"),
        "following": _safe_get(data, "data", "following"),
    },
    "resolve_short_url": lambda data: {
        "bvid": data.get("bvid") if isinstance(data, dict) else None,
        "avid": data.get("avid") if isinstance(data, dict) else None,
        "upper_mid": data.get("mid") if isinstance(data, dict) else None,
        "resolved_url": data.get("resolved_url") if isinstance(data, dict) else None,
    },
}


def extract_tool_output(tool_name: str, data: Any, param_pool: dict[str, Any]) -> None:
    """执行工具后，把返回数据中的关键字段回填到 param_pool。

    直接修改传入的 param_pool（就地更新）。
    """
    extractor = TOOL_OUTPUT_EXTRACTORS.get(tool_name)
    if extractor is None:
        return
    try:
        extracted = extractor(data)
        for key, val in extracted.items():
            if val is not None:
                param_pool[key] = val
    except Exception as exc:
        logger.warning(f"[ParamPool] 工具 {tool_name} 输出提取异常: {exc}")


# ------------------------------------------------------------------------------
# 5. 执行调度层（统一入口）
# ------------------------------------------------------------------------------


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

    func: Callable = entry["func"]
    args_model: type[BaseModel] = entry["args_model"]

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


# ------------------------------------------------------------------------------
# 6. 参数类型转换
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
# 7. 结果截断
# ------------------------------------------------------------------------------


def _trim_result(data, max_length: int | None = None) -> dict | list | str:
    """对工具返回结果进行截断，确保不会超过 LLM 上下文承载能力。

    策略：
    - 若为 list 且超长，保留头部 + 尾部 + 省略提示。
    - 若为 dict 且序列化后超长，递归截断内部超长的 list 字段，保留 dict 结构。
      这样 _extract_vlist / _extract_page_info 等提取函数仍能正常工作。
    """
    limit = max_length or settings.MAX_TOOL_RESULT_LENGTH

    try:
        json_str = json.dumps(data, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        json_str = str(data)

    # 调试日志：帮助确认配置是否生效
    logger.info(f"[_trim_result] 数据类型={type(data).__name__}, 序列化长度={len(json_str)}, 限制={limit}")

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

    # dict 类型：结构保留截断，递归截断内部超长的 list，绝不破坏整体结构
    if isinstance(data, dict):
        trimmed_dict = _trim_dict_recursive(data, limit)
        trimmed_str = json.dumps(trimmed_dict, ensure_ascii=False, default=str)
        if len(trimmed_str) <= limit:
            return trimmed_dict
        # 如果还是超长，进一步激进截断所有 list
        trimmed_dict2 = _trim_dict_aggressive(trimmed_dict)
        trimmed_str2 = json.dumps(trimmed_dict2, ensure_ascii=False, default=str)
        if len(trimmed_str2) <= limit:
            return trimmed_dict2

    # 兜底：字符串截断（只对无法结构保留的基础类型）
    truncated = json_str[:limit]
    truncated = truncated.rsplit("}", 1)[0] + "}"
    return {
        "_truncated": True,
        "_note": f"结果超长已截断，原长度 {len(json_str)} 字符",
        "preview": truncated,
    }


def _trim_dict_recursive(data: dict, limit: int) -> dict:
    """递归截断 dict 内部超长的 list，保留 dict 键值结构。"""
    result = {}
    for key, val in data.items():
        if isinstance(val, list) and len(val) > 10:
            # 截断 list：保留头3尾3
            trimmed = val[:3] + [{"_note": f"已截断，省略 {len(val) - 6} 条，共 {len(val)} 条"}] + val[-3:]
            result[key] = trimmed
        elif isinstance(val, dict):
            result[key] = _trim_dict_recursive(val, limit)
        else:
            result[key] = val
    return result


def _trim_dict_aggressive(data: dict) -> dict:
    """更激进地截断 dict 内部所有 list，只保留头1尾1。"""
    result = {}
    for key, val in data.items():
        if isinstance(val, list) and len(val) > 2:
            trimmed = val[:1] + [{"_note": f"已截断，省略 {len(val) - 2} 条，共 {len(val)} 条"}] + val[-1:]
            result[key] = trimmed
        elif isinstance(val, dict):
            result[key] = _trim_dict_aggressive(val)
        else:
            result[key] = val
    return result
