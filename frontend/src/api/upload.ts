// =============================================================================
// 文件上传 API
// =============================================================================

import { postForm } from './request'
import type { ExcelParseResponse, Creator } from '../types'

/** Excel 文件上传并解析 */
export async function uploadExcel(file: File): Promise<Creator[]> {
  const formData = new FormData()
  formData.append('file', file)
  
  const result = await postForm<ExcelParseResponse>('/api/upload-excel', formData)
  return result.creators || []
}
