"""
小红书 API 模块
"""

from .apis import (
    API_REGISTRY,
    APIError,
    get_api,
    list_apis,
    # 博主信息
    get_user_info,
    get_data_overview,
    get_data_v1,
    # 笔记内容
    get_notes_list,
    get_note_detail,
    # 粉丝数据
    get_fans_summary,
    get_fans_portrait,
    get_fans_trend,
    # 带货/直播
    get_ecommerce_category,
    get_distribution_analysis,
    get_live_detail,
    get_live_trend,
    # 评论
    get_note_comments,
    get_spread_performance,
)

# 别名（与 data_apis.py 中的导入名称一致）
get_xhs_notes_list = get_notes_list
get_xhs_note_info = get_note_detail

__all__ = [
    "API_REGISTRY",
    "get_api",
    "list_apis",
    "APIError",
    # 博主信息
    "get_user_info",
    "get_data_overview",
    "get_data_v1",
    # 笔记内容
    "get_notes_list",
    "get_note_detail",
    "get_xhs_notes_list",  # 别名
    "get_xhs_note_info",   # 别名
    # 粉丝数据
    "get_fans_summary",
    "get_fans_portrait",
    "get_fans_trend",
    # 带货/直播
    "get_ecommerce_category",
    "get_distribution_analysis",
    "get_live_detail",
    "get_live_trend",
    # 评论
    "get_note_comments",
    "get_spread_performance",
]
