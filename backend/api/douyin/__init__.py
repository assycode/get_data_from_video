"""抖音（douyin）平台数据接口包。

已实现接口详见 apis.py，包括：
- get_douyin_video_detail : 批量视频详情
- get_douyin_short_url    : 获取用户短链接
- get_douyin_ac_nonce     : 获取粉丝查询标识
- get_douyin_follower     : 获取达人粉丝
- get_douyin_room_id      : 获取直播房间号
- get_douyin_user_videos  : 获取用户视频列表（文档不完整，占位）
"""
from __future__ import annotations

from .apis import API_REGISTRY

__all__ = ["API_REGISTRY"]
