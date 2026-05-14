<script setup lang="ts">
// =============================================================================
// 小红书测试页
// =============================================================================

import { onMounted, computed, ref, nextTick } from 'vue'
import { ArrowLeft } from '@element-plus/icons-vue'

// Composables
import { useTask, useExcel } from '../composables'
import { useTaskStore, useResultStore } from '../stores'

// Components
import {
  AppHeader,
  ProgressCard,
  WorkflowTimeline,
  ResultTable,
} from '../components/common'
import { TaskConfig } from '../components/business'

// 使用 Excel composable（不涉及 store）
const excel = useExcel()

// 延迟初始化 store 和 task composable（确保 Pinia 已就绪）
const taskStore = ref<ReturnType<typeof useTaskStore> | null>(null)
const resultStore = ref<ReturnType<typeof useResultStore> | null>(null)
const task = ref<ReturnType<typeof useTask> | null>(null)

// 计算属性：传递给子组件的数据
const progressData = computed(() => ({
  isRunning: taskStore.value?.isRunning ?? false,
  isPlanning: taskStore.value?.isPlanning ?? false,
  total: taskStore.value?.progress.total ?? 0,
  completed: taskStore.value?.progress.completed ?? 0,
  successCount: taskStore.value?.successCount ?? 0,
  errorCount: taskStore.value?.errorCount ?? 0,
  matchedVideos: resultStore.value?.matchedVideos ?? 0,
  percent: taskStore.value?.progress.percent ?? 0,
}))

const resultData = computed(() => ({
  videos: resultStore.value?.videos ?? [],
  exportColumns: resultStore.value?.exportColumns ?? [],
  exportFields: resultStore.value?.exportFields ?? [],
  matchedVideos: resultStore.value?.matchedVideos ?? 0,
  hasResult: resultStore.value?.hasResult ?? false,
}))

// 存储解析后的达人列表
const parsedCreators = ref<any[]>([])

// ============================================================================
// 事件处理
// ============================================================================

function handleFileParsed(creators: any[]) {
  parsedCreators.value = creators
}

async function handleTaskSubmit(form: {
  question: string
  topic: string
  startDate: string
  file: File | null
}) {
  if (!form.file) return
  const creators = parsedCreators.value
  if (creators.length === 0) {
    alert('请先上传有效的 Excel 文件')
    return
  }
  if (!task.value) {
    alert('系统尚未初始化完成，请刷新页面后再试')
    console.error('[XiaoHongShuTest] task.value is null, initialization may have failed')
    return
  }
  await task.value.startTask(form.file, form.question, form.topic, form.startDate, creators)
}

function handleCancel() {
  task.value?.cancel()
}

function goBack() {
  window.location.href = '/'
}

// ============================================================================
// 生命周期
// ============================================================================

onMounted(() => {
  console.log('[XiaoHongShuTest] onMounted starting...')
  // 延迟一点执行，确保 Pinia 已就绪
  setTimeout(() => {
    initializeApp()
  }, 100)
})

async function initializeApp() {
  // 等待下一个 tick，确保 Pinia 已就绪
  await nextTick()
  
  try {
    console.log('[XiaoHongShuTest] initializing...')
    
    // 延迟初始化 store 和 task composable（确保 Pinia 已就绪）
    taskStore.value = useTaskStore()
    console.log('[XiaoHongShuTest] taskStore initialized:', !!taskStore.value)
    
    resultStore.value = useResultStore()
    console.log('[XiaoHongShuTest] resultStore initialized:', !!resultStore.value)
    
    task.value = useTask({ platform: 'xiaohongshu' }, taskStore.value, resultStore.value)
    console.log('[XiaoHongShuTest] task composable initialized:', !!task.value)
    
    task.value?.resumeTask()
    console.log('[XiaoHongShuTest] resumeTask called')
  } catch (e) {
    console.error('[XiaoHongShuTest] initialization error:', e)
    // 延迟重试
    console.log('[XiaoHongShuTest] retrying initialization in 500ms...')
    setTimeout(initializeApp, 500)
  }
}
</script>

<template>
  <div class="app-container">
    <AppHeader
      title="📕 小红书接口测试"
      subtitle="专门针对小红书平台的批量数据抓取测试页面"
    >
      <template #default>
        <div class="header-left">
          <el-button @click="goBack" :icon="ArrowLeft">返回主页面</el-button>
        </div>
      </template>
    </AppHeader>

    <main class="app-main">
      <!-- 左侧：配置 -->
      <section class="config-section">
        <TaskConfig
          @submit="handleTaskSubmit"
          @cancel="handleCancel"
          @file-parsed="handleFileParsed"
        />

        <!-- 显示已解析的达人数量 -->
        <el-alert 
          v-if="parsedCreators.length > 0"
          :title="`已解析 ${parsedCreators.length} 个达人`" 
          type="success" 
          :closable="false" 
          show-icon
          style="margin-top: 12px;"
        />

        <!-- 小红书平台说明 -->
        <el-card shadow="hover" style="margin-top: 16px;">
          <template #header>
            <div class="card-header"><span>📋 小红书平台字段说明</span></div>
          </template>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="user_id">小红书用户ID（必需）</el-descriptions-item>
            <el-descriptions-item label="note_id">笔记ID（用于获取笔记详情）</el-descriptions-item>
            <el-descriptions-item label="readNum">阅读量</el-descriptions-item>
            <el-descriptions-item label="likeNum">点赞数</el-descriptions-item>
            <el-descriptions-item label="collectNum">收藏数</el-descriptions-item>
            <el-descriptions-item label="cmtNum">评论数</el-descriptions-item>
            <el-descriptions-item label="shareNum">分享数</el-descriptions-item>
            <el-descriptions-item label="followCnt">涨粉数</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </section>

      <!-- 右侧：结果 -->
      <section class="result-section">
        <ProgressCard
          :is-running="progressData.isRunning"
          :is-planning="progressData.isPlanning"
          :total="progressData.total"
          :completed="progressData.completed"
          :success-count="progressData.successCount"
          :error-count="progressData.errorCount"
          :matched-videos="progressData.matchedVideos"
          :percent="progressData.percent"
        />
        <WorkflowTimeline :llm-plan="taskStore?.llmPlan ?? null" />
        <ResultTable
          :videos="resultData.videos"
          :export-columns="resultData.exportColumns"
          :export-fields="resultData.exportFields"
          :matched-videos="resultData.matchedVideos"
          :has-result="resultData.hasResult"
        />
      </section>
    </main>
  </div>
</template>

<style scoped>
.app-container {
  min-height: 100vh;
  background: linear-gradient(135deg, #ff2442 0%, #ff6b81 100%);
  color: #fff;
}

::deep(.app-header) {
  background: rgba(0, 0, 0, 0.3);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

::deep(.app-header h1) {
  color: #fff;
}

::deep(.app-header .subtitle) {
  color: #ffe0e6;
}

.header-left {
  position: absolute;
  left: 20px;
  top: 50%;
  transform: translateY(-50%);
}

.app-main {
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px;
  display: grid;
  grid-template-columns: 420px 1fr;
  gap: 24px;
}

@media (max-width: 1024px) {
  .app-main {
    grid-template-columns: 1fr;
  }
}

.config-section {
  position: sticky;
  top: 24px;
  align-self: start;
}

.card-header {
  font-weight: 600;
  font-size: 16px;
}
</style>
