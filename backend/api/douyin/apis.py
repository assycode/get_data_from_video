"""
抖音（douyin）平台数据接口实现

对接观星 API，负责抖音相关的所有数据抓取。

已实现接口：
- aweme-detail    : 批量视频详情（最多20个）
- aweme-shorten   : 通过 sec_uid 获取用户短链接
- ac-nonce        : 获取达人粉丝所需的 ac_nonce 标识
- aweme-video     : 获取达人粉丝（需要 aweme_id + ac_nonce + ac_signature）
- get-roomid      : 获取用户当前直播房间号

⚠️ 已知缺失（文档不完整）：
- 获取用户视频列表（主页作品列表）—— 缺少请求URL和参数说明
- ac_signature 的获取方式 —— 文档中未提供对应接口
"""
from __future__ import annotations

import logging
from typing import Any

from api.base import api_request
from config import settings

logger = logging.getLogger(__name__)

# 抖音观星 API 基础地址（与 B站共用同一 base_url）
BASE_URL = settings.DATA_API_BASE_URL


# ------------------------------------------------------------------------------
# 接口 1：批量视频详情
# ------------------------------------------------------------------------------
async def get_douyin_video_detail(ids: str) -> dict:
    """批量获取抖音视频详情。

    Args:
        ids: 视频ID，多个用逗号分隔，单次最多20个。
             如 "7098235952635579679,7148762346909961503"

    Returns:
        包含 data（视频详情数组）的 dict。
        每条视频含 aweme_id / desc / create_time / author / statistics / text_extra 等。
    """
    return await api_request(BASE_URL, "/aweme-detail", {"ids": ids})


# ------------------------------------------------------------------------------
# 接口 2：获取用户短链接
# ------------------------------------------------------------------------------
async def get_douyin_short_url(sec_uid: str) -> dict:
    """通过用户 sec_uid 获取抖音短链接。

    Args:
        sec_uid: 用户加密ID。如 "MS4wLjABAAAATWmP2vPRlE8jyQ0-VVmFwxfXcjkBu3toGOhh2kKdL_g99J20qlJ9e8Gb2-PY2y9h"

    Returns:
        包含 short_url / target 的 dict。
    """
    return await api_request(BASE_URL, "/aweme-shorten", {"sec_uid": sec_uid})


# ------------------------------------------------------------------------------
# 接口 3：获取 ac_nonce（达人粉丝前置接口）
# ------------------------------------------------------------------------------
async def get_douyin_ac_nonce(aweme_id: str) -> dict:
    """获取查询达人粉丝所需的 ac_nonce 标识。

    Args:
        aweme_id: 视频ID。

    Returns:
        包含 ac_nonce 的 dict。
    """
    return await api_request(BASE_URL, "/ac-nonce", {"aweme_id": aweme_id})


# ------------------------------------------------------------------------------
# 接口 4：获取达人粉丝
# ------------------------------------------------------------------------------
async def get_douyin_follower(aweme_id: str, ac_nonce: str, ac_signature: str) -> dict:
    """获取视频对应的达人粉丝数。

    ⚠️ 注意：此接口需要 ac_signature，但当前接口文档未提供获取 ac_signature 的方式。
    如果 ac_signature 为空，接口可能返回错误。

    Args:
        aweme_id: 视频ID。
        ac_nonce: 从 ac-nonce 接口获取的标识。
        ac_signature: 签名令牌（文档缺失获取方式，目前需要外部传入）。

    Returns:
        包含 followerCount 的 dict。
    """
    params: dict[str, Any] = {"aweme_id": aweme_id, "ac_nonce": ac_nonce}
    if ac_signature:
        params["ac_signature"] = ac_signature
    return await api_request(BASE_URL, "/aweme-video", params)


# ------------------------------------------------------------------------------
# 接口 5：获取用户当前直播房间号
# ------------------------------------------------------------------------------
async def get_douyin_room_id(uid: str) -> dict:
    """获取抖音用户当前直播房间号。

    Args:
        uid: 抖音用户数字UID。

    Returns:
        包含 room_id 的 dict。
    """
    return await api_request(BASE_URL, "/get-roomid", {"uid": uid})


# ------------------------------------------------------------------------------
# 接口 6：获取用户视频列表
# ------------------------------------------------------------------------------
async def get_douyin_user_videos(sec_uid: str, cursor: int = 0, count: int = 50) -> dict:
    """获取抖音用户的视频列表（主页作品）。

    Args:
        sec_uid: 用户加密ID（executor 使用 sec_uid，但 API 需要 sec_user_id）。
        cursor: 分页游标（max_cursor，时间戳毫秒），默认0。
        count: 每页数量，默认50。

    Returns:
        标准化响应格式：
        {
            "data": {
                "list": [...],           # 视频列表（从 item_info_list 提取 aweme_info）
                "cursor": int,           # 下一页游标
                "has_more": bool,        # 是否还有更多
                "total": int             # 当前页数量
            }
        }
    """
    # 参数映射：executor 使用 sec_uid/cursor，但 API 需要 sec_user_id/max_cursor
    params = {
        "sec_user_id": sec_uid,
        "max_cursor": cursor,
        "count": count,
    }

    result = await api_request(BASE_URL, "/aweme-list", params)

    # 标准化响应格式，与 B站 get_video_list 保持一致
    if result.get("code") != 0:
        return result

    raw_data = result.get("data", {})

    # 从 item_info_list 提取 aweme_info 作为 list
    item_info_list = raw_data.get("item_info_list", [])
    video_list = []
    for item in item_info_list:
        aweme_info = item.get("aweme_info")
        if aweme_info:
            video_list.append(aweme_info)

    # 构建标准化响应
    normalized = {
        "code": 0,
        "message": "success",
        "data": {
            "list": video_list,
            "cursor": raw_data.get("cursor", 0),
            "has_more": bool(raw_data.get("has_more", 0)),
            "total": len(video_list),
        }
    }

    return normalized


# 接口注册表（供 Executor 动态反射发现）
API_REGISTRY = {
    "get_douyin_video_detail": get_douyin_video_detail,
    "get_douyin_short_url": get_douyin_short_url,
    "get_douyin_ac_nonce": get_douyin_ac_nonce,
    "get_douyin_follower": get_douyin_follower,
    "get_douyin_room_id": get_douyin_room_id,
    "get_douyin_user_videos": get_douyin_user_videos,
}
