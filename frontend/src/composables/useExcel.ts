// =============================================================================
// Excel 处理 Composable
// =============================================================================

import { ref } from 'vue'
import * as XLSX from 'xlsx'
import { ElMessage } from 'element-plus'
import type { Creator, VideoItem, ColumnConfig } from '../types'
import { uploadExcel } from '../api'
import { formatDate, formatNumber, formatDouyinDuration, formatTags, formatValue } from '../utils'

export function useExcel() {
  const fileList = ref<File[]>([])
  const parsedCreators = ref<Creator[]>([])
  const isParsing = ref(false)

  /**
   * 解析 Excel 文件
   */
  async function parseExcel(file: File): Promise<Creator[]> {
    isParsing.value = true
    try {
      const creators = await uploadExcel(file)
      parsedCreators.value = creators
      fileList.value = [file]
      ElMessage.success(`已解析 ${creators.length} 个达人`)
      return creators
    } catch (e) {
      ElMessage.error('Excel 解析失败')
      throw e
    } finally {
      isParsing.value = false
    }
  }

  /**
   * 清除文件
   */
  function clearFile() {
    fileList.value = []
    parsedCreators.value = []
  }

  /**
   * 导出 Excel
   */
  function exportExcel(
    videos: VideoItem[],
    columns: (ColumnConfig & { key: string })[],
    fileName: string
  ) {
    if (!videos.length) {
      ElMessage.warning('没有可导出的数据')
      return
    }

    const rows = videos.map(v => {
      const row: Record<string, any> = {}
      columns.forEach(col => {
        row[col.label] = formatCellValue(v, col.key)
      })
      return row
    })

    const ws = XLSX.utils.json_to_sheet(rows)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, '抓取结果')
    XLSX.writeFile(wb, fileName)
    ElMessage.success('导出成功')
  }

  /**
   * 格式化单元格值（用于导出）
   */
  function formatCellValue(row: VideoItem, key: string): string {
    const val = row[key]
    if (val === undefined || val === null) return '-'

    // 发布时间
    if ((key === 'pubdate' || key === 'create_time') && typeof val === 'number') {
      return formatDate(val)
    }

    // 链接
    if (key === 'url') return val || '-'

    // 数字统计
    if (['view', 'danmaku', 'reply', 'favorite', 'coin', 'share', 'like',
         'follower', 'following', 'play_count', 'digg_count', 'comment_count', 'share_count'].includes(key)) {
      return formatNumber(val)
    }

    // 标签数组
    if ((key === 'tags' || key === 'text_extra') && Array.isArray(val)) {
      return formatTags(val)
    }

    // 话题数组
    if (key === 'participle' && Array.isArray(val)) {
      return val.join('、') || '-'
    }

    // 时长
    if (key === 'duration') {
      // 抖音是毫秒，B站是秒
      if (val > 10000) {
        return formatDouyinDuration(val)
      }
      const m = Math.floor(val / 60)
      const s = val % 60
      return m > 0 ? `${m}分${s}秒` : `${s}秒`
    }

    return formatValue(val)
  }

  return {
    fileList,
    parsedCreators,
    isParsing,
    parseExcel,
    clearFile,
    exportExcel,
    formatCellValue,
  }
}
