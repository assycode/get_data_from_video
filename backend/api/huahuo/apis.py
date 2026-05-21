"""
花火（Huahuo）平台 API 接口封装

对接观星 API，负责 B站花火商业合作平台相关的所有数据抓取。
"""
from __future__ import annotations

import logging
from typing import Any

from api.base import api_request
from config import settings

logger = logging.getLogger(__name__)

BASE_URL = settings.DATA_API_BASE_URL


# ------------------------------------------------------------------------------
# 接口 1：获取UP主列表（花火达人库）
# ------------------------------------------------------------------------------
async def get_huahuo_list(
    key: str | None = None,
    page: int = 1,
    order_bys: int | None = None,
    content_tag_id: int | None = None,
    commercial_tag_id: str | None = None,
    fans_ranges: str | None = None,
    min_fans_num: int | None = None,
    max_fans_num: int | None = None,
    task_price_ranges: str | None = None,
    min_task_price: int | None = None,
    max_task_price: int | None = None,
    cooperation_types: str | None = None,
    region_id: int | None = None,
    partition_id: int | None = None,
    second_partition_id: int | None = None,
    gender: str | None = None,
) -> dict[str, Any]:
    """获取花火UP主列表（达人库）

    Args:
        key: 搜索关键词
        page: 页码，默认1
        order_bys: 排序字段，0-综合 1-粉丝升序 2-粉丝降序 3-报价降序 4-报价升序
        content_tag_id: 内容分类ID
        commercial_tag_id: 商单类型ID，多个逗号分隔
        fans_ranges: 粉丝数量范围，多个逗号分隔
        min_fans_num: 粉丝数最小值
        max_fans_num: 粉丝数最大值
        task_price_ranges: 任务价格范围，多个逗号分隔
        min_task_price: 报价最小值
        max_task_price: 报价最大值
        cooperation_types: 合作类型，1-植入视频 2-定制视频 3-直发动态 4-转发动态 -1-非标准
        region_id: UP主画像--主分区
        partition_id: UP主画像--所在地域省份
        second_partition_id: UP主画像--所在地域城市
        gender: 达人性别，0-男 1-女

    Returns:
        包含UP主列表和分页信息的dict
    """
    params: dict[str, Any] = {"page": page}
    if key:
        params["key"] = key
    if order_bys is not None:
        params["order_bys"] = order_bys
    if content_tag_id:
        params["content_tag_id"] = content_tag_id
    if commercial_tag_id:
        params["commercial_tag_id"] = commercial_tag_id
    if fans_ranges:
        params["fans_ranges"] = fans_ranges
    if min_fans_num is not None:
        params["min_fans_num"] = min_fans_num
    if max_fans_num is not None:
        params["max_fans_num"] = max_fans_num
    if task_price_ranges:
        params["task_price_ranges"] = task_price_ranges
    if min_task_price is not None:
        params["min_task_price"] = min_task_price
    if max_task_price is not None:
        params["max_task_price"] = max_task_price
    if cooperation_types:
        params["cooperation_types"] = cooperation_types
    if region_id:
        params["region_id"] = region_id
    if partition_id:
        params["partition_id"] = partition_id
    if second_partition_id:
        params["second_partition_id"] = second_partition_id
    if gender:
        params["gender"] = gender

    return await api_request(BASE_URL, "/bl-list", params)


# ------------------------------------------------------------------------------
# 接口 2：获取UP主个人信息（画像）
# ------------------------------------------------------------------------------
async def get_huahuo_up_portrait(upper_mid: int, mcn_id: int) -> dict[str, Any]:
    """获取UP主个人信息（画像数据）

    Args:
        upper_mid: UP主ID（B站UID）
        mcn_id: MCN机构ID（花火ID）

    Returns:
        包含UP主详细画像数据的dict，包括粉丝分布、内容数据、报价等
    """
    params = {"upper_mid": upper_mid, "mcn_id": mcn_id}
    return await api_request(BASE_URL, "/bl-portrait", params)


# ------------------------------------------------------------------------------
# 接口 3：获取UP主最新作品
# ------------------------------------------------------------------------------
async def get_huahuo_up_trend(upper_mid: int, trend_type: int = 3) -> dict[str, Any]:
    """获取UP主最新作品趋势数据

    Args:
        upper_mid: UP主ID
        trend_type: 数据类型，3-播放量 4-点赞 5-评论 6-弹幕

    Returns:
        包含UP主最新作品数据的dict
    """
    params = {"upper_mid": upper_mid, "trend_type": trend_type}
    return await api_request(BASE_URL, "/bl-trend", params)


# ------------------------------------------------------------------------------
# 接口 4：获取UP主成长表现
# ------------------------------------------------------------------------------
async def get_huahuo_up_growth(upper_mid: int, query_type: int = 1) -> dict[str, Any]:
    """获取UP主成长表现数据

    Args:
        upper_mid: UP主ID
        query_type: 查询类型，1-总量 2-增量

    Returns:
        包含UP主粉丝增长数据的dict
    """
    params = {"upper_mid": upper_mid, "query_type": query_type}
    return await api_request(BASE_URL, "/bl-attention", params)


# ------------------------------------------------------------------------------
# 接口 5：获取UP主分区
# ------------------------------------------------------------------------------
async def get_huahuo_partitions() -> dict[str, Any]:
    """获取UP主分区列表

    Returns:
        包含B站所有分区的树形结构数据
    """
    return await api_request(BASE_URL, "/bl-partition", {})


# ------------------------------------------------------------------------------
# 接口 6：获取UP主粉丝重合
# ------------------------------------------------------------------------------
async def get_huahuo_up_attention_user(
    upper_mid: int, fans_range: int = 6, page: int = 1
) -> dict[str, Any]:
    """获取UP主粉丝重合的达人列表

    Args:
        upper_mid: UP主ID
        fans_range: 粉丝量范围，2-1~5W 3-5~10W 4-10~20W 5-20~30W 6-30~50W 7-50~100W 8-100~200W 9-200W以上
        page: 页码

    Returns:
        包含粉丝重合达人列表的dict
    """
    params = {"upper_mid": upper_mid, "fans_range": fans_range, "page": page}
    return await api_request(BASE_URL, "/bl-attentionuser", params)


# ------------------------------------------------------------------------------
# 接口 7：获取UP主个人案例
# ------------------------------------------------------------------------------
async def get_huahuo_up_representative(
    upper_mid: int, type: int = 1
) -> dict[str, Any]:
    """获取UP主个人案例/商业案例

    Args:
        upper_mid: UP主ID
        type: 案例类型，1-个人案例 2-商业案例

    Returns:
        包含UP主案例视频列表的dict
    """
    params = {"upper_mid": upper_mid, "type": type}
    return await api_request(BASE_URL, "/bl-representative", params)


# ------------------------------------------------------------------------------
# 接口 8：获取UP主内容重合
# ------------------------------------------------------------------------------
async def get_huahuo_up_similar_content(upper_mid: int) -> dict[str, Any]:
    """获取UP主内容重合的达人列表

    Args:
        upper_mid: UP主ID

    Returns:
        包含内容重合达人列表的dict
    """
    params = {"upper_mid": upper_mid}
    return await api_request(BASE_URL, "/bl-similarcontent", params)


# ------------------------------------------------------------------------------
# 接口 9：获取签约UP主
# ------------------------------------------------------------------------------
async def get_huahuo_signed_up_list(page: int = 1, size: int = 50) -> dict[str, Any]:
    """获取签约UP主列表

    Args:
        page: 页码，默认1
        size: 每页条数，默认50

    Returns:
        包含签约UP主列表的dict
    """
    params = {"page": page, "size": size}
    return await api_request(BASE_URL, "/bl-uplist", params)


# ------------------------------------------------------------------------------
# 接口 10：获取任务基础内容
# ------------------------------------------------------------------------------
async def get_huahuo_task_info(task_no: str) -> dict[str, Any]:
    """获取任务基础内容

    Args:
        task_no: 任务编号

    Returns:
        包含任务详细信息的dict
    """
    params = {"task_no": task_no}
    return await api_request(BASE_URL, "/bl-taskno", params)


# ------------------------------------------------------------------------------
# 接口 11：获取订单基础内容
# ------------------------------------------------------------------------------
async def get_huahuo_order_info(order_no: str) -> dict[str, Any]:
    """获取订单基础内容

    Args:
        order_no: 订单编号

    Returns:
        包含订单详细信息的dict
    """
    params = {"order_no": order_no}
    return await api_request(BASE_URL, "/bl-orderno", params)


# ------------------------------------------------------------------------------
# 接口 12：获取稿件亮点
# ------------------------------------------------------------------------------
async def get_huahuo_up_highlights(upper_mid: int, type: int = 1) -> dict[str, Any]:
    """获取UP主稿件亮点数据

    Args:
        upper_mid: UP主ID
        type: 时间范围，1-近30天 2-近90天 3-近180天

    Returns:
        包含投稿数、热门稿件数、爆款视频数等的dict
    """
    params = {"upper_mid": upper_mid, "type": type}
    return await api_request(BASE_URL, "/bl-highlights", params)


# ------------------------------------------------------------------------------
# 接口 13：获取地域
# ------------------------------------------------------------------------------
async def get_huahuo_regions() -> dict[str, Any]:
    """获取地域列表

    Returns:
        包含中国所有省份城市的树形结构数据
    """
    return await api_request(BASE_URL, "/bl-region", {})


# ------------------------------------------------------------------------------
# 接口 14：获取内容标签
# ------------------------------------------------------------------------------
async def get_huahuo_content_tags() -> dict[str, Any]:
    """获取内容标签列表

    Returns:
        包含所有内容分类标签的树形结构数据
    """
    return await api_request(BASE_URL, "/bl-startag", {})


# ------------------------------------------------------------------------------
# 接口 15：获取清单列表
# ------------------------------------------------------------------------------
async def get_huahuo_fav_lists() -> dict[str, Any]:
    """获取收藏清单列表

    Returns:
        包含收藏夹/清单列表的dict
    """
    return await api_request(BASE_URL, "/bl-favlist", {})


# ------------------------------------------------------------------------------
# 接口 16：获取清单数据
# ------------------------------------------------------------------------------
async def get_huahuo_fav_up_list(
    folder_id: int, page: int = 1, size: int = 50
) -> dict[str, Any]:
    """获取清单中的UP主数据

    Args:
        folder_id: 清单ID
        page: 页码，默认1
        size: 每页条数，默认50

    Returns:
        包含清单中UP主列表的dict
    """
    params = {"folder_id": folder_id, "page": page, "size": size}
    return await api_request(BASE_URL, "/bl-favup", params)


# ------------------------------------------------------------------------------
# 接口 17：添加清单
# ------------------------------------------------------------------------------
async def add_huahuo_fav(folder_id: int, mapping_ids: str) -> dict[str, Any]:
    """添加UP主到清单

    Args:
        folder_id: 清单ID
        mapping_ids: 花火ID，多个逗号分隔

    Returns:
        操作结果
    """
    params = {"folder_id": folder_id, "mapping_ids": mapping_ids}
    return await api_request(BASE_URL, "/bl-favadd", params)


# ------------------------------------------------------------------------------
# 接口 18：取消清单
# ------------------------------------------------------------------------------
async def cancel_huahuo_fav(folder_id: int, mapping_id: int) -> dict[str, Any]:
    """从清单中移除UP主

    Args:
        folder_id: 清单ID
        mapping_id: 花火ID

    Returns:
        操作结果
    """
    params = {"folder_id": folder_id, "mapping_id": mapping_id}
    return await api_request(BASE_URL, "/bl-favcan", params)


# ------------------------------------------------------------------------------
# 接口 19：获取服务商列表
# ------------------------------------------------------------------------------
async def get_huahuo_service_providers() -> dict[str, Any]:
    """获取服务商列表

    Returns:
        包含服务商列表的dict
    """
    return await api_request(BASE_URL, "/bl-service", {})


# API 注册表（供 Executor 动态反射发现）
API_REGISTRY = {
    # UP主相关
    "get_huahuo_list": get_huahuo_list,
    "get_huahuo_up_portrait": get_huahuo_up_portrait,
    "get_huahuo_up_trend": get_huahuo_up_trend,
    "get_huahuo_up_growth": get_huahuo_up_growth,
    "get_huahuo_up_attention_user": get_huahuo_up_attention_user,
    "get_huahuo_up_representative": get_huahuo_up_representative,
    "get_huahuo_up_similar_content": get_huahuo_up_similar_content,
    "get_huahuo_up_highlights": get_huahuo_up_highlights,
    # 签约UP主
    "get_huahuo_signed_up_list": get_huahuo_signed_up_list,
    # 任务订单相关
    "get_huahuo_task_info": get_huahuo_task_info,
    "get_huahuo_order_info": get_huahuo_order_info,
    # 配置数据
    "get_huahuo_partitions": get_huahuo_partitions,
    "get_huahuo_regions": get_huahuo_regions,
    "get_huahuo_content_tags": get_huahuo_content_tags,
    "get_huahuo_service_providers": get_huahuo_service_providers,
    # 清单相关
    "get_huahuo_fav_lists": get_huahuo_fav_lists,
    "get_huahuo_fav_up_list": get_huahuo_fav_up_list,
    "add_huahuo_fav": add_huahuo_fav,
    "cancel_huahuo_fav": cancel_huahuo_fav,
}
