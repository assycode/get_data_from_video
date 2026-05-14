// =============================================================================
// 格式化工具函数
// =============================================================================

/** 格式化日期戳 */
export function formatDate(ts: number): string {
  if (!ts) return '-'
  const d = new Date(ts * 1000)
  return d.toLocaleString('zh-CN')
}

/** 格式化时长（秒） */
export function formatDuration(seconds: number): string {
  if (!seconds && seconds !== 0) return '-'
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return m > 0 ? `${m}分${s}秒` : `${s}秒`
}

/** 格式化抖音时长（毫秒转秒） */
export function formatDouyinDuration(ms: number): string {
  if (!ms && ms !== 0) return '-'
  const seconds = Math.floor(ms / 1000)
  return formatDuration(seconds)
}

/** 格式化数字 */
export function formatNumber(val: number): string {
  if (val === undefined || val === null) return '-'
  return typeof val === 'number' ? val.toLocaleString() : String(val)
}

/** 格式化标签数组 */
export function formatTags(tags: any[], maxCount = 3): string {
  if (!Array.isArray(tags) || tags.length === 0) return '-'
  return tags.slice(0, maxCount).map(t => t.tag_name || t.hashtag_name || t).join('、')
}

/** 格式化处理空值 */
export function formatValue(val: any): string {
  if (val === undefined || val === null) return '-'
  return String(val)
}
