<script setup lang="ts">
// =============================================================================
// 达人处理结果表格组件
// =============================================================================

import { computed } from 'vue'
import { useTaskStore } from '../../stores'

const taskStore = useTaskStore()

const creatorResults = computed(() => taskStore.creatorResults)
const hasResults = computed(() => creatorResults.value.length > 0)

const successCount = computed(() => 
  creatorResults.value.filter(r => r.status === 'success').length
)

const errorCount = computed(() => 
  creatorResults.value.filter(r => r.status === 'error').length
)

function getStatusType(status: string) {
  switch (status) {
    case 'success': return 'success'
    case 'error': return 'danger'
    case 'processing': return 'warning'
    default: return 'info'
  }
}

function getStatusText(status: string) {
  switch (status) {
    case 'success': return '成功'
    case 'error': return '失败'
    case 'processing': return '处理中'
    default: return '等待'
  }
}

function getPlatformType(platform: string) {
  switch (platform) {
    case 'bilibili': return 'primary'
    case 'douyin': return 'warning'
    case 'xiaohongshu': return 'danger'
    default: return 'info'
  }
}

function getPlatformText(platform: string) {
  switch (platform) {
    case 'bilibili': return 'B站'
    case 'douyin': return '抖音'
    case 'xiaohongshu': return '小红书'
    default: return platform || '未知'
  }
}
</script>

<template>
  <el-card shadow="hover" class="creator-card">
    <template #header>
      <div class="header-content">
        <span>达人处理详情</span>
        <span v-if="hasResults" class="summary">
          成功 {{ successCount }} | 失败 {{ errorCount }} | 共 {{ creatorResults.length }}
        </span>
      </div>
    </template>
    
    <el-empty v-if="!hasResults" description="暂无数据" />
    
    <el-table v-else :data="creatorResults" stripe size="small">
      <el-table-column prop="nickname" label="达人昵称" min-width="120" />
      <el-table-column prop="status" label="状态" width="80">
        <template #default="{ row }">
          <el-tag size="small" :type="getStatusType(row.status)">
            {{ getStatusText(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="matched_videos" label="匹配视频" width="80" align="center" />
      <el-table-column prop="error" label="备注" min-width="150" show-overflow-tooltip />
    </el-table>
  </el-card>
</template>

<style scoped>
.creator-card {
  margin-bottom: 16px;
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.summary {
  font-size: 13px;
  color: #909399;
}
</style>
