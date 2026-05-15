// =============================================================================
// 任务状态管理 (Pinia)
// =============================================================================

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  TaskStatus,
  TaskProgress,
  CreatorResult,
  LLMWorkflowPlan,
} from '../types'
import { calcProgress, saveTaskId, clearTaskId } from '../utils'

export const useTaskStore = defineStore('task', () => {
  // ==========================================================================
  // State
  // ==========================================================================
  
  const currentTaskId = ref('')
  const status = ref<TaskStatus>('idle')
  const progress = ref<TaskProgress>({ completed: 0, total: 0, percent: 0 })
  const creatorResults = ref<CreatorResult[]>([])
  const llmPlan = ref<LLMWorkflowPlan | null>(null)
  const isPlanning = ref(false)
  const errorMsg = ref('')

  // ==========================================================================
  // Getters
  // ==========================================================================
  
  const isRunning = computed(() => status.value === 'running' || status.value === 'planning')
  const isCompleted = computed(() => status.value === 'completed')
  const isCancelled = computed(() => status.value === 'cancelled')
  const hasError = computed(() => !!errorMsg.value)
  
  const successCount = computed(() => 
    creatorResults.value.filter(r => r.status === 'success').length
  )
  const errorCount = computed(() => 
    creatorResults.value.filter(r => r.status === 'error').length
  )

  // ==========================================================================
  // Actions
  // ==========================================================================
  
  function setTaskId(taskId: string) {
    currentTaskId.value = taskId
    saveTaskId(taskId)
  }

  function clearTask(keepPlan: boolean = true) {
    currentTaskId.value = ''
    clearTaskId()
    status.value = 'idle'
    progress.value = { completed: 0, total: 0, percent: 0 }
    creatorResults.value = []
    // 默认保留大模型选型结果，方便用户查看
    if (!keepPlan) {
      llmPlan.value = null
    }
    isPlanning.value = false
    errorMsg.value = ''
  }

  function setPlanning(value: boolean) {
    isPlanning.value = value
    status.value = value ? 'planning' : status.value
  }

  function setRunning() {
    status.value = 'running'
    isPlanning.value = false
  }

  function setCompleted() {
    status.value = 'completed'
  }

  function setCancelled() {
    status.value = 'cancelled'
  }

  function setError(msg: string) {
    status.value = 'error'
    errorMsg.value = msg
  }

  function updateProgress(completed: number, total: number) {
    progress.value = {
      completed,
      total,
      percent: calcProgress(completed, total),
    }
  }

  function setPlan(plan: LLMWorkflowPlan) {
    llmPlan.value = plan
  }

  function addCreatorResult(result: CreatorResult) {
    const index = creatorResults.value.findIndex(r => r.nickname === result.nickname)
    if (index >= 0) {
      creatorResults.value[index] = result
    } else {
      creatorResults.value.push(result)
    }
  }

  function reset() {
    clearTask(false) // 新任务开始时清空所有状态，包括 plan
  }

  // ==========================================================================
  // Return
  // ==========================================================================
  return {
    // State
    currentTaskId,
    status,
    progress,
    creatorResults,
    llmPlan,
    isPlanning,
    errorMsg,
    // Getters
    isRunning,
    isCompleted,
    isCancelled,
    hasError,
    successCount,
    errorCount,
    // Actions
    setTaskId,
    clearTask,
    setPlanning,
    setRunning,
    setCompleted,
    setCancelled,
    setError,
    updateProgress,
    setPlan,
    addCreatorResult,
    reset,
  }
})
