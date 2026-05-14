// =============================================================================
// 请求封装 - 统一处理错误和 loading
// =============================================================================

import { ElMessage } from 'element-plus'
import type { ApiResponse } from '../types'

/** 基础请求配置 */
interface RequestConfig extends RequestInit {
  showError?: boolean  // 是否显示错误消息
}

/** 发送请求 */
export async function request<T = any>(
  url: string,
  config: RequestConfig = {}
): Promise<T> {
  const { showError = true, ...fetchConfig } = config

  try {
    const response = await fetch(url, {
      ...fetchConfig,
      headers: {
        'Accept': 'application/json',
        ...(fetchConfig.headers || {}),
      },
    })

    const data: ApiResponse<T> = await response.json()

    if (!response.ok || data.code !== 0) {
      const errorMsg = data.message || `请求失败: ${response.status}`
      if (showError) {
        ElMessage.error(errorMsg)
      }
      throw new Error(errorMsg)
    }

    return data.data
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      // 用户取消，不报错
      throw error
    }
    if (showError) {
      ElMessage.error(error instanceof Error ? error.message : '网络请求失败')
    }
    throw error
  }
}

/** GET 请求 */
export function get<T = any>(url: string, config: RequestConfig = {}) {
  return request<T>(url, { ...config, method: 'GET' })
}

/** POST 请求 (JSON) */
export function post<T = any>(url: string, data: any, config: RequestConfig = {}) {
  return request<T>(url, {
    ...config,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(config.headers || {}),
    },
    body: JSON.stringify(data),
  })
}

/** POST 请求 (FormData) */
export function postForm<T = any>(url: string, formData: FormData, config: RequestConfig = {}) {
  return request<T>(url, {
    ...config,
    method: 'POST',
    body: formData,
  })
}
