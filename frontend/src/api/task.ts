// =============================================================================
// 任务管理 API
// =============================================================================

import { get, post, postForm } from './request'
import type {
  LLMWorkflowPlan,
  TaskCreateResponse,
  TaskStatusResponse,
  Creator,
} from '../types'

/** 任务规划 - 获取 LLM 执行计划 */
export async function planTask(
  question: string,
  topic: string,
  startDate: string,
  creators: Creator[],
  signal?: AbortSignal
): Promise<LLMWorkflowPlan> {
  return post<LLMWorkflowPlan>(
    '/api/plan-task',
    {
      question,
      topic,
      start_date: startDate,
      creators,
    },
    { signal }
  )
}

/** 创建任务 */
export async function createTask(
  file: File,
  question: string,
  topic: string,
  startDate: string,
  plan: LLMWorkflowPlan
): Promise<string> {
  // 防护检查：确保 plan 是有效对象
  if (!plan || typeof plan !== 'object') {
    throw new Error('执行计划(plan)不能为空')
  }
  
  const formData = new FormData()
  formData.append('question', question)
  formData.append('file', file)
  if (topic) formData.append('topic', topic)
  if (startDate) formData.append('start_date', startDate)
  formData.append('plan_json', JSON.stringify(plan))

  const result = await postForm<TaskCreateResponse>('/api/start-task', formData)
  return result.task_id
}

/** 获取任务状态 */
export async function getTaskStatus(taskId: string): Promise<TaskStatusResponse> {
  return get<TaskStatusResponse>(`/api/task-status?task_id=${taskId}`)
}

/** 取消任务 */
export async function cancelTask(taskId: string): Promise<void> {
  const formData = new FormData()
  formData.append('task_id', taskId)
  await postForm('/api/cancel-task', formData)
}

/** SSE 进度流 URL */
export function getTaskProgressUrl(taskId: string): string {
  return `/api/task-progress/${taskId}`
}
