"""
数据接口实现（真实 API 层）

本模块直接对接观星 API（或其他可替换的数据源），负责：
1. 发送 HTTP 请求到真实接口。
2. 解析响应，统一返回结构化 dict。
3. 异常捕获：网络错误、超时、接口返回非 200 等全部捕获并包装为错误 dict。

设计原则：
- 每个函数对应接口文档中的一个接口（一对一映射）。
- 所有函数签名与 api_schema.json 中定义的 parameters 保持一致。
- 返回格式：成功时返回 JSON dict；失败时返回 {"error": "...", "detail": "..."}。
- 便于 Executor 统一处理，无需关心底层差异。
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from config import settings

from utils.common_utils import extract_mid_from_space_url

# ------------------------------------------------------------------------------
# 公共 HTTP 客户端和辅助函数
# ------------------------------------------------------------------------------





async def _api_request(endpoint: str, params: dict[str, Any]) -> dict:
    """发送 GET 请求到数据 API，统一处理响应和异常。

    Args:
        endpoint: API 端点路径，如 "/bl-arclist"。
        params: 查询参数字典。

    Returns:
        成功：接口返回的 JSON dict（通常包含 data / code 字段）。
        失败：{"error": "...", "detail": "..."}。
    """
    url = f"{settings.DATA_API_BASE_URL}{endpoint}"
    # 如有认证密钥，自动附加
    req_params = dict(params)
    if settings.DATA_API_AUTH_KEY:
        req_params["auth_key"] = settings.DATA_API_AUTH_KEY

    try:
        async with httpx.AsyncClient(timeout=settings.DATA_API_TIMEOUT) as client:
            #异步  必须await
            response = await client.get(url, params=req_params)
            # 如果status不是200 直接报错
            response.raise_for_status()
            data = response.json()
            # 部分接口以 code != 0 表示业务错误
            # 如果不是字典实例，也直接报错
            if isinstance(data, dict) and data.get("code", 0) != 0:
                return {
                    "error": f"接口业务错误 code={data.get('code')}",
                    "detail": data.get("message", "未知错误"),
                    "raw": data,
                }
            return data
    except httpx.TimeoutException:
        return {"error": "请求超时", "detail": f"{url} 在 {settings.DATA_API_TIMEOUT}s 内未响应"}
    except httpx.HTTPStatusError as exc:
        return {"error": "HTTP 错误", "detail": f"状态码 {exc.response.status_code}: {exc.response.text[:200]}"}
    except httpx.RequestError as exc:
        return {"error": "网络请求失败", "detail": str(exc)}
    except json.JSONDecodeError as exc:
        return {"error": "JSON 解析失败", "detail": str(exc)}
    except Exception as exc:
        return {"error": "未知异常", "detail": f"{type(exc).__name__}: {exc}"}


# ------------------------------------------------------------------------------
# 接口 1：获取 UP 主基本信息
# ------------------------------------------------------------------------------


async def get_up_info(upper_mid: int) -> dict:
    """获取 UP 主基本信息。

    Args:
        upper_mid: UP 主 ID（mid）。

    Returns:
        包含 name / sex / face / sign / level 等字段的 dict。
    """
    return await _api_request("/bl-accinfo", {"upper_mid": upper_mid})


# ------------------------------------------------------------------------------
# 接口 2：获取 UP 主粉丝数据
# ------------------------------------------------------------------------------


async def get_up_follower(upper_mid: int) -> dict:
    """获取 UP 主粉丝数据。

    Args:
        upper_mid: UP 主 ID（mid）。

    Returns:
        包含 follower / following 等字段的 dict。
    """
    return await _api_request("/bl-accstat", {"upper_mid": upper_mid})


# ------------------------------------------------------------------------------
# 接口 3：获取视频列表（分页）
# ------------------------------------------------------------------------------


async def get_video_list(upper_mid: int, pn: int = 1) -> dict:
    """获取 UP 主的视频列表（分页）。

    Args:
        upper_mid: UP 主 ID（mid）。
        pn: 页码，从 1 开始。

    Returns:
        包含 vlist（视频数组）和 page（分页信息）的 dict。
        vlist 中每项含 bvid / aid / title / play / comment / created(时间戳) 等。
    """
    return await _api_request("/bl-arclist", {"upper_mid": upper_mid, "pn": pn})


# ------------------------------------------------------------------------------
# 接口 4：获取视频数据（基础详情）
# ------------------------------------------------------------------------------


async def get_video_data(id: str) -> dict:
    """获取单个视频的详细数据（不含标签）。

    Args:
        id: 视频 ID，bvid 或 aid 均可，如 "BV1iq4y1o7BS"。

    Returns:
        包含 bvid / title / pubdate / stat(播放/点赞/投币/收藏/分享) 等字段的 dict。
    """
    return await _api_request("/bl-view", {"id": id})


# ------------------------------------------------------------------------------
# 接口 5：获取视频完整数据（含标签）
# ------------------------------------------------------------------------------


async def get_video_detail(id: str) -> dict:
    """获取视频完整数据（含标签 Tags 和分词 participle）。

    Args:
        id: 视频 ID，bvid 或 aid 均可。

    Returns:
        包含 View / Tags / participle / Card 的 dict。
        Tags 数组每项含 tag_name；participle 为字符串数组，是话题标签列表。
    """
    return await _api_request("/bl-detail", {"id": id})


# ------------------------------------------------------------------------------
# 接口注册表（供 Executor 动态反射发现）
# key 必须与 api_schema.json 中的 tool.name 保持一致
# ------------------------------------------------------------------------------

API_REGISTRY = {
    "get_up_info": get_up_info,
    "get_up_follower": get_up_follower,
    "get_video_list": get_video_list,
    "get_video_data": get_video_data,
    "get_video_detail": get_video_detail,
}

# 同步辅助函数注册表（用于非异步场景，如 Excel 解析时提取 mid）
SYNC_HELPERS = {
    "extract_mid_from_space_url": extract_mid_from_space_url,
}
