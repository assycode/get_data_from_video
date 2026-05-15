"""
小红书(xiaohongshu) API 接口封装
基于观星 API: http://api-guanxing.changwankeji.com/api/
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

# API 配置
BASE_URL = os.getenv("XIAOHONGSHU_API_URL", "http://api-guanxing.changwankeji.com/api")
API_KEY = os.getenv("XIAOHONGSHU_API_KEY", "")

# 请求重试配置
MAX_RETRIES = 3
RETRY_DELAY = 1.0


def _build_url(endpoint: str, user_id: str) -> str:
    """构建完整的 API URL"""
    return f"{BASE_URL}/{endpoint}/{user_id}"


async def _request(
    endpoint: str,
    user_id: str,
    params: dict | None = None,
) -> dict[str, Any]:
    """
    发送 HTTP 请求并处理响应
    
    Args:
        endpoint: API 端点
        user_id: 小红书用户ID
        params: 请求参数
        
    Returns:
        API 响应数据
    """
    url = _build_url(endpoint, user_id)
    headers = {}
    
    # 如果配置了 API Key，添加到请求头
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                # 检查业务错误码
                if data.get("code") != 0:
                    raise APIError(f"API Error: {data.get('message', 'Unknown error')}", data)
                
                return data.get("data", {})
                
        except httpx.HTTPStatusError as e:
            last_error = f"HTTP Error {e.response.status_code}: {e.response.text}"
            if e.response.status_code in (429, 500, 502, 503, 504):
                # 可重试错误
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
            raise APIError(last_error)
            
        except httpx.RequestError as e:
            last_error = f"Request Error: {str(e)}"
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
            raise APIError(last_error)
    
    raise APIError(f"Max retries exceeded: {last_error}")


class APIError(Exception):
    """API 错误异常"""
    def __init__(self, message: str, response_data: dict | None = None):
        super().__init__(message)
        self.response_data = response_data


# =============================================================================
# 博主信息相关接口
# =============================================================================

async def get_user_info(user_id: str) -> dict[str, Any]:
    """
    获取博主个人信息
    
    Args:
        user_id: 小红书用户ID
        
    Returns:
        {
            "distributor_id": "用户ID",
            "distributor_name": "昵称",
            "avatar": "头像URL",
            "signature": "签名",
            "sex": "性别",
            "city": "城市",
            "mcn_name": "MCN机构",
            "content_category": [...],
            "red_id": "小红书号",
            ...
        }
    """
    return await _request("xhs-info", user_id)


async def get_data_overview(user_id: str, date_type: int = 1) -> dict[str, Any]:
    """
    获取数据概览
    
    Args:
        user_id: 小红书用户ID
        date_type: 统计天数 1-30天, 2-90天
        
    Returns:
        {
            "fans_num": 粉丝数,
            "increase_fans_num": 新增粉丝数,
            "active_fans_rate": 活跃粉丝占比,
            "engage_fans_rate": 互动粉丝占比,
            "order_fans_rate": 下单粉丝占比,
            "live_viewer_num": 平均观看人数,
            ...
        }
    """
    return await _request("xhs-overview", user_id, {"date_type": date_type})


async def get_data_v1(user_id: str, business: int = 0) -> dict[str, Any]:
    """
    获取新版数据概览（更详细）
    
    Args:
        user_id: 小红书用户ID
        business: 分类 0-按规模, 1-按成本
        
    Returns:
        包含预估CPM、阅读单价、互动单价等详细数据的字典
    """
    return await _request("xhs-datav1", user_id, {"business": business})


# =============================================================================
# 笔记内容相关接口
# =============================================================================

async def get_notes_list(
    user_id: str,
    page_number: int = 1,
    page_size: int = 20,
    note_type: int = 4,
    advertise_switch: int = 1,
    order_type: int = 1,
    with_component: int = 0,
    feature_tag: str = "",
    content_tag: str = "",
) -> dict[str, Any]:
    """
    获取博主笔记列表
    
    Args:
        user_id: 小红书用户ID
        page_number: 页数
        page_size: 每页数量
        note_type: 笔记类型 1-图文, 2-视频, 3-合作, 4-全部
        advertise_switch: 流量类型 0-自然流量, 1-全部流量
        order_type: 排序类型 1-最新, 2-阅读, 3-互动
        with_component: 是否组件 0-全部, 1-仅展示带组件笔记
        feature_tag: 内容特征 (vlog, ootd等)
        content_tag: 内容类目 (母婴等)
        
    Returns:
        {
            "list": [
                {
                    "noteId": "笔记ID",
                    "title": "标题",
                    "imgUrl": "封面URL",
                    "date": "发布日期",
                    "isVideo": true/false,
                    "readNum": 阅读数,
                    "likeNum": 点赞数,
                    "collectNum": 收藏数,
                    ...
                }
            ],
            "total": 总数
        }
    """
    params = {
        "id": user_id,
        "pageNumber": page_number,
        "pageSize": page_size,
        "noteType": note_type,
        "advertiseSwitch": advertise_switch,
        "orderType": order_type,
        "withComponent": with_component,
    }
    
    if feature_tag:
        params["featureTag"] = feature_tag
    if content_tag:
        params["contentTag"] = content_tag
    
    return await _request("xhs-notesDetail", user_id, params)


async def get_note_detail(note_id: str) -> dict[str, Any]:
    """
    获取笔记详情 (通过 note_id 获取单条笔记数据)
    
    Args:
        note_id: 笔记ID
        
    Returns:
        {
            "likeNum": 点赞数,
            "favNum": 收藏数,
            "cmtNum": 评论数,
            "readNum": 阅读数,
            "shareNum": 分享数,
            "followCnt": 关注数,
            "userInfo": {...},
            ...
        }
    """
    # 注意：这里可能需要用不同的端点或参数
    # 根据文档，可能需要使用 note_id 直接查询
    return await _request("xhs-note-detail", note_id)


# =============================================================================
# 粉丝数据相关接口
# =============================================================================

async def get_fans_summary(user_id: str, business: int = 0) -> dict[str, Any]:
    """
    获取博主粉丝数据摘要
    
    Args:
        user_id: 小红书用户ID
        business: 0-日常笔记, 1-合作笔记
        
    Returns:
        {
            "fansNum": 粉丝数,
            "fansIncreaseNum": 粉丝增量,
            "fansGrowthRate": 粉丝量变化幅度,
            "activeFansRate": 活跃粉丝占比,
            "engageFansRate": 互动粉丝占比,
            "readFansRate": 阅读粉丝占比,
            "payFansUserRate30d": 下单粉丝占比,
            ...
        }
    """
    return await _request("xhs-fanssummary", user_id, {"business": business})


async def get_fans_portrait(user_id: str) -> dict[str, Any]:
    """
    获取粉丝画像
    
    Args:
        user_id: 小红书用户ID
        
    Returns:
        包含粉丝年龄、性别、地域等分布数据的字典
    """
    return await _request("xhs-fans-portrait", user_id)


async def get_fans_trend(user_id: str) -> dict[str, Any]:
    """
    获取粉丝趋势
    
    Args:
        user_id: 小红书用户ID
        
    Returns:
        包含粉丝增长趋势数据的字典
    """
    return await _request("xhs-fans-trend", user_id)


# =============================================================================
# 带货/直播相关接口
# =============================================================================

async def get_ecommerce_category(user_id: str) -> dict[str, Any]:
    """
    获取带货类目
    
    Args:
        user_id: 小红书用户ID
        
    Returns:
        带货类目数据
    """
    return await _request("xhs-ecommerce", user_id)


async def get_distribution_analysis(user_id: str) -> dict[str, Any]:
    """
    获取带货分析数据
    
    Args:
        user_id: 小红书用户ID
        
    Returns:
        带货分析数据
    """
    return await _request("xhs-distribution", user_id)


async def get_live_detail(user_id: str) -> dict[str, Any]:
    """
    获取直播明细
    
    Args:
        user_id: 小红书用户ID
        
    Returns:
        直播明细数据
    """
    return await _request("xhs-live-detail", user_id)


async def get_live_trend(user_id: str) -> dict[str, Any]:
    """
    获取直播数据趋势
    
    Args:
        user_id: 小红书用户ID
        
    Returns:
        直播趋势数据
    """
    return await _request("xhs-live-trend", user_id)


# =============================================================================
# 评论相关接口
# =============================================================================

async def get_note_comments(
    note_id: str,
    page_number: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """
    获取笔记评论
    
    Args:
        note_id: 笔记ID
        page_number: 页数
        page_size: 每页数量
        
    Returns:
        {
            "list": [
                {
                    "commentId": "评论ID",
                    "content": "评论内容",
                    "userId": "用户ID",
                    "userNickName": "用户昵称",
                    "likeNum": 点赞数,
                    ...
                }
            ],
            "total": 总数,
            "users": {...}  // 用户信息映射
        }
    """
    return await _request("xhs-comments", note_id, {
        "pageNumber": page_number,
        "pageSize": page_size,
    })


async def get_spread_performance(user_id: str) -> dict[str, Any]:
    """
    获取传播表现数据
    
    Args:
        user_id: 小红书用户ID
        
    Returns:
        传播表现数据
    """
    return await _request("xhs-spread", user_id)


# =============================================================================
# API 注册表 (用于工具注册)
# =============================================================================

API_REGISTRY = {
    # 博主信息
    "get_xhs_user_info": get_user_info,
    "get_xhs_data_overview": get_data_overview,
    "get_xhs_data_v1": get_data_v1,
    
    # 笔记内容
    "get_xhs_notes_list": get_notes_list,
    "get_xhs_note_detail": get_note_detail,
    
    # 粉丝数据
    "get_xhs_fans_summary": get_fans_summary,
    "get_xhs_fans_portrait": get_fans_portrait,
    "get_xhs_fans_trend": get_fans_trend,
    
    # 带货/直播
    "get_xhs_ecommerce_category": get_ecommerce_category,
    "get_xhs_distribution_analysis": get_distribution_analysis,
    "get_xhs_live_detail": get_live_detail,
    "get_xhs_live_trend": get_live_trend,
    
    # 评论
    "get_xhs_note_comments": get_note_comments,
    "get_xhs_spread_performance": get_spread_performance,
}


def get_api(name: str):
    """获取指定名称的 API 函数"""
    return API_REGISTRY.get(name)


def list_apis() -> list[str]:
    """列出所有可用的 API 名称"""
    return list(API_REGISTRY.keys())
