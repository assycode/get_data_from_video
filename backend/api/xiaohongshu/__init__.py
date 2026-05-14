"""小红书（xiaohongshu）平台数据接口实现

对接观星 API，负责小红书相关的所有数据抓取。
"""
from __future__ import annotations

import logging
from typing import Any

from api.base import api_request
from config import settings

logger = logging.getLogger(__name__)

# 小红书观星 API 基础地址
BASE_URL = settings.DATA_API_BASE_URL


# ------------------------------------------------------------------------------
# 接口 1：获取用户笔记列表
# ------------------------------------------------------------------------------
async def get_xhs_notes_list(
    user_id: str,
    page_number: int = 1,
    page_size: int = 20,
    note_type: int = 4,
    advertise_switch: int = 1,
    order_type: int = 1,
) -> dict:
    """获取小红书用户的笔记列表。

    Args:
        user_id: 小红书用户ID。
        page_number: 页码，从1开始。
        page_size: 每页数量，默认20。
        note_type: 笔记类型 1-图文 2-视频 3-合作 4-全部。
        advertise_switch: 流量类型 1-全部流量 0-自然流量。
        order_type: 排序类型 1-最新 2-阅读 3-互动。

    Returns:
        包含笔记列表的 dict。
    """
    params = {
        "pageNumber": page_number,
        "pageSize": page_size,
        "noteType": note_type,
        "advertiseSwitch": advertise_switch,
        "orderType": order_type,
        "withComponent": 0,
        "featureTag": "",
        "contentTag": "",
    }
    return await api_request(BASE_URL, f"/xhs-notesDetail/{user_id}", params)


# ------------------------------------------------------------------------------
# 接口 2：获取笔记详情
# ------------------------------------------------------------------------------
async def get_xhs_note_info(note_id: str) -> dict:
    """获取小红书笔记详情。

    Args:
        note_id: 笔记ID。

    Returns:
        包含笔记详情的 dict。
    """
    return await api_request(BASE_URL, f"/xhs-noteInfo/{note_id}", {})


# 接口注册表
API_REGISTRY = {
    "get_xhs_notes_list": get_xhs_notes_list,
    "get_xhs_note_info": get_xhs_note_info,
}
