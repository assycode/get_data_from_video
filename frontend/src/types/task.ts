// =============================================================================
// 任务相关类型定义
// =============================================================================

/** 达人信息 */
export interface Creator {
  nickname: string
  platform: 'bilibili' | 'douyin' | 'xiaohongshu'
  sec_uid?: string
  uid?: string
  aweme_id?: string
  bvid?: string
  [key: string]: any
}

/** 全局过滤条件 */
export interface GlobalFilter {
  topic?: string
  start_date?: string
  end_date?: string
  min_play?: number
}

/** 工作流步骤 */
export interface WorkflowStep {
  tool_name: string
  reason: string
}

/** 详情查询配置 */
export interface EachDetailConfig {
  need_query: boolean
  tool_name: string
  param_mapping: Record<string, string>
}

/** 分页规则 */
export interface PageRule {
  enable_page: boolean
  max_page: number
  page_size: number
  cursor_field: string
  has_more_field: string
}

/** 单平台工作流 */
export interface Workflow {
  tool_sequence: WorkflowStep[]
  each_detail: EachDetailConfig
  page_rule: PageRule
}

/** LLM 工作流计划 */
export interface LLMWorkflowPlan {
  reasoning: string
  global_filter: GlobalFilter
  workflows: Record<string, Workflow>
  export_fields: string[]
}

/** 任务进度 */
export interface TaskProgress {
  completed: number
  total: number
  percent: number
}

/** 达人处理结果 */
export interface CreatorResult {
  nickname: string
  status: 'pending' | 'processing' | 'success' | 'error'
  total_videos: number
  candidate_videos: number
  matched_videos: number
  error?: string
}

/** 任务结果 */
export interface TaskResult {
  totalCreators: number
  matchedVideos: number
  videos: VideoItem[]
  exportFields: string[]
}

/** 视频项 */
export interface VideoItem {
  // B站字段
  bvid?: string
  aid?: number
  title?: string
  description?: string
  dynamic?: string
  pubdate?: number
  duration?: number
  view?: number
  danmaku?: number
  reply?: number
  favorite?: number
  coin?: number
  share?: number
  like?: number
  tags?: any[]
  participle?: string[]
  
  // 抖音字段
  aweme_id?: string
  desc?: string
  create_time?: number
  play_count?: number
  digg_count?: number
  comment_count?: number
  share_count?: number
  author_nickname?: string
  author_unique_id?: string
  text_extra?: any[]
  
  // 通用字段
  creator_nickname?: string
  creator_mid?: string
  follower?: number
  following?: number
  sign?: string
  level?: number
  url?: string
}

/** 时间线步骤 */
export interface TimelineStep {
  tool_name: string
  reason: string
  is_detail: boolean
  is_platform_header: boolean
  platform?: string
}
