"""
结果截断模块。

对工具返回的超长结果进行智能截断，确保不会超过 LLM 上下文承载能力。
关键原则：dict 结构必须保留（因为下游提取函数依赖它），list 可以截断。
"""
from __future__ import annotations

import json
import logging

from config import settings

logger = logging.getLogger(__name__)


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
