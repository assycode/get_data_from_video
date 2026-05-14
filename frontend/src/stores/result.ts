// =============================================================================
// 结果数据管理 (Pinia)
// =============================================================================

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { VideoItem, ColumnConfig } from '../types'
import { COLUMN_MAP } from '../utils'

export const useResultStore = defineStore('result', () => {
  // ==========================================================================
  // State
  // ==========================================================================
  
  const videos = ref<VideoItem[]>([])
  const exportFields = ref<string[]>([])
  const totalCreators = ref(0)
  const matchedVideos = ref(0)

  // ==========================================================================
  // Getters
  // ==========================================================================
  
  const hasResult = computed(() => videos.value.length > 0)
  
  const exportColumns = computed(() => {
    const fields = exportFields.value.length > 0
      ? exportFields.value
      : Object.keys(videos.value[0] || {})
    
    return fields
      .map(key => ({
        key,
        ...COLUMN_MAP[key],
      }))
      .filter(col => col.label) as (ColumnConfig & { key: string })[]
  })

  // ==========================================================================
  // Actions
  // ==========================================================================
  
  function setVideos(data: VideoItem[]) {
    videos.value = data
  }

  function setExportFields(fields: string[]) {
    exportFields.value = fields
  }

  function setTotalCreators(count: number) {
    totalCreators.value = count
  }

  function setMatchedVideos(count: number) {
    matchedVideos.value = count
  }

  function appendVideos(newVideos: VideoItem[]) {
    videos.value.push(...newVideos)
  }

  function reset() {
    videos.value = []
    exportFields.value = []
    totalCreators.value = 0
    matchedVideos.value = 0
  }

  // ==========================================================================
  // Return
  // ==========================================================================
  return {
    // State
    videos,
    exportFields,
    totalCreators,
    matchedVideos,
    // Getters
    hasResult,
    exportColumns,
    // Actions
    setVideos,
    setExportFields,
    setTotalCreators,
    setMatchedVideos,
    appendVideos,
    reset,
  }
})
