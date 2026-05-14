"""
数据提取辅助函数与工具输出提取器。

负责从各种 API 返回结构中安全提取关键字段，
以及定义每个工具执行完后如何回填 param_pool。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# 通用数据提取辅助
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
    """从接口返回数据中提取视频列表。

    支持多种返回结构：
    - B站: data.list.vlist / data.vlist
    - 抖音: data（直接为数组）
    - 通用: 根级 list / data 本身是 list
    """
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
        if isinstance(data, list):
            logger.info(f"[_extract_vlist] data 本身是 list，共 {len(data)} 条")
            return data
        return []

    list_fields = ("vlist", "archives", "list", "videos", "items", "records", "aweme_list")

    # 1. 尝试 data.list.xxx
    inner = _safe_get(data, "data", "list", default={})
    if isinstance(inner, dict):
        videos = _find_list_field(inner, *list_fields)
        if videos:
            sample = videos[0] if videos else {}
            logger.info(f"[_extract_vlist] 从 data.list 提取到 {len(videos)} 条视频，首条字段={list(sample.keys())[:8]}")
            return videos

    # 2. 尝试 data.xxx（data 本身可能是 dict 或 list）
    inner = _safe_get(data, "data", default={})
    if isinstance(inner, list):
        # 抖音 aweme-detail 返回 data 直接为数组
        logger.info(f"[_extract_vlist] 从 data（数组）提取到 {len(inner)} 条视频，首条字段={list(inner[0].keys())[:8] if inner else []}")
        return inner
    if isinstance(inner, dict):
        videos = _find_list_field(inner, *list_fields)
        if videos:
            sample = videos[0] if videos else {}
            logger.info(f"[_extract_vlist] 从 data 提取到 {len(videos)} 条视频，首条字段={list(sample.keys())[:8]}")
            return videos

    # 3. 尝试根级
    videos = _find_list_field(data, *list_fields)
    if videos:
        sample = videos[0] if videos else {}
        logger.info(f"[_extract_vlist] 从根级提取到 {len(videos)} 条视频，首条字段={list(sample.keys())[:8]}")
        return videos

    # 4. data 本身是 list（兜底）
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
    for key in ("created", "pubdate", "ctime", "timestamp", "publish_time", "addtime", "create_time"):
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
# 抖音专用提取辅助
# ------------------------------------------------------------------------------


def _extract_douyin_video_detail(data: Any) -> dict[str, Any]:
    """从 aweme-detail 返回中提取关键字段。"""
    if not isinstance(data, dict):
        return {"video_list": []}
    video_list = data.get("data", [])
    if not isinstance(video_list, list):
        video_list = []

    result: dict[str, Any] = {"video_list": video_list}

    # 从第一条视频提取关键字段到 param_pool，方便后续步骤使用
    first = video_list[0] if video_list else {}
    if isinstance(first, dict):
        result["aweme_id"] = first.get("aweme_id")
        result["title"] = first.get("desc")  # desc 对应 title
        result["pubdate"] = first.get("create_time")
        result["desc"] = first.get("desc")
        result["statistics"] = first.get("statistics")
        result["author"] = first.get("author")
        result["text_extra"] = first.get("text_extra")
        result["share_url"] = first.get("share_url")
        result["duration"] = first.get("duration")
        # 作者信息扁平化
        author = first.get("author", {})
        if isinstance(author, dict):
            result["author_uid"] = author.get("uid")
            result["author_nickname"] = author.get("nickname")
            result["author_unique_id"] = author.get("unique_id")

    return result


# ------------------------------------------------------------------------------
# 工具输出提取器：每个工具执行完后，把关键字段回填到 param_pool
# ------------------------------------------------------------------------------

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
    # --- 抖音工具 ---
    "get_douyin_video_detail": lambda data: _extract_douyin_video_detail(data),
    "get_douyin_short_url": lambda data: {
        "short_url": data.get("short_url") if isinstance(data, dict) else None,
        "target_url": data.get("target") if isinstance(data, dict) else None,
    },
    "get_douyin_ac_nonce": lambda data: {
        "ac_nonce": data.get("ac_nonce") if isinstance(data, dict) else None,
    },
    "get_douyin_follower": lambda data: {
        "follower_count": data.get("followerCount") if isinstance(data, dict) else None,
    },
    "get_douyin_room_id": lambda data: {
        "room_id": data.get("room_id") if isinstance(data, dict) else None,
    },
    "get_douyin_user_videos": lambda data: {
        "video_list": _extract_vlist(data),
        "has_more": _safe_get(data, "data", "has_more"),
        "cursor": _safe_get(data, "data", "cursor"),
    },
    # --- 小红书工具 ---
    "get_xhs_notes_list": lambda data: {
        "note_list": _extract_vlist(data),
        "total": _safe_get(data, "data", "total"),
        "page_info": _extract_page_info(data),
    },
    "get_xhs_note_info": lambda data: {
        "like_num": _safe_get(data, "data", "likeNum"),
        "fav_num": _safe_get(data, "data", "favNum"),
        "cmt_num": _safe_get(data, "data", "cmtNum"),
        "read_num": _safe_get(data, "data", "readNum"),
        "share_num": _safe_get(data, "data", "shareNum"),
        "follow_cnt": _safe_get(data, "data", "followCnt"),
        "user_info": _safe_get(data, "data", "userInfo"),
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
