// =============================================================================
// 通用辅助函数
// =============================================================================

import type { TimelineStep, Workflow, Creator } from '../types'

/** 从工作流计划生成时间线步骤 */
export function generateWorkflowSteps(
  workflows: Record<string, Workflow>
): TimelineStep[] {
  const steps: TimelineStep[] = []

  for (const [platform, wf] of Object.entries(workflows)) {
    // 平台标题
    steps.push({
      tool_name: `${platform} 平台`,
      reason: '',
      is_detail: false,
      is_platform_header: true,
    })

    // 该平台的 tool_sequence
    for (const s of wf.tool_sequence || []) {
      steps.push({
        tool_name: s.tool_name,
        reason: s.reason,
        is_detail: false,
        is_platform_header: false,
        platform,
      })
    }

    // 该平台的 each_detail
    if (wf.each_detail?.need_query && wf.each_detail.tool_name) {
      steps.push({
        tool_name: wf.each_detail.tool_name,
        reason: `对 ${platform} 列表逐条调用 ${wf.each_detail.tool_name} 获取完整数据`,
        is_detail: true,
        is_platform_header: false,
        platform,
      })
    }
  }

  return steps
}

/** 计算进度百分比 */
export function calcProgress(completed: number, total: number): number {
  if (total <= 0) return 0
  return Math.round((completed / total) * 100)
}

/** 过滤抖音平台的达人 */
export function filterDouyinCreators(creators: Creator[]): Creator[] {
  return creators.filter(c => c.platform === 'douyin')
}

/** 过滤B站平台的达人 */
export function filterBilibiliCreators(creators: Creator[]): Creator[] {
  return creators.filter(c => c.platform === 'bilibili')
}

/** 生成 Excel 文件名 */
export function generateExportFileName(prefix = '抓取结果'): string {
  const date = new Date().toLocaleDateString()
  return `${prefix}_${date}.xlsx`
}

/** 保存任务 ID 到 sessionStorage */
export function saveTaskId(taskId: string): void {
  sessionStorage.setItem('current_task_id', taskId)
}

/** 从 sessionStorage 获取任务 ID */
export function getTaskId(): string | null {
  return sessionStorage.getItem('current_task_id')
}

/** 清除任务 ID */
export function clearTaskId(): void {
  sessionStorage.removeItem('current_task_id')
}
