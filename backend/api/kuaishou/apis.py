"""
快手 API 接口封装
"""
from __future__ import annotations

import logging
from typing import Any

from api.base import api_request
from config import settings

logger = logging.getLogger(__name__)

BASE_URL = settings.DATA_API_BASE_URL


async def get_ks_video_list(uid: int | str, pcursor: int | str | None = None) -> dict[str, Any]:
    """获取快手用户视频列表
    
    Args:
        uid: 快手用户UID
        pcursor: 时间戳毫秒级别，拉取比当前时间小的数据
    
    Returns:
        视频列表数据
    """
    params = {"uid": uid}
    if pcursor:
        params["pcursor"] = pcursor
    
    return await api_request(BASE_URL, "/ks-feed", params)


async def get_ks_video_detail(photo_id: int | str) -> dict[str, Any]:
    """获取快手单个视频详情
    
    Args:
        photo_id: 快手视频ID
    
    Returns:
        视频详情数据
    """
    params = {"photo_id": photo_id}
    
    return await api_request(BASE_URL, "/ks-detail", params)


async def get_ks_user_info(uid: int | str) -> dict[str, Any]:
    """获取快手用户基础数据
    
    Args:
        uid: 快手用户UID
    
    Returns:
        用户基础数据
    """
    params = {"uid": uid}
    
    return await api_request(BASE_URL, "/ks-user", params)


# API 注册表
API_REGISTRY = {
    "get_ks_video_list": get_ks_video_list,
    "get_ks_video_detail": get_ks_video_detail,
    "get_ks_user_info": get_ks_user_info,
}
