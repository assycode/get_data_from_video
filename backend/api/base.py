"""
公共 HTTP 客户端和辅助函数

所有平台的数据接口共享同一个 HTTP 请求逻辑。
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from config import settings


async def api_request(base_url: str, endpoint: str, params: dict[str, Any], auth_key: str = "") -> dict:
    """发送 GET 请求到数据 API，统一处理响应和异常。

    Args:
        base_url: API 基础地址，如 "http://api-guanxing.changwankeji.com/api"。
        endpoint: API 端点路径，如 "/bl-arclist"。
        params: 查询参数字典。
        auth_key: 认证密钥，如果有的话。

    Returns:
        成功：接口返回的 JSON dict。
        失败：{"error": "...", "detail": "..."}。
    """
    url = f"{base_url.rstrip('/')}{endpoint}"
    req_params = dict(params)
    if auth_key:
        req_params["auth_key"] = auth_key
    elif settings.DATA_API_AUTH_KEY:
        req_params["auth_key"] = settings.DATA_API_AUTH_KEY

    try:
        async with httpx.AsyncClient(timeout=settings.DATA_API_TIMEOUT) as client:
            response = await client.get(url, params=req_params)
            response.raise_for_status()
            data = response.json()
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
