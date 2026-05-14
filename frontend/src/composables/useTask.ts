// =============================================================================
// 任务管理 Composable - 核心逻辑
// =============================================================================

import { ref, computed, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useTaskStore, useResultStore } from '../stores'
import { planTask, createTask, cancelTask, getTaskStatus } from '../api'
import { useSSE } from './useSSE'
import { useProgress } from './useProgress'
import { generateWorkflowSteps, getTaskId, saveTaskId, clearTaskId } from '../utils'
import type { SSEEvent, Creator, LLMWorkflowPlan } from '../types'

export interface UseTaskOptions {
  platform?: 'all' | 'douyin' | 'bilibili' | 'xiaohongshu'
}

export function useTask(
  options: UseTaskOptions = {},
  // 允许外部传入 store，避免在 setup 阶段调用 useStore
  externalTaskStore?: ReturnType<typeof useTaskStore>,
  externalResultStore?: ReturnType<typeof useResultStore>
) {
  const { platform = 'all' } = options

  // Composables
  const sse = useSSE()
  const progress = useProgress()

  // Local state
  const planAbortController = ref<AbortController | null>(null)
  const isStartingTask = ref(false)

  // Store 引用（延迟初始化）
  let _taskStore: ReturnType<typeof useTaskStore> | undefined = externalTaskStore
  let _resultStore: ReturnType<typeof useResultStore> | undefined = externalResultStore
  
  const getTaskStore = () => {
    if (!_taskStore) _taskStore = useTaskStore()
    return _taskStore
  }
  
  const getResultStore = () => {
    if (!_resultStore) _resultStore = useResultStore()
    return _resultStore
  }

  // Getters - 使用延迟初始化，避免在 composable 创建时访问 store
  const workflowSteps = computed(() => {
    const store = getTaskStore()
    if (!store.llmPlan?.workflows) return []
    return generateWorkflowSteps(store.llmPlan.workflows)
  })

  /**
   * 启动任务（完整流程）
   */
  async function startTask(
    file: File,
    question: string,
    topic: string,
    startDate: string,
    creators: Creator[]
  ) {
    const taskStore = getTaskStore()
    const resultStore = getResultStore()
    
    // 防护检查
    if (taskStore.currentTaskId) {
      ElMessage.warning('已有任务在运行')
      return
    }
    if (getTaskId()) {
      ElMessage.info('检测到未完成任务，正在恢复...')
      return
    }
    if (isStartingTask.value || taskStore.isRunning) {
      ElMessage.warning('任务正在进行中')
      return
    }

    isStartingTask.value = true
    taskStore.reset()
    resultStore.reset()
    taskStore.setPlanning(true)

    try {
      // Step 1: 获取 LLM 执行计划
      const plan = await fetchPlan(question, topic, startDate, creators)
      taskStore.setPlan(plan)
      taskStore.setPlanning(false)

      // Step 2: 创建任务
      const taskId = await createTask(file, question, topic, startDate, plan)
      taskStore.setTaskId(taskId)
      taskStore.setRunning()

      // Step 3: 连接 SSE
      connectSSE(taskId)

      ElMessage.success('任务已创建，开始批量抓取')
    } catch (e: any) {
      console.error('[startTask] 任务启动失败:', e)
      handleError(e)
    } finally {
      isStartingTask.value = false
    }
  }

  /**
   * 获取执行计划
   */
  async function fetchPlan(
    question: string,
    topic: string,
    startDate: string,
    creators: Creator[]
  ): Promise<LLMWorkflowPlan> {
    planAbortController.value = new AbortController()
    try {
      const plan = await planTask(question, topic, startDate, creators, planAbortController.value.signal)
      
      // 防护检查：确保 plan 是有效对象
      if (!plan || typeof plan !== 'object') {
        throw new Error('AI 返回的执行计划格式无效')
      }
      if (!plan.workflows || Object.keys(plan.workflows).length === 0) {
        throw new Error('AI 返回的执行计划中没有工作流')
      }
      
      ElMessage.success('AI 接口选型完成')
      return plan
    } finally {
      planAbortController.value = null
    }
  }

  /**
   * 连接 SSE
   */
  function connectSSE(taskId: string) {
    sse.connect(`/api/task-progress/${taskId}`, {
      onMessage: handleSSEMessage,
      onClose: () => {
        // SSE 断开，切换到轮询
        const store = getTaskStore()
        if (store.currentTaskId && !progress.isPolling.value) {
          ElMessage.info('连接已断开，自动切换为进度轮询模式')
          progress.startPolling(taskId, {
            onUpdate: handlePollingUpdate,
            onComplete: handlePollingComplete,
          })
        }
      },
    })
  }

  /**
   * 处理 SSE 消息
   */
  function handleSSEMessage(payload: SSEEvent) {
    const taskStore = getTaskStore()
    const resultStore = getResultStore()
    
    switch (payload.event) {
      case 'start':
        resultStore.setTotalCreators(payload.content.total_creators || 0)
        taskStore.updateProgress(0, payload.content.total_creators || 0)
        if (payload.content.task_id) {
          taskStore.setTaskId(payload.content.task_id)
        }
        break

      case 'thought':
        taskStore.setPlan(payload.content.plan)
        break

      case 'progress':
        taskStore.updateProgress(
          payload.content.completed || 0,
          payload.content.total || 0
        )
        resultStore.setMatchedVideos(payload.content.matched_so_far || 0)
        break

      case 'resume':
        if (payload.content.task_id) {
          taskStore.setTaskId(payload.content.task_id)
        }
        taskStore.updateProgress(
          payload.content.completed || 0,
          payload.content.total || 0
        )
        resultStore.setMatchedVideos(payload.content.matched_so_far || 0)
        resultStore.setTotalCreators(payload.content.total || 0)
        if (payload.content.videos) {
          resultStore.setVideos(payload.content.videos)
        }
        break

      case 'final':
        resultStore.setMatchedVideos(payload.content.matched_videos || 0)
        if (payload.content.videos) {
          resultStore.setVideos(payload.content.videos)
        }
        if (payload.content.export_fields) {
          resultStore.setExportFields(payload.content.export_fields)
        }
        break

      case 'error':
        taskStore.setError(payload.content.message || '未知错误')
        ElMessage.error(payload.content.message || '未知错误')
        break

      case 'done':
        taskStore.setCompleted()
        taskStore.clearTask()
        break
    }
  }

  /**
   * 处理轮询更新
   */
  function handlePollingUpdate(data: any) {
    const taskStore = getTaskStore()
    const resultStore = getResultStore()
    taskStore.updateProgress(data.completed || 0, data.total || 0)
    resultStore.setMatchedVideos(data.matched_so_far || 0)
    if (data.videos?.length > 0) {
      resultStore.setVideos(data.videos)
    }
  }

  /**
   * 处理轮询完成
   */
  function handlePollingComplete(data: any) {
    const taskStore = getTaskStore()
    taskStore.setCompleted()
    taskStore.clearTask()
  }

  /**
   * 取消任务
   */
  async function cancel() {
    const taskStore = getTaskStore()
    const taskId = taskStore.currentTaskId || getTaskId()

    // 取消规划阶段
    if (planAbortController.value) {
      planAbortController.value.abort()
      planAbortController.value = null
      taskStore.setPlanning(false)
      ElMessage.info('已取消规划')
      if (taskId) {
        try {
          await cancelTask(taskId)
        } catch (e) {
          console.warn('取消请求失败:', e)
        }
      }
      return
    }

    // 取消执行阶段
    sse.disconnect()
    progress.stopPolling()

    if (taskId) {
      try {
        await cancelTask(taskId)
      } catch (e) {
        console.warn('取消请求失败:', e)
      }
      taskStore.clearTask()
    }

    ElMessage.info('已取消')
  }

  /**
   * 恢复任务（页面刷新后）
   */
  async function resumeTask() {
    const savedTaskId = getTaskId()
    if (!savedTaskId) return

    const taskStore = getTaskStore()
    const resultStore = getResultStore()

    try {
      const data = await getTaskStatus(savedTaskId)
      const status = data.status

      // 恢复状态
      taskStore.setTaskId(savedTaskId)
      taskStore.updateProgress(data.completed || 0, data.total || 0)
      resultStore.setMatchedVideos(data.matched_so_far || 0)
      resultStore.setTotalCreators(data.total || 0)
      resultStore.setVideos(data.videos || [])

      if (status === 'completed' || status === 'cancelled') {
        taskStore.setCompleted()
        taskStore.clearTask()
        if (status === 'completed') {
          ElMessage.success('任务已完成，已恢复结果')
        }
        return
      }

      // 任务仍在运行
      taskStore.setRunning()
      ElMessage.info('检测到正在进行的任务，已恢复 SSE 连接')
      connectSSE(savedTaskId)
    } catch (e) {
      console.warn('恢复任务失败:', e)
      clearTaskId()
    }
  }

  /**
   * 错误处理
   */
  function handleError(e: any) {
    const taskStore = getTaskStore()
    
    if (e.name === 'AbortError') {
      // 用户取消，静默处理，但仍需重置状态
      taskStore.setPlanning(false)
      return
    }
    
    const msg = e.message || '任务执行失败'
    console.error('[handleError] 任务出错:', msg, e)
    taskStore.setError(msg)
    taskStore.setPlanning(false)  // 重置规划状态
    ElMessage.error(msg)
  }

  return {
    // State
    isStartingTask,
    workflowSteps,
    // Actions
    startTask,
    cancel,
    resumeTask,
    // Store getters（延迟初始化）
    get taskStore() { return getTaskStore() },
    get resultStore() { return getResultStore() },
    // Composables (暴露以便外部使用)
    sse,
    progress,
  }
}
