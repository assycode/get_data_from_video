"""B站（bilibili）平台数据接口包。"""
from __future__ import annotations

from .apis import (
    get_up_info,
    get_up_follower,
    get_video_list,
    get_video_data,
    get_video_detail,
    resolve_short_url,
)

__all__ = [
    "get_up_info",
    "get_up_follower",
    "get_video_list",
    "get_video_data",
    "get_video_detail",
    "resolve_short_url",
]
