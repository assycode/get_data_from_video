<script setup lang="ts">
// =============================================================================
// 结果表格组件
// =============================================================================

import { useExcel } from '../../composables'
import { generateExportFileName } from '../../utils'
import { computed } from 'vue'
import type { ExportColumn } from '../../types'

interface Props {
  videos?: any[]
  exportColumns?: ExportColumn[]
  exportFields?: string[]
  matchedVideos?: number
  hasResult?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  videos: () => [],
  exportColumns: () => [],
  exportFields: () => [],
  matchedVideos: 0,
  hasResult: false,
})

const emit = defineEmits<{
  export: []
}>()

const { formatCellValue } = useExcel()

function exportData() {
  const { exportExcel } = useExcel()
  exportExcel(
    props.videos,
    props.exportColumns,
    generateExportFileName('抓取结果')
  )
  emit('export')
}

// 调试信息
const debugInfo = computed(() => {
  return {
    videosCount: props.videos.length,
    exportFields: props.exportFields,
    exportColumns: props.exportColumns.map(c => c.key),
    firstVideoKeys: props.videos[0] ? Object.keys(props.videos[0]) : []
  }
})

// 打印到控制台
console.log('[ResultTable] Debug:', debugInfo.value)
</script>

<template>
  <el-card v-if="hasResult" shadow="hover" class="result-table-card">
    <template #header>
      <div class="table-header">
        <span>抓取结果（共 {{ matchedVideos }} 条）</span>
        <el-button type="primary" size="small" @click="exportData">导出 Excel</el-button>
      </div>
    </template>
    
    <!-- 调试信息 -->
    <el-alert 
      :title="`调试: exportFields=${exportFields.length}个, columns=${exportColumns.length}个`" 
      type="info" 
      :closable="false"
      style="margin-bottom: 12px;"
    />
    <div style="font-size: 12px; color: #666; margin-bottom: 12px;">
      <div>视频字段: {{ debugInfo.firstVideoKeys.join(', ') }}</div>
      <div>表格列: {{ debugInfo.exportColumns.join(', ') }}</div>
    </div>
    
    <el-table 
      :data="videos" 
      stripe 
      border 
      height="500" 
      style="width: 100%;" 
      v-if="exportColumns.length"
    >
      <el-table-column type="index" width="50" />
      <el-table-column
        v-for="col in exportColumns"
        :key="col.key"
        :prop="col.key"
        :label="col.label"
        :width="col.width"
        :min-width="col.minWidth"
        :align="col.align || 'left'"
        show-overflow-tooltip
      >
        <template #default="{ row }">
          <span v-if="col.key === 'url'">
            <el-link :href="row.url" target="_blank" type="primary">查看</el-link>
          </span>
          <span v-else-if="(col.key === 'tags' || col.key === 'text_extra') && Array.isArray(row[col.key])">
            <el-tag 
              v-for="tag in row[col.key].slice(0, 3)" 
              :key="tag.tag_name || tag.hashtag_name || tag" 
              size="small" 
              style="margin-right: 4px;"
            >
              {{ tag.tag_name || tag.hashtag_name || tag }}
            </el-tag>
          </span>
          <span v-else>{{ formatCellValue(row, col.key) }}</span>
        </template>
      </el-table-column>
    </el-table>
    
    <el-empty v-else description="暂无数据字段可展示" />
  </el-card>
</template>

<style scoped>
.result-table-card {
  margin-bottom: 24px;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
