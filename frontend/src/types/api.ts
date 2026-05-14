// =============================================================================
// API 相关类型定义
// =============================================================================

/** API 统一响应格式 */
export interface ApiResponse<T = any> {
  code: number
  message: string
  data: T
}

/** Excel 解析响应 */
export interface ExcelParseResponse {
  total: number
  creators: import('./task').Creator[]
}

/** 任务创建响应 */
export interface TaskCreateResponse {
  task_id: string
  total_creators: number
}

/** 任务状态响应 */
export interface TaskStatusResponse {
  status: 'pending' | 'running' | 'completed' | 'cancelled'
  completed: number
  total: number
  matched_so_far: number
  videos: import('./task').VideoItem[]
}

/** SSE 事件类型 */
export type SSEEventType = 
  | 'start' 
  | 'thought' 
  | 'progress' 
  | 'resume' 
  | 'final' 
  | 'error' 
  | 'done'
  | 'creator_start'
  | 'creator_done'

/** SSE 事件数据 */
export interface SSEEvent {
  event: SSEEventType
  content: any
}

/** SSE 开始事件 */
export interface SSEStartEvent {
  total_creators: number
  task_id: string
}

/** SSE 思考事件 */
export interface SSEThoughtEvent {
  plan: import('./task').LLMWorkflowPlan
}

/** SSE 进度事件 */
export interface SSEProgressEvent {
  completed: number
  total: number
  matched_so_far: number
}

/** SSE 恢复事件 */
export interface SSEResumeEvent extends SSEProgressEvent {
  task_id: string
  videos: import('./task').VideoItem[]
}

/** SSE 最终事件 */
export interface SSEFinalEvent {
  matched_videos: number
  videos: import('./task').VideoItem[]
  export_fields: string[]
}

/** SSE 错误事件 */
export interface SSEErrorEvent {
  message: string
}

/** SSE 完成事件 */
export interface SSEDoneEvent {
  status: 'completed' | 'cancelled'
}
