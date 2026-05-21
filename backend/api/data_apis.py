"""
数据接口实现（向后兼容转发）。

本模块已按平台拆包到 api/bilibili/、api/douyin/、api/xiaohongshu/ 目录下。
此处保留原有导入路径，确保已引用本模块的代码不会崩溃。
"""
from __future__ import annotations

# 从 bilibili 包导入所有函数（向后兼容）
from api.bilibili.apis import (
    get_up_info,
    get_up_follower,
    get_video_list,
    get_video_data,
    get_video_detail,
    resolve_short_url,
)

# 从 douyin 包导入所有函数（新增）
from api.douyin.apis import (
    get_douyin_video_detail,
    get_douyin_short_url,
    get_douyin_ac_nonce,
    get_douyin_follower,
    get_douyin_room_id,
    get_douyin_user_videos,
)

# 从小红书包导入所有函数
from api.xiaohongshu import (
    get_xhs_notes_list,
    get_xhs_note_info,
)

# 从快手包导入所有函数
from api.kuaishou import (
    get_ks_video_list,
    get_ks_video_detail,
    get_ks_user_info,
    get_ks_topic_list,
    get_ks_share_data,
    get_ks_live,
)

# 从花火包导入所有函数
from api.huahuo import (
    get_huahuo_list,
    get_huahuo_up_portrait,
    get_huahuo_up_trend,
    get_huahuo_up_growth,
    get_huahuo_up_attention_user,
    get_huahuo_up_representative,
    get_huahuo_up_similar_content,
    get_huahuo_up_highlights,
    get_huahuo_signed_up_list,
    get_huahuo_task_info,
    get_huahuo_order_info,
    get_huahuo_fav_lists,
    get_huahuo_fav_up_list,
    add_huahuo_fav,
    cancel_huahuo_fav,
)

# 接口注册表（向后兼容，新代码建议使用 api.registry.API_REGISTRY）
API_REGISTRY = {
    "get_up_info": get_up_info,
    "get_up_follower": get_up_follower,
    "get_video_list": get_video_list,
    "get_video_data": get_video_data,
    "get_video_detail": get_video_detail,
    "resolve_short_url": resolve_short_url,
    # 抖音接口
    "get_douyin_video_detail": get_douyin_video_detail,
    "get_douyin_short_url": get_douyin_short_url,
    "get_douyin_ac_nonce": get_douyin_ac_nonce,
    "get_douyin_follower": get_douyin_follower,
    "get_douyin_room_id": get_douyin_room_id,
    "get_douyin_user_videos": get_douyin_user_videos,
    # 小红书接口
    "get_xhs_notes_list": get_xhs_notes_list,
    "get_xhs_note_info": get_xhs_note_info,
    # 快手接口
    "get_ks_video_list": get_ks_video_list,
    "get_ks_video_detail": get_ks_video_detail,
    "get_ks_user_info": get_ks_user_info,
    "get_ks_topic_list": get_ks_topic_list,
    "get_ks_share_data": get_ks_share_data,
    "get_ks_live": get_ks_live,
    # 花火接口
    "get_huahuo_list": get_huahuo_list,
    "get_huahuo_up_portrait": get_huahuo_up_portrait,
    "get_huahuo_up_trend": get_huahuo_up_trend,
    "get_huahuo_up_growth": get_huahuo_up_growth,
    "get_huahuo_up_attention_user": get_huahuo_up_attention_user,
    "get_huahuo_up_representative": get_huahuo_up_representative,
    "get_huahuo_up_similar_content": get_huahuo_up_similar_content,
    "get_huahuo_up_highlights": get_huahuo_up_highlights,
    "get_huahuo_signed_up_list": get_huahuo_signed_up_list,
    "get_huahuo_task_info": get_huahuo_task_info,
    "get_huahuo_order_info": get_huahuo_order_info,
    "get_huahuo_fav_lists": get_huahuo_fav_lists,
    "get_huahuo_fav_up_list": get_huahuo_fav_up_list,
    "add_huahuo_fav": add_huahuo_fav,
    "cancel_huahuo_fav": cancel_huahuo_fav,
}

# 同步辅助函数注册表（向后兼容）
from utils.common_utils import extract_mid_from_space_url

SYNC_HELPERS = {
    "extract_mid_from_space_url": extract_mid_from_space_url,
}
