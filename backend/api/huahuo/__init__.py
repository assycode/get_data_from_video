"""
花火（Huahuo）API 模块

B站花火商业合作平台数据接口。
"""
from .apis import (
    API_REGISTRY,
    # UP主相关
    get_huahuo_list,
    get_huahuo_up_portrait,
    get_huahuo_up_trend,
    get_huahuo_up_growth,
    get_huahuo_up_attention_user,
    get_huahuo_up_representative,
    get_huahuo_up_similar_content,
    get_huahuo_up_highlights,
    # 签约UP主
    get_huahuo_signed_up_list,
    # 任务订单相关
    get_huahuo_task_info,
    get_huahuo_order_info,
    # 配置数据
    get_huahuo_partitions,
    get_huahuo_regions,
    get_huahuo_content_tags,
    get_huahuo_service_providers,
    # 清单相关
    get_huahuo_fav_lists,
    get_huahuo_fav_up_list,
    add_huahuo_fav,
    cancel_huahuo_fav,
)

__all__ = [
    "API_REGISTRY",
    # UP主相关
    "get_huahuo_list",
    "get_huahuo_up_portrait",
    "get_huahuo_up_trend",
    "get_huahuo_up_growth",
    "get_huahuo_up_attention_user",
    "get_huahuo_up_representative",
    "get_huahuo_up_similar_content",
    "get_huahuo_up_highlights",
    # 签约UP主
    "get_huahuo_signed_up_list",
    # 任务订单相关
    "get_huahuo_task_info",
    "get_huahuo_order_info",
    # 配置数据
    "get_huahuo_partitions",
    "get_huahuo_regions",
    "get_huahuo_content_tags",
    "get_huahuo_service_providers",
    # 清单相关
    "get_huahuo_fav_lists",
    "get_huahuo_fav_up_list",
    "add_huahuo_fav",
    "cancel_huahuo_fav",
]
