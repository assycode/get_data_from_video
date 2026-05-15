<script setup lang="ts">
// =============================================================================
// 主页面 - 批量数据抓取助手
// =============================================================================

import { onMounted, computed, ref, nextTick } from 'vue'

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

// 保存当前解析的达人列表（从 FileUploader 事件传递）
const currentCreators = ref<any[]>([])

// 延迟初始化 store 和 task composable（确保 Pinia 已就绪）
const taskStore = ref<ReturnType<typeof useTaskStore> | null>(null)
const resultStore = ref<ReturnType<typeof useResultStore> | null>(null)
const task = ref<ReturnType<typeof useTask> | null>(null)

// 计算属性：传递给子组件的数据（使用可选链保护）
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

// 独立计算属性用于 llmPlan，避免可选链问题
const llmPlanData = computed(() => {
  const plan = taskStore.value?.llmPlan
  console.log('[Home] llmPlanData:', plan ? '有数据' : '无数据', plan)
  return plan ?? null
})

const resultData = computed(() => ({
  videos: resultStore.value?.videos ?? [],
  exportColumns: resultStore.value?.exportColumns ?? [],
  exportFields: resultStore.value?.exportFields ?? [],
  matchedVideos: resultStore.value?.matchedVideos ?? 0,
  hasResult: resultStore.value?.hasResult ?? false,
}))
const { parseExcel, exportExcel } = excel

// ============================================================================
// 事件处理
// ============================================================================

async function handleFileChange(file: File) {
  await parseExcel(file)
}

function handleFileParsed(creators: any[]) {
  // FileUploader 解析完成后保存 creators
  currentCreators.value = creators
  console.log('[Home] File parsed, creators count:', creators.length)
}

async function handleTaskSubmit(form: {
  question: string
  topic: string
  startDate: string
  file: File | null
}) {
  if (!form.file) return
  if (!task.value) {
    alert('系统尚未初始化完成，请刷新页面后再试')
    return
  }
  // 从 currentCreators 中获取已解析的达人列表（从 FileUploader 传递过来）
  const creators = currentCreators.value
  if (!creators || creators.length === 0) {
    alert('请先上传并解析Excel文件')
    return
  }
  await task.value.startTask(form.file, form.question, form.topic, form.startDate, creators)
}

function handleCancel() {
  task.value?.cancel()
}

function handleExport() {
  // 导出功能在 ResultTable 组件中已实现
}

// ============================================================================
// 生命周期
// ============================================================================

onMounted(() => {
  initializeApp()
})

async function initializeApp() {
  // 等待下一个 tick，确保 Pinia 已就绪
  await nextTick()
  
  try {
    // 延迟初始化 store 和 task composable（确保 Pinia 已就绪）
    taskStore.value = useTaskStore()
    resultStore.value = useResultStore()
    task.value = useTask({}, taskStore.value, resultStore.value)
    
    task.value?.resumeTask()
  } catch (e) {
    console.error('[Home] initialization error:', e)
    // 延迟重试
    setTimeout(initializeApp, 500)
  }
}
</script>

<template>
  <div class="app-container">
    <AppHeader
      title="AI 批量数据抓取助手"
      subtitle="上传达人 Excel → AI 自动规划 → 批量抓取 → 话题过滤 → 导出结果"
    />

    <main class="app-main">
      <!-- 左侧：配置 -->
      <section class="config-section">
        <TaskConfig
          :is-running="progressData.isRunning"
          :is-planning="progressData.isPlanning"
          @submit="handleTaskSubmit"
          @cancel="handleCancel"
          @fileParsed="handleFileParsed"
        />
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
        <WorkflowTimeline :llm-plan="llmPlanData" />
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
  background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%);
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
</style>
