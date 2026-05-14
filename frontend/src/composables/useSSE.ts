// =============================================================================
// SSE 连接管理 Composable
// =============================================================================

import { ref } from 'vue'
import { fetchEventSource } from '@microsoft/fetch-event-source'
import { ElMessage } from 'element-plus'
import type { SSEEvent } from '../types'

export interface UseSSEOptions {
  onMessage?: (event: SSEEvent) => void
  onClose?: () => void
  onError?: (error: Error) => void
}

export function useSSE() {
  const abortController = ref<AbortController | null>(null)
  const isUserCancelled = ref(false)
  const isConnected = ref(false)

  /**
   * 连接 SSE
   */
  function connect(url: string, options: UseSSEOptions = {}) {
    isUserCancelled.value = false
    isConnected.value = true
    abortController.value = new AbortController()

    fetchEventSource(url, {
      method: 'GET',
      signal: abortController.value.signal,
      openWhenHidden: true,
      onmessage(msg) {
        if (!msg.data) return
        try {
          const payload: SSEEvent = JSON.parse(msg.data)
          options.onMessage?.(payload)
        } catch (e) {
          console.warn('SSE 解析失败:', msg.data)
        }
      },
      onclose() {
        isConnected.value = false
        if (isUserCancelled.value) {
          options.onClose?.()
          return
        }
        // 非主动断开
        options.onClose?.()
        throw new Error('SSE connection closed')
      },
      onerror(err) {
        if (isUserCancelled.value) {
          return
        }
        options.onError?.(err)
        throw err
      },
    })
  }

  /**
   * 断开连接
   */
  function disconnect() {
    isUserCancelled.value = true
    if (abortController.value) {
      abortController.value.abort()
      abortController.value = null
    }
    isConnected.value = false
  }

  /**
   * 重新连接
   */
  function reconnect(url: string, options: UseSSEOptions = {}) {
    disconnect()
    // 延迟一点再重连，避免过于频繁
    setTimeout(() => {
      connect(url, options)
    }, 100)
  }

  return {
    isConnected,
    isUserCancelled,
    connect,
    disconnect,
    reconnect,
  }
}
