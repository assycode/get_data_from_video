// =============================================================================
// 类型定义 - 统一出口
// =============================================================================

export * from './task'
export * from './api'

// 通用类型
export interface ColumnConfig {
  label: string
  width?: number
  minWidth?: number
  align?: 'left' | 'center' | 'right'
}

export interface VideoItem {
  [key: string]: any
}

export type TaskStatus = 'idle' | 'planning' | 'running' | 'completed' | 'cancelled' | 'error'
