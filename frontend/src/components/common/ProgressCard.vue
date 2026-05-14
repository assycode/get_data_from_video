<script setup lang="ts">
// =============================================================================
// 进度卡片组件
// =============================================================================

import { Loading } from '@element-plus/icons-vue'

interface Props {
  isRunning?: boolean
  isPlanning?: boolean
  total?: number
  completed?: number
  successCount?: number
  errorCount?: number
  matchedVideos?: number
  percent?: number
}

withDefaults(defineProps<Props>(), {
  isRunning: false,
  isPlanning: false,
  total: 0,
  completed: 0,
  successCount: 0,
  errorCount: 0,
  matchedVideos: 0,
  percent: 0,
})
</script>

<template>
  <el-card v-if="isRunning || isPlanning || total > 0" shadow="hover" class="progress-card">
    <!-- AI 规划状态 -->
    <div v-if="isPlanning" class="planning-status">
      <el-icon class="is-loading"><loading /></el-icon>
      <span>AI 正在进行接口选型...</span>
    </div>
    
    <!-- 进度信息 -->
    <template v-else>
      <div class="progress-info">
        <span>进度：{{ completed }} / {{ total }} 个达人</span>
        <span>
          成功 {{ successCount }} | 
          失败 {{ errorCount }} | 
          已匹配 {{ matchedVideos }} 条视频
        </span>
      </div>
      <el-progress 
        :percentage="percent"
        :status="percent === 100 ? 'success' : ''" 
        :stroke-width="16" 
      />
    </template>
  </el-card>
</template>

<style scoped>
.progress-card {
  margin-bottom: 16px;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 14px;
  color: #606266;
}

.planning-status {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  color: #409eff;
  font-size: 14px;
}

.planning-status .el-icon {
  font-size: 18px;
}

.is-loading {
  animation: rotating 2s linear infinite;
}

@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
