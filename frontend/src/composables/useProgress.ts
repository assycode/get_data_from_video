// =============================================================================
// 进度轮询 Composable
// =============================================================================

import { ref, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getTaskStatus } from '../api'
import type { TaskStatusResponse } from '../types'

export interface UseProgressOptions {
  interval?: number  // 轮询间隔（毫秒）
  onUpdate?: (data: TaskStatusResponse) => void
  onComplete?: (data: TaskStatusResponse) => void
}

export function useProgress() {
  const isPolling = ref(false)
  const timer = ref<ReturnType<typeof setInterval> | null>(null)

  /**
   * 开始轮询
   */
  function startPolling(taskId: string, options: UseProgressOptions = {}) {
    const { interval = 2000, onUpdate, onComplete } = options

    if (timer.value) return
    isPolling.value = true

    timer.value = setInterval(async () => {
      try {
        const data = await getTaskStatus(taskId)
        onUpdate?.(data)

        const status = data.status
        if (status === 'completed' || status === 'cancelled') {
          stopPolling()
          onComplete?.(data)
          if (status === 'completed') {
            ElMessage.success('任务已完成！')
          }
        }
      } catch (e) {
        console.warn('轮询失败:', e)
      }
    }, interval)
  }

  /**
   * 停止轮询
   */
  function stopPolling() {
    if (timer.value) {
      clearInterval(timer.value)
      timer.value = null
    }
    isPolling.value = false
  }

  // 组件卸载时自动清理
  onUnmounted(() => {
    stopPolling()
  })

  return {
    isPolling,
    startPolling,
    stopPolling,
  }
}
