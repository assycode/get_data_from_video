"""
B站（bilibili）平台数据接口实现

对接观星 API，负责 B 站相关的所有数据抓取。
"""
from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from api.base import api_request
from config import settings

logger = logging.getLogger(__name__)

# B站观星 API 基础地址
BASE_URL = settings.DATA_API_BASE_URL


# ------------------------------------------------------------------------------
# 接口 1：获取 UP 主基本信息
# ------------------------------------------------------------------------------
async def get_up_info(upper_mid: int) -> dict:
    """获取 UP 主基本信息。

    Returns:
        包含 name / sex / face / sign / level 等字段的 dict。
    """
    return await api_request(BASE_URL, "/bl-accinfo", {"upper_mid": upper_mid})


# ------------------------------------------------------------------------------
# 接口 2：获取 UP 主粉丝数据
# ------------------------------------------------------------------------------
async def get_up_follower(upper_mid: int) -> dict:
    """获取 UP 主粉丝数据。

    Returns:
        包含 follower / following 等字段的 dict。
    """
    return await api_request(BASE_URL, "/bl-accstat", {"upper_mid": upper_mid})


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
    """
    return await api_request(BASE_URL, "/bl-arclist", {"upper_mid": upper_mid, "pn": pn})


# ------------------------------------------------------------------------------
# 接口 4：获取视频数据（基础详情）
# ------------------------------------------------------------------------------
async def get_video_data(id: str) -> dict:
    """获取单个视频的详细数据（不含标签）。

    Args:
        id: 视频 ID，bvid 或 aid 均可，如 "BV1iq4y1o7BS"。

    Returns:
        包含 bvid / title / pubdate / stat 等字段的 dict。
    """
    return await api_request(BASE_URL, "/bl-view", {"id": id})


# ------------------------------------------------------------------------------
# 接口 5：获取视频完整数据（含标签）
# ------------------------------------------------------------------------------
async def get_video_detail(id: str) -> dict:
    """获取视频完整数据（含标签 Tags 和分词 participle）。

    Args:
        id: 视频 ID，bvid 或 aid 均可。

    Returns:
        包含 View / Tags / participle / Card 的 dict。
    """
    return await api_request(BASE_URL, "/bl-detail", {"id": id})


# ------------------------------------------------------------------------------
# 接口 6：解析短链接
# ------------------------------------------------------------------------------
async def resolve_short_url(short_code: str) -> dict:
    """解析B站短链接为真实URL，提取bvid/avid/mid。

    Args:
        short_code: 短链接代码，如 b23.tv/xxxx 中的 xxxx 部分。

    Returns:
        包含 bvid / avid / mid / resolved_url 的 dict。
    """
    if not short_code:
        return {"error": "短链接代码为空"}

    url = f"https://b23.tv/{short_code}"
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                },
            )
            final_url = str(response.url)

            # B站短链接可能返回 200 + JS 跳转
            if "b23.tv/" in final_url or "bilibili.com" not in final_url:
                html = response.text
                for pattern in [
                    r'<meta[^>]*http-equiv=["\']?refresh["\']?[^>]*content=["\']?\d+;\s*url=([^"\'>\s]+)',
                    r'(?:window\.)?location\.(?:href|replace|assign)\s*=\s*["\']([^"\']+)["\']',
                    r'(?:window\.)?location\s*=\s*["\']([^"\']+)["\']',
                    r'href=["\'](https?://(?:www\.)?bilibili\.com/[^"\']+)["\']',
                ]:
                    match = re.search(pattern, html, re.IGNORECASE)
                    if match:
                        final_url = match.group(1)
                        break

                if final_url.startswith("/"):
                    final_url = f"https://b23.tv{final_url}"
                if final_url and final_url != str(response.url):
                    try:
                        resp2 = await client.get(final_url, headers={"User-Agent": "Mozilla/5.0"})
                        final_url = str(resp2.url)
                    except Exception:
                        pass

            result: dict[str, Any] = {"resolved_url": final_url}

            bv_match = re.search(r"bilibili\.com/video/(BV\w+)", final_url, re.IGNORECASE)
            if bv_match:
                result["bvid"] = bv_match.group(1)
            av_match = re.search(r"bilibili\.com/video/av(\d+)", final_url, re.IGNORECASE)
            if av_match:
                result["avid"] = int(av_match.group(1))
            mid_match = re.search(r"space\.bilibili\.com/(\d+)", final_url, re.IGNORECASE)
            if mid_match:
                result["mid"] = int(mid_match.group(1))

            logger.info(
                f"[ShortURL] {short_code} → {final_url} | "
                f"bvid={result.get('bvid')} mid={result.get('mid')}"
            )
            return result
    except httpx.TimeoutException:
        return {"error": "短链接解析超时", "detail": f"{url} 在 30s 内未响应"}
    except Exception as exc:
        return {"error": "短链接解析异常", "detail": f"{type(exc).__name__}: {exc}"}


# 接口注册表（供 Executor 动态反射发现）
API_REGISTRY = {
    "get_up_info": get_up_info,
    "get_up_follower": get_up_follower,
    "get_video_list": get_video_list,
    "get_video_data": get_video_data,
    "get_video_detail": get_video_detail,
    "resolve_short_url": resolve_short_url,
}
