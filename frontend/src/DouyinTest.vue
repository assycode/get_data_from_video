<script setup>
import { ref, reactive, computed } from 'vue'
import { fetchEventSource } from '@microsoft/fetch-event-source'
import * as XLSX from 'xlsx'
import { ElMessage } from 'element-plus'
import { UploadFilled, ArrowLeft } from '@element-plus/icons-vue'

// =============================================================================
// 响应式状态
// =============================================================================

const loading = ref(false)
const isPlanning = ref(false)
const abortController = ref(null)
const planAbortController = ref(null)
let isUserCancelled = false
let isStartingTask = false

const form = reactive({
  question: '获取这些抖音视频的数据，包括播放量、点赞、评论、分享',
  topic: '',
  startDate: '',
  file: null,
})

const fileList = ref([])
const parsedCreators = ref([])
const llmPlan = ref(null)
const result = reactive({
  totalCreators: 0,
  matchedVideos: 0,
  videos: [],
  exportFields: [],
})

const progress = reactive({
  completed: 0,
  total: 0,
  percent: 0,
})

const errorMsg = ref('')
const currentTaskId = ref('')

// =============================================================================
// 计算属性
// =============================================================================

const hasResult = computed(() => result.videos.length > 0)

const workflowSteps = computed(() => {
  if (!llmPlan.value || !llmPlan.value.workflows) return []
  const steps = []
  for (const [platform, wf] of Object.entries(llmPlan.value.workflows)) {
    steps.push({
      tool_name: `${platform} 平台`,
      reason: '',
      is_platform_header: true,
    })
    for (const s of (wf.tool_sequence || [])) {
      steps.push({
        tool_name: s.tool_name,
        reason: s.reason,
        is_detail: false,
        platform,
      })
    }
    if (wf.each_detail && wf.each_detail.need_query && wf.each_detail.tool_name) {
      steps.push({
        tool_name: wf.each_detail.tool_name,
        reason: `对 ${platform} 列表逐条调用 ${wf.each_detail.tool_name} 获取完整数据`,
        is_detail: true,
        platform,
      })
    }
  }
  return steps
})

// =============================================================================
// 文件上传
// =============================================================================

function handleFileChange(uploadFile) {
  form.file = uploadFile.raw
  previewExcel()
}

function handleFileRemove() {
  form.file = null
  fileList.value = []
  parsedCreators.value = []
}

async function previewExcel() {
  if (!form.file) return
  const data = new FormData()
  data.append('file', form.file)
  try {
    const res = await fetch('/api/upload-excel', { method: 'POST', body: data })
    const json = await res.json()
    if (json.code === 0) {
      parsedCreators.value = json.data.creators || []
      // 过滤出抖音平台的达人
      const douyinCreators = parsedCreators.value.filter(c => c.platform === 'douyin')
      ElMessage.success(`已解析 ${json.data.total} 个达人，其中抖音平台 ${douyinCreators.length} 个`)
    } else {
      ElMessage.error(json.message || '解析失败')
    }
  } catch (e) {
    ElMessage.error('Excel 解析请求失败')
  }
}

// =============================================================================
// 启动任务
// =============================================================================

async function startTask() {
  if (!form.file) { ElMessage.warning('请先上传 Excel'); return }
  if (!form.question.trim()) { ElMessage.warning('请输入抓取需求'); return }

  if (currentTaskId.value) {
    ElMessage.warning('已有任务在运行，请先等待完成或取消')
    return
  }

  if (isStartingTask) { return }
  if (loading.value) { ElMessage.warning('任务正在进行中，请勿重复点击'); return }

  isStartingTask = true
  isUserCancelled = false

  loading.value = true
  isPlanning.value = true
  llmPlan.value = null
  result.videos = []
  result.totalCreators = 0
  result.matchedVideos = 0
  progress.completed = 0
  progress.total = 0
  progress.percent = 0
  errorMsg.value = ''

  // Step 1: 先通过同步接口拿到 LLM 执行计划
  let plan = null
  try {
    planAbortController.value = new AbortController()
    const planRes = await fetch('/api/plan-task', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question: form.question,
        topic: form.topic,
        start_date: form.startDate,
        creators: parsedCreators.value,
      }),
      signal: planAbortController.value.signal,
    })
    const planJson = await planRes.json()
    if (!planRes.ok || planJson.code !== 0) {
      throw new Error(planJson.detail || planJson.message || '接口选型失败')
    }
    plan = planJson.plan
    llmPlan.value = plan
    ElMessage.success('AI 接口选型完成')
  } catch (e) {
    isStartingTask = false
    if (isUserCancelled || (planAbortController.value && planAbortController.value.signal.aborted)) {
      loading.value = false
      isPlanning.value = false
      planAbortController.value = null
      return
    }
    errorMsg.value = e.message || '接口选型失败'
    ElMessage.error(errorMsg.value)
    loading.value = false
    isPlanning.value = false
    planAbortController.value = null
    return
  }

  planAbortController.value = null
  isPlanning.value = false

  if (!form.file || !(form.file instanceof File)) {
    isStartingTask = false
    ElMessage.error('文件对象无效，请重新上传 Excel')
    loading.value = false
    return
  }

  // Step 2: POST /api/start-task 创建后台任务
  const startData = new FormData()
  startData.append('question', form.question)
  startData.append('file', form.file)
  if (form.topic) startData.append('topic', form.topic)
  if (form.startDate) startData.append('start_date', form.startDate)
  startData.append('plan_json', JSON.stringify(plan))

  let taskId
  try {
    const startRes = await fetch('/api/start-task', { method: 'POST', body: startData })
    const startJson = await startRes.json()
    if (!startRes.ok || startJson.code !== 0) {
      throw new Error(startJson.detail || startJson.message || '创建任务失败')
    }
    taskId = startJson.task_id
    currentTaskId.value = taskId
    ElMessage.success('任务已创建，开始批量抓取')
  } catch (e) {
    isStartingTask = false
    if (isUserCancelled) {
      loading.value = false
      return
    }
    errorMsg.value = e.message || '创建任务失败'
    ElMessage.error(errorMsg.value)
    loading.value = false
    return
  }

  connectSSE(taskId)
  isStartingTask = false
}

function connectSSE(taskId) {
  isUserCancelled = false
  abortController.value = new AbortController()

  fetchEventSource(`/api/task-progress/${taskId}`, {
    method: 'GET',
    signal: abortController.value.signal,
    openWhenHidden: true,
    onmessage(msg) {
      if (!msg.data) return
      try {
        const payload = JSON.parse(msg.data)
        handleEvent(payload)
      } catch (e) { console.warn('解析失败:', msg.data) }
    },
    onclose() {
      if (isUserCancelled) {
        return
      }
      loading.value = false
      throw new Error('SSE connection closed')
    },
    onerror(err) {
      if (isUserCancelled) {
        return
      }
      throw err
    },
  })
}

async function stopTask() {
  const taskId = currentTaskId.value
  isUserCancelled = true

  if (planAbortController.value) {
    planAbortController.value.abort()
    planAbortController.value = null
    loading.value = false
    isPlanning.value = false
    ElMessage.info('已取消规划')
    if (taskId) {
      try {
        const data = new FormData()
        data.append('task_id', taskId)
        await fetch('/api/cancel-task', { method: 'POST', body: data })
      } catch (e) {
        console.warn('取消请求失败:', e)
      }
    }
    return
  }

  if (abortController.value) {
    abortController.value.abort()
    abortController.value = null
  }

  if (taskId) {
    try {
      const data = new FormData()
      data.append('task_id', taskId)
      await fetch('/api/cancel-task', { method: 'POST', body: data })
    } catch (e) {
      console.warn('取消请求失败:', e)
    }
    currentTaskId.value = ''
  }
  loading.value = false
  isPlanning.value = false
  ElMessage.info('已取消')
}

function handleEvent(payload) {
  switch (payload.event) {
    case 'start':
      result.totalCreators = payload.content.total_creators || 0
      progress.total = payload.content.total_creators || 0
      break

    case 'thought':
      llmPlan.value = payload.content.plan
      break

    case 'progress':
      progress.completed = payload.content.completed || 0
      progress.total = payload.content.total || 0
      progress.percent = progress.total > 0
        ? Math.round((progress.completed / progress.total) * 100)
        : 0
      result.matchedVideos = payload.content.matched_so_far || 0
      break

    case 'final':
      result.matchedVideos = payload.content.matched_videos || 0
      if (payload.content.videos) {
        result.videos = payload.content.videos
      }
      if (payload.content.export_fields) {
        result.exportFields = payload.content.export_fields
      }
      break

    case 'error':
      errorMsg.value = payload.content.message || '未知错误'
      ElMessage.error(errorMsg.value)
      break

    case 'done':
      loading.value = false
      currentTaskId.value = ''
      break
  }
}

// =============================================================================
// 动态列配置（适配抖音字段）
// =============================================================================

const COLUMN_MAP = {
  creator_nickname: { label: '达人昵称', width: 120 },
  desc: { label: '标题/描述', minWidth: 200 },
  create_time: { label: '发布时间', width: 160 },
  duration: { label: '时长', width: 100 },
  aweme_id: { label: '视频ID', width: 160 },
  play_count: { label: '播放量', width: 100, align: 'right' },
  digg_count: { label: '点赞', width: 90, align: 'right' },
  comment_count: { label: '评论', width: 90, align: 'right' },
  share_count: { label: '分享', width: 90, align: 'right' },
  author_nickname: { label: '作者昵称', width: 120 },
  author_unique_id: { label: '抖音号', width: 120 },
  url: { label: '链接', width: 80 },
  text_extra: { label: '话题标签', minWidth: 150 },
}

const exportColumns = computed(() => {
  const fields = result.exportFields && result.exportFields.length
    ? result.exportFields
    : Object.keys(result.videos[0] || {})
  return fields.map(key => ({
    key,
    ...COLUMN_MAP[key],
  })).filter(col => col.label)
})

function formatCellValue(row, key) {
  const val = row[key]
  if (val === undefined || val === null) return '-'
  if (key === 'create_time' && typeof val === 'number') return formatDate(val)
  if (key === 'url') return val
  if (['play_count', 'digg_count', 'comment_count', 'share_count'].includes(key)) {
    return typeof val === 'number' ? val.toLocaleString() : val
  }
  if (key === 'text_extra' && Array.isArray(val)) {
    return val.slice(0, 3).map(t => t.hashtag_name || t).join('、') || '-'
  }
  if (key === 'duration' && typeof val === 'number') {
    // 抖音 duration 是毫秒，转为秒
    const seconds = Math.floor(val / 1000)
    const m = Math.floor(seconds / 60)
    const s = seconds % 60
    return m > 0 ? `${m}分${s}秒` : `${s}秒`
  }
  return val
}

function formatDate(ts) {
  if (!ts) return '-'
  const d = new Date(ts * 1000)
  return d.toLocaleString('zh-CN')
}

// =============================================================================
// 导出 Excel
// =============================================================================

function exportExcel() {
  if (!result.videos.length) { ElMessage.warning('没有可导出的数据'); return }
  const rows = result.videos.map(v => {
    const row = {}
    exportColumns.value.forEach(col => {
      row[col.label] = formatCellValue(v, col.key)
    })
    return row
  })
  const ws = XLSX.utils.json_to_sheet(rows)
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, '抖音数据')
  XLSX.writeFile(wb, `抖音数据抓取_${new Date().toLocaleDateString()}.xlsx`)
  ElMessage.success('导出成功')
}

// =============================================================================
// 返回主页
// =============================================================================

function goBack() {
  window.location.href = '/'
}
</script>

<template>
  <div class="app-container">
    <!-- 顶部 -->
    <header class="app-header">
      <div class="header-left">
        <el-button @click="goBack" :icon="ArrowLeft">返回主页面</el-button>
      </div>
      <h1>🎵 抖音接口测试</h1>
      <p class="subtitle">专门针对抖音平台的批量数据抓取测试页面</p>
    </header>

    <main class="app-main">
      <!-- 左侧：配置 -->
      <section class="config-section">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header"><span>任务配置</span></div>
          </template>

          <el-form label-position="top">
            <el-form-item label="抓取需求描述">
              <el-input v-model="form.question" type="textarea" :rows="3" />
            </el-form-item>

            <el-form-item label="达人列表（Excel）">
              <el-upload drag action="#" :auto-upload="false" :on-change="handleFileChange"
                :on-remove="handleFileRemove" :file-list="fileList" accept=".xlsx,.xls" :limit="1">
                <el-icon class="el-icon--upload"><upload-filled /></el-icon>
                <div class="el-upload__text">拖拽文件到此处或 <em>点击上传</em></div>
                <template #tip>
                  <div class="el-upload__tip">
                    支持 .xlsx / .xls<br>
                    <span style="color: #409eff;">需包含 aweme_id 或 sec_uid 列</span>
                  </div>
                </template>
              </el-upload>
            </el-form-item>

            <el-alert v-if="parsedCreators.length > 0"
              :title="`已解析 ${parsedCreators.length} 个达人（抖音平台 ${parsedCreators.filter(c => c.platform === 'douyin').length} 个）`"
              type="success" :closable="false" show-icon style="margin-bottom: 16px;" />

            <el-form-item>
              <el-button type="primary" size="large" :loading="loading" @click="startTask"
                :disabled="!form.file">
                {{ loading ? (isPlanning ? 'AI 正在规划...' : '抓取中...') : '开始抖音数据抓取' }}
              </el-button>
              <el-button v-if="loading" size="large" @click="stopTask">取消</el-button>
              <el-button v-if="hasResult" type="success" size="large" @click="exportExcel">
                导出 Excel
              </el-button>
            </el-form-item>
            <el-alert v-if="isPlanning" title="AI 正在进行接口选型，请稍候..." type="info" :closable="false" show-icon />
          </el-form>
        </el-card>

        <!-- 抖音平台说明 -->
        <el-card shadow="hover" style="margin-top: 16px;">
          <template #header>
            <div class="card-header"><span>📋 抖音平台字段说明</span></div>
          </template>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="aweme_id">抖音视频ID（必需）</el-descriptions-item>
            <el-descriptions-item label="sec_uid">用户加密ID（用于获取短链接）</el-descriptions-item>
            <el-descriptions-item label="uid">抖音数字UID（用于查直播间）</el-descriptions-item>
            <el-descriptions-item label="play_count">播放量</el-descriptions-item>
            <el-descriptions-item label="digg_count">点赞数</el-descriptions-item>
            <el-descriptions-item label="comment_count">评论数</el-descriptions-item>
            <el-descriptions-item label="share_count">分享数</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </section>

      <!-- 右侧：结果 -->
      <section class="result-section">
        <!-- 总体进度 -->
        <el-card v-if="loading || progress.total > 0" shadow="hover" class="progress-card">
          <div class="progress-info">
            <span>进度：{{ progress.completed }} / {{ progress.total }} 个达人</span>
            <span>已匹配 {{ result.matchedVideos }} 条视频</span>
          </div>
          <el-progress :percentage="progress.percent"
            :status="progress.percent === 100 ? 'success' : ''" :stroke-width="16" />
        </el-card>

        <!-- 错误提示 -->
        <el-alert v-if="errorMsg" :title="errorMsg" type="error" :closable="false" show-icon
          style="margin-bottom: 16px;" />

        <!-- LLM 计划 -->
        <el-card v-if="llmPlan" shadow="hover" class="plan-card">
          <template #header><span>AI 执行计划</span></template>
          <div v-if="llmPlan.reasoning" class="plan-reasoning">
            <strong>推理：</strong>{{ llmPlan.reasoning }}
          </div>
          <div v-if="llmPlan.global_filter" class="plan-filters">
            <el-tag type="primary">话题: {{ llmPlan.global_filter.topic || '无' }}</el-tag>
            <el-tag type="info">开始: {{ llmPlan.global_filter.start_date || '无' }}</el-tag>
          </div>
          <div v-if="llmPlan.workflows" style="margin-top: 12px;">
            <div style="font-weight: 600; margin-bottom: 8px;">工作流</div>
            <el-timeline v-if="workflowSteps.length">
              <el-timeline-item
                v-for="(step, idx) in workflowSteps"
                :key="idx"
                :type="step.is_detail ? 'warning' : (step.is_platform_header ? 'success' : '')"
              >
                <template v-if="step.is_platform_header">
                  <el-tag type="success" size="small">{{ step.tool_name }}</el-tag>
                </template>
                <template v-else>
                  <strong>{{ step.tool_name }}</strong>
                  <el-tag v-if="step.is_detail" size="small" type="warning" style="margin-left: 8px;">逐条</el-tag>
                  <p style="margin: 4px 0 0; color: #666; font-size: 13px;">{{ step.reason }}</p>
                </template>
              </el-timeline-item>
            </el-timeline>
          </div>
        </el-card>

        <!-- 结果表格 -->
        <el-card v-if="hasResult" shadow="hover" class="result-table-card">
          <template #header>
            <div class="table-header">
              <span>抓取结果（共 {{ result.matchedVideos }} 条）</span>
              <el-button type="primary" size="small" @click="exportExcel">导出 Excel</el-button>
            </div>
          </template>
          <el-table :data="result.videos" stripe border height="500" style="width: 100%;" v-if="exportColumns.length">
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
                <span v-else-if="col.key === 'text_extra' && Array.isArray(row.text_extra)">
                  <el-tag v-for="tag in row.text_extra.slice(0, 3)" :key="tag.hashtag_name || tag" size="small" style="margin-right: 4px;">
                    {{ tag.hashtag_name || tag }}
                  </el-tag>
                </span>
                <span v-else>{{ formatCellValue(row, col.key) }}</span>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="暂无数据字段可展示" />
        </el-card>

        <!-- 空状态 -->
        <el-empty v-if="!loading && !hasResult"
          description="上传包含抖音 aweme_id 的 Excel 并点击「开始抖音数据抓取」" />
      </section>
    </main>
  </div>
</template>

<style scoped>
.app-container { min-height: 100vh; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: #fff; }
.app-header { text-align: center; padding: 24px 20px; background: rgba(0,0,0,0.3); border-bottom: 1px solid rgba(255,255,255,0.1); position: relative; }
.header-left { position: absolute; left: 20px; top: 50%; transform: translateY(-50%); }
.app-header h1 { margin: 0; font-size: 28px; color: #fff; font-weight: 600; }
.app-header .subtitle { margin: 8px 0 0; color: #a0a0a0; font-size: 14px; }
.app-main { max-width: 1400px; margin: 0 auto; padding: 24px; display: grid; grid-template-columns: 420px 1fr; gap: 24px; }
@media (max-width: 1024px) { .app-main { grid-template-columns: 1fr; } }
.config-section { position: sticky; top: 24px; align-self: start; }
.card-header { font-weight: 600; font-size: 16px; }
.progress-card { margin-bottom: 16px; }
.progress-info { display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 14px; }
.plan-card { margin-bottom: 16px; }
.plan-reasoning { background: rgba(64, 158, 255, 0.1); border-left: 4px solid #409eff; padding: 12px 16px; margin-bottom: 12px; border-radius: 4px; font-size: 14px; }
.plan-filters { margin-bottom: 12px; }
.plan-filters .el-tag { margin-right: 8px; }
.result-table-card { margin-bottom: 24px; }
.table-header { display: flex; justify-content: space-between; align-items: center; }
</style>
