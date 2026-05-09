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
# 接口 6：解析短链接
# ------------------------------------------------------------------------------


async def resolve_short_url(short_code: str) -> dict:
    """解析B站短链接为真实URL，提取bvid/avid/mid。

    Args:
        short_code: 短链接代码，如 b23.tv/xxxx 中的 xxxx 部分。

    Returns:
        包含 bvid / avid / mid / resolved_url 的 dict。
        失败时返回 {"error": "...", "detail": "..."}。
    """
    if not short_code:
        return {"error": "短链接代码为空"}

    url = f"https://b23.tv/{short_code}"
    try:
        # 使用支持 cookie 持久化的 client，B站短链接可能需要 cookie
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            # 第一次请求：获取最终跳转 URL
            response = await client.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                },
            )

            # 获取最终 URL（follow_redirects=True 会自动跟随 302）
            final_url = str(response.url)

            # B站短链接可能返回 200 + JS 跳转（而不是 302），需要手动解析 HTML
            if "b23.tv/" in final_url or "bilibili.com" not in final_url:
                html = response.text

                # 1. 尝试 meta refresh
                meta_match = re.search(
                    r'<meta[^>]*http-equiv=["\']?refresh["\']?[^>]*content=["\']?\d+;\s*url=([^"\'>\s]+)',
                    html, re.IGNORECASE
                )
                if meta_match:
                    final_url = meta_match.group(1)
                else:
                    # 2. 尝试 JS window.location.href / location.replace
                    js_match = re.search(
                        r'(?:window\.)?location\.(?:href|replace|assign)\s*=\s*["\']([^"\']+)["\']',
                        html
                    )
                    if js_match:
                        final_url = js_match.group(1)
                    else:
                        # 3. 尝试 window.location = "..."
                        js_match2 = re.search(
                            r'(?:window\.)?location\s*=\s*["\']([^"\']+)["\']',
                            html
                        )
                        if js_match2:
                            final_url = js_match2.group(1)
                        else:
                            # 4. 尝试 href 链接（找 bilibili.com 相关链接）
                            href_match = re.search(
                                r'href=["\'](https?://(?:www\.)?bilibili\.com/[^"\']+)["\']',
                                html
                            )
                            if href_match:
                                final_url = href_match.group(1)

                # 处理相对 URL
                if final_url.startswith("/"):
                    final_url = f"https://b23.tv{final_url}"

                # 如果解析出了新 URL 且不是当前 URL，再次请求
                if final_url and final_url != str(response.url):
                    try:
                        resp2 = await client.get(
                            final_url,
                            headers={
                                "User-Agent": (
                                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                                )
                            },
                        )
                        final_url = str(resp2.url)
                    except Exception:
                        pass

            result: dict[str, Any] = {"resolved_url": final_url}

            # 提取 bvid（兼容大小写）
            bv_match = re.search(r"bilibili\.com/video/(BV\w+)", final_url, re.IGNORECASE)
            if bv_match:
                result["bvid"] = bv_match.group(1)

            # 提取 avid
            av_match = re.search(r"bilibili\.com/video/av(\d+)", final_url, re.IGNORECASE)
            if av_match:
                result["avid"] = int(av_match.group(1))

            # 提取 mid
            mid_match = re.search(r"space\.bilibili\.com/(\d+)", final_url, re.IGNORECASE)
            if mid_match:
                result["mid"] = int(mid_match.group(1))

            import logging as _logging
            _logger = _logging.getLogger(__name__)
            _logger.info(
                f"[ShortURL] {short_code} status={response.status_code} "
                f"history={[str(h.url) for h in response.history]} "
                f"→ {final_url} | bvid={result.get('bvid')} mid={result.get('mid')}"
            )

            return result
    except httpx.TimeoutException:
        return {"error": "短链接解析超时", "detail": f"{url} 在 30s 内未响应"}
    except httpx.RequestError as exc:
        return {"error": "短链接解析请求失败", "detail": str(exc)}
    except Exception as exc:
        return {"error": "短链接解析异常", "detail": f"{type(exc).__name__}: {exc}"}


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
    "resolve_short_url": resolve_short_url,
}

# 同步辅助函数注册表（用于非异步场景，如 Excel 解析时提取 mid）
SYNC_HELPERS = {
    "extract_mid_from_space_url": extract_mid_from_space_url,
}
