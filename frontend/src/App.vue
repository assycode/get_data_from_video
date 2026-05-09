<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { fetchEventSource } from '@microsoft/fetch-event-source'
import * as XLSX from 'xlsx'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'

// =============================================================================
// 响应式状态
// =============================================================================

const loading = ref(false)
const isPlanning = ref(false)
// SSE 连接的 AbortController（批量抓取阶段）
const abortController = ref(null)
// plan-task 请求的 AbortController（规划阶段）
const planAbortController = ref(null)
// 页面恢复轮询定时器
let recoveryPollingTimer = null
// 防止重复启动任务（fetchEventSource 内部 retry 或用户快速双击）
let isStartingTask = false
// 标记是否用户主动点击了取消（用于 SSE onclose 判断，避免依赖 abortController）
let isUserCancelled = false

const form = reactive({
  question: '抓取这些达人发布的带星布谷地话题的视频，从2026年4月21日开始',
  topic: '星布谷地',
  startDate: '2026-04-21',
  file: null,
})

const fileList = ref([])
const parsedCreators = ref([])

// LLM 计划
const llmPlan = ref(null)

// 每个达人的处理结果
const creatorResults = ref([])

// 最终结果
const result = reactive({
  totalCreators: 0,
  matchedVideos: 0,
  videos: [],
  exportFields: [],
})

// 进度
const progress = reactive({
  completed: 0,
  total: 0,
  percent: 0,
})

// 错误信息
const errorMsg = ref('')

// 当前任务 ID（用于取消和恢复）
const currentTaskId = ref('')


// =============================================================================
// 计算属性
// =============================================================================

const hasResult = computed(() => result.videos.length > 0)

const successCount = computed(() => creatorResults.value.filter(r => r.status === 'success').length)
const errorCount = computed(() => creatorResults.value.filter(r => r.status === 'error').length)

// 工作流步骤：把 tool_sequence + each_detail 合并为一个完整的步骤列表，用于时间线展示
const workflowSteps = computed(() => {
  if (!llmPlan.value || !llmPlan.value.workflow) return []
  const wf = llmPlan.value.workflow
  const steps = (wf.tool_sequence || []).map(s => ({
    tool_name: s.tool_name,
    reason: s.reason,
    is_detail: false,
  }))
  // 如果启用了逐条详情，把 each_detail 作为独立步骤追加到时间线末尾
  if (wf.each_detail && wf.each_detail.need_query && wf.each_detail.tool_name) {
    steps.push({
      tool_name: wf.each_detail.tool_name,
      reason: `对列表中每条记录逐条调用 ${wf.each_detail.tool_name} 获取完整数据（标签、话题、详细统计等）`,
      is_detail: true,
    })
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
      ElMessage.success(`已解析 ${json.data.total} 个达人`)
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

  // 强防护 1：如果当前已有任务在跑（currentTaskId 存在），直接拒绝
  if (currentTaskId.value) {
    ElMessage.warning('已有任务在运行，请先等待完成或取消')
    return
  }
  // 强防护 2：如果 sessionStorage 里还存着未完成的任务（页面刷新过），让 onMounted 恢复逻辑处理，不要新建
  const savedTaskId = sessionStorage.getItem('current_task_id')
  if (savedTaskId) {
    ElMessage.info('检测到未完成的任务，正在自动恢复进度...')
    return
  }
  // 强防护 3：防止快速重复点击或 fetchEventSource 内部 retry 导致重复进入
  if (isStartingTask) { return }
  if (loading.value) { ElMessage.warning('任务正在进行中，请勿重复点击'); return }

  isStartingTask = true
  isUserCancelled = false

  // 重置
  loading.value = true
  isPlanning.value = true
  llmPlan.value = null
  creatorResults.value = []
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
    // 用户主动取消时（stopTask 已设置 isUserCancelled），静默处理
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

  // Step 2: 校验 file
  if (!form.file || !(form.file instanceof File)) {
    isStartingTask = false
    ElMessage.error('文件对象无效，请重新上传 Excel')
    loading.value = false
    return
  }

  // Step 3: POST /api/start-task 创建后台任务
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
    sessionStorage.setItem('current_task_id', taskId)
    ElMessage.success('任务已创建，开始批量抓取')
  } catch (e) {
    isStartingTask = false
    // 用户主动取消时静默处理
    if (isUserCancelled) {
      loading.value = false
      return
    }
    errorMsg.value = e.message || '创建任务失败'
    ElMessage.error(errorMsg.value)
    loading.value = false
    return
  }

  // Step 4: 开 SSE 接收进度
  connectSSE(taskId)
  isStartingTask = false
}

function connectSSE(taskId) {
  isUserCancelled = false
  abortController.value = new AbortController()

  fetchEventSource(`/api/task-progress/${taskId}`, {
    method: 'GET',
    signal: abortController.value.signal,
    // 页面切换到后台时保持连接
    openWhenHidden: true,
    onmessage(msg) {
      if (!msg.data) return
      try {
        const payload = JSON.parse(msg.data)
        handleEvent(payload)
      } catch (e) { console.warn('解析失败:', msg.data) }
    },
    onclose() {
      // 主动取消：静默关闭，不 throw（避免错误冒泡到页面）
      if (isUserCancelled) {
        return
      }
      // 非主动断开 → 切换到轮询
      if (currentTaskId.value && !recoveryPollingTimer) {
        ElMessage.info('连接已断开，自动切换为进度轮询模式')
        startPolling(currentTaskId.value)
      } else {
        loading.value = false
      }
      // 非主动断开时 throw，阻止 fetchEventSource 自动重试
      throw new Error('SSE connection closed')
    },
    onerror(err) {
      // 主动取消时静默处理，不报红字
      if (isUserCancelled) {
        return
      }
      throw err
    },
  })
}

function connectResumeSSE(taskId) {
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
      if (currentTaskId.value && !recoveryPollingTimer) {
        ElMessage.info('连接已断开，自动切换为进度轮询模式')
        startPolling(currentTaskId.value)
      } else {
        loading.value = false
      }
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

function startPolling(taskId) {
  if (recoveryPollingTimer) return
  recoveryPollingTimer = setInterval(async () => {
    try {
      const pollRes = await fetch(`/api/task-status?task_id=${taskId}`)
      const pollJson = await pollRes.json()
      if (!pollRes.ok || pollJson.code !== 0) {
        clearInterval(recoveryPollingTimer)
        recoveryPollingTimer = null
        loading.value = false
        sessionStorage.removeItem('current_task_id')
        return
      }
      const d = pollJson.data
      progress.completed = d.completed || 0
      progress.total = d.total || 0
      progress.percent = progress.total > 0
        ? Math.round((progress.completed / progress.total) * 100)
        : 0
      result.matchedVideos = d.matched_so_far || 0
      result.totalCreators = d.total || 0
      if (d.videos && d.videos.length > 0) {
        result.videos = d.videos
      }
      const s = d.status || ''
      if (s === 'completed' || s === 'cancelled' || s === 'done') {
        clearInterval(recoveryPollingTimer)
        recoveryPollingTimer = null
        loading.value = false
        currentTaskId.value = ''
        sessionStorage.removeItem('current_task_id')
        if (s === 'completed') {
          ElMessage.success('任务已完成！')
        } else if (s === 'cancelled') {
          ElMessage.info('任务已取消')
        }
      }
    } catch (e) {
      console.warn('轮询失败:', e)
    }
  }, 2000)
}

async function stopTask() {
  // 统一获取 task_id（currentTaskId 优先，其次 sessionStorage）
  const taskId = currentTaskId.value || sessionStorage.getItem('current_task_id')

  // 标记用户主动取消（必须在 abort 之前设置，供 onclose/onerror 读取）
  isUserCancelled = true

  // ---- 阶段 1：规划阶段（LLM 选型）正在进行中 ----
  if (planAbortController.value) {
    planAbortController.value.abort()
    planAbortController.value = null
    loading.value = false
    isPlanning.value = false
    ElMessage.info('已取消规划')
    // 即使规划阶段，如果已经有 task_id 也通知后端取消
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

  // ---- 阶段 2：批量抓取阶段（SSE 已建立或在轮询中） ----
  // 先断开 SSE（触发 onclose），再通知后端取消
  if (abortController.value) {
    abortController.value.abort()
    abortController.value = null
  }
  // 停止恢复轮询（如果有）
  if (recoveryPollingTimer) {
    clearInterval(recoveryPollingTimer)
    recoveryPollingTimer = null
  }
  // 通知后端取消任务
  if (taskId) {
    try {
      const data = new FormData()
      data.append('task_id', taskId)
      await fetch('/api/cancel-task', { method: 'POST', body: data })
    } catch (e) {
      console.warn('取消请求失败:', e)
    }
    currentTaskId.value = ''
    sessionStorage.removeItem('current_task_id')
  }
  loading.value = false
  isPlanning.value = false
  ElMessage.info('已取消')
}

// =============================================================================
// SSE 事件处理
// =============================================================================

function handleEvent(payload) {
  switch (payload.event) {
    case 'start':
      // 兼容旧模式（新架构下 SSE 不再推送 start，但保留以防万一）
      result.totalCreators = payload.content.total_creators || 0
      progress.total = payload.content.total_creators || 0
      if (payload.content.task_id) {
        currentTaskId.value = payload.content.task_id
        sessionStorage.setItem('current_task_id', payload.content.task_id)
      }
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

    case 'resume':
      // 刷新恢复 / SSE 首次连接：从后端缓存恢复状态快照
      if (payload.content.task_id) {
        currentTaskId.value = payload.content.task_id
        sessionStorage.setItem('current_task_id', payload.content.task_id)
      }
      progress.completed = payload.content.completed || 0
      progress.total = payload.content.total || 0
      progress.percent = progress.total > 0
        ? Math.round((progress.completed / progress.total) * 100)
        : 0
      result.matchedVideos = payload.content.matched_so_far || 0
      result.totalCreators = payload.content.total || 0
      if (payload.content.videos) {
        result.videos = payload.content.videos
      }
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
      sessionStorage.removeItem('current_task_id')
      currentTaskId.value = ''
      break
  }
}

// =============================================================================
// 动态列配置
// =============================================================================

const COLUMN_MAP = {
  creator_nickname: { label: 'UP主', width: 120 },
  title: { label: '标题', minWidth: 200 },
  pubdate: { label: '发布时间', width: 160 },
  description: { label: '描述', minWidth: 200 },
  dynamic: { label: '动态', minWidth: 150 },
  duration: { label: '时长(秒)', width: 100 },
  bvid: { label: 'BV号', width: 140 },
  aid: { label: 'AID', width: 120 },
  view: { label: '播放量', width: 100, align: 'right' },
  danmaku: { label: '弹幕', width: 90, align: 'right' },
  reply: { label: '评论', width: 90, align: 'right' },
  favorite: { label: '收藏', width: 90, align: 'right' },
  coin: { label: '投币', width: 90, align: 'right' },
  share: { label: '分享', width: 90, align: 'right' },
  like: { label: '点赞', width: 90, align: 'right' },
  tags: { label: '标签', minWidth: 150 },
  participle: { label: '话题', minWidth: 150 },
  url: { label: '链接', width: 80 },
  creator_mid: { label: 'UP主MID', width: 120 },
  follower: { label: '粉丝数', width: 100, align: 'right' },
  following: { label: '关注数', width: 100, align: 'right' },
  sign: { label: '签名', minWidth: 200 },
  level: { label: '等级', width: 80 },
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
  if (key === 'pubdate' && typeof val === 'number') return formatDate(val)
  if (key === 'url') return val
  if (['view', 'danmaku', 'reply', 'favorite', 'coin', 'share', 'like', 'follower', 'following'].includes(key)) {
    return typeof val === 'number' ? val.toLocaleString() : val
  }
  if (key === 'tags' && Array.isArray(val)) {
    return val.slice(0, 3).map(t => t.tag_name || t).join('、') || '-'
  }
  if (key === 'participle' && Array.isArray(val)) {
    return val.join('、') || '-'
  }
  if (key === 'duration' && typeof val === 'number') {
    const m = Math.floor(val / 60)
    const s = val % 60
    return m > 0 ? `${m}分${s}秒` : `${s}秒`
  }
  return val
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
  XLSX.utils.book_append_sheet(wb, ws, '抓取结果')
  XLSX.writeFile(wb, `批量抓取结果_${new Date().toLocaleDateString()}.xlsx`)
  ElMessage.success('导出成功')
}

function formatDate(ts) {
  if (!ts) return '-'
  const d = new Date(ts * 1000)
  return d.toLocaleString('zh-CN')
}

// =============================================================================
// 页面加载时检查是否有未完成的任务（轮询恢复，不重建 SSE）
// =============================================================================

onMounted(async () => {
  const savedTaskId = sessionStorage.getItem('current_task_id')
  if (!savedTaskId) return

  try {
    const res = await fetch(`/api/task-status?task_id=${savedTaskId}`)
    const json = await res.json()
    if (!res.ok || json.code !== 0) {
      sessionStorage.removeItem('current_task_id')
      return
    }

    const data = json.data
    const status = data.status || ''

    // 恢复状态到 UI
    currentTaskId.value = savedTaskId
    progress.completed = data.completed || 0
    progress.total = data.total || 0
    progress.percent = progress.total > 0
      ? Math.round((progress.completed / progress.total) * 100)
      : 0
    result.matchedVideos = data.matched_so_far || 0
    result.totalCreators = data.total || 0
    result.videos = data.videos || []

    if (status === 'completed' || status === 'cancelled' || status === 'done') {
      loading.value = false
      if (status === 'completed') {
        ElMessage.success('任务已完成，已恢复结果')
      }
      sessionStorage.removeItem('current_task_id')
      currentTaskId.value = ''
      return
    }

    // 任务仍在运行中 → 直接重建 SSE 接收实时进度
    loading.value = true
    ElMessage.info('检测到正在进行的任务，已恢复 SSE 连接')
    connectResumeSSE(savedTaskId)
  } catch (e) {
    console.warn('恢复任务失败:', e)
    sessionStorage.removeItem('current_task_id')
  }
})

onUnmounted(() => {
  // 页面卸载时清理轮询定时器，但不取消后台任务（让其继续在服务器端运行）
  if (recoveryPollingTimer) {
    clearInterval(recoveryPollingTimer)
    recoveryPollingTimer = null
  }
})
</script>

<template>
  <div class="app-container">
    <!-- 顶部 -->
    <header class="app-header">
      <h1>AI 批量数据抓取助手</h1>
      <p class="subtitle">上传达人 Excel → AI 自动规划 → 批量抓取 → 话题过滤 → 导出结果</p>
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
                  <div class="el-upload__tip">支持 .xlsx / .xls</div>
                </template>
              </el-upload>
            </el-form-item>

            <el-alert v-if="parsedCreators.length > 0"
              :title="`已解析 ${parsedCreators.length} 个达人`" type="success" :closable="false" show-icon
              style="margin-bottom: 16px;" />

            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="话题关键词">
                  <el-input v-model="form.topic" placeholder="例如：星布谷地" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="开始日期">
                  <el-date-picker v-model="form.startDate" type="date" placeholder="选择开始日期"
                    value-format="YYYY-MM-DD" style="width: 100%;" />
                </el-form-item>
              </el-col>
            </el-row>

            <el-form-item>
              <el-button type="primary" size="large" :loading="loading" @click="startTask"
                :disabled="!form.file">
                {{ loading ? (isPlanning ? 'AI 正在规划...' : '抓取中...') : '开始批量抓取' }}
              </el-button>
              <el-button v-if="loading" size="large" @click="stopTask">取消</el-button>
              <el-button v-if="hasResult" type="success" size="large" @click="exportExcel">
                导出 Excel
              </el-button>
            </el-form-item>
            <el-alert v-if="isPlanning" title="AI 正在进行接口选型，请稍候..." type="info" :closable="false" show-icon />
          </el-form>
        </el-card>
      </section>

      <!-- 右侧：结果 -->
      <section class="result-section">
        <!-- 总体进度 -->
        <el-card v-if="loading || progress.total > 0" shadow="hover" class="progress-card">
          <div class="progress-info">
            <span>进度：{{ progress.completed }} / {{ progress.total }} 个达人</span>
            <span>成功 {{ successCount }} | 失败 {{ errorCount }} | 已匹配 {{ result.matchedVideos }} 条视频</span>
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
            <el-tag type="info">结束: {{ llmPlan.global_filter.end_date || '无' }}</el-tag>
          </div>
          <div v-if="llmPlan.workflow" style="margin-top: 12px;">
            <div style="font-weight: 600; margin-bottom: 8px;">工作流</div>
            <el-timeline v-if="workflowSteps.length">
              <el-timeline-item
                v-for="(step, idx) in workflowSteps"
                :key="idx"
                :type="step.is_detail ? 'warning' : ''"
                :icon="step.is_detail ? 'CollectionTag' : ''"
              >
                <strong>{{ step.tool_name }}</strong>
                <el-tag v-if="step.is_detail" size="small" type="warning" style="margin-left: 8px;">逐条</el-tag>
                <p style="margin: 4px 0 0; color: #666; font-size: 13px;">{{ step.reason }}</p>
              </el-timeline-item>
            </el-timeline>
            <div v-if="llmPlan.workflow.page_rule && llmPlan.workflow.page_rule.enable_page" style="font-size: 12px; color: #909399; margin-top: 8px;">
              分页采集：最多 {{ llmPlan.workflow.page_rule.max_page }} 页，每页 {{ llmPlan.workflow.page_rule.page_size }} 条
            </div>
          </div>
        </el-card>

        <!-- 每个达人的处理结果 -->
        <el-card v-if="creatorResults.length > 0" shadow="hover" class="creator-card">
          <template #header>
            <span>达人处理详情（{{ creatorResults.length }} / {{ progress.total }}）</span>
          </template>
          <el-table :data="creatorResults" stripe border height="400" style="width: 100%;"
            :row-class-name="rowClassName">
            <el-table-column type="index" width="50" />
            <el-table-column prop="nickname" label="UP主" width="140" />
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag v-if="row.status === 'success'" type="success" size="small">成功</el-tag>
                <el-tag v-else-if="row.status === 'error'" type="danger" size="small">失败</el-tag>
                <el-tag v-else type="info" size="small">处理中</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="获取视频" width="90" align="center">
              <template #default="{ row }">{{ row.total_videos }}</template>
            </el-table-column>
            <el-table-column label="时间过滤后" width="100" align="center">
              <template #default="{ row }">{{ row.candidate_videos }}</template>
            </el-table-column>
            <el-table-column label="匹配视频" width="90" align="center">
              <template #default="{ row }">
                <strong style="color: #409eff;">{{ row.matched_videos }}</strong>
              </template>
            </el-table-column>
            <el-table-column label="错误信息" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">
                <span v-if="row.error" style="color: #f56c6c;">{{ row.error }}</span>
                <span v-else style="color: #909399;">-</span>
              </template>
            </el-table-column>
          </el-table>
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
                <span v-else-if="col.key === 'tags' && Array.isArray(row.tags)">
                  <el-tag v-for="tag in row.tags.slice(0, 3)" :key="tag.tag_name || tag" size="small" style="margin-right: 4px;">
                    {{ tag.tag_name || tag }}
                  </el-tag>
                </span>
                <span v-else>{{ formatCellValue(row, col.key) }}</span>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="暂无数据字段可展示" />
        </el-card>

        <!-- 空状态 -->
        <el-empty v-if="!loading && !hasResult && creatorResults.length === 0 && !errorMsg"
          description="配置任务参数并点击「开始批量抓取」" />
      </section>
    </main>
  </div>
</template>

<style scoped>
.app-container { min-height: 100vh; background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%); }
.app-header { text-align: center; padding: 32px 20px 20px; background: #fff; border-bottom: 1px solid #e4e7ed; }
.app-header h1 { margin: 0; font-size: 28px; color: #303133; font-weight: 600; }
.app-header .subtitle { margin: 8px 0 0; color: #909399; font-size: 14px; }
.app-main { max-width: 1400px; margin: 0 auto; padding: 24px; display: grid; grid-template-columns: 420px 1fr; gap: 24px; }
@media (max-width: 1024px) { .app-main { grid-template-columns: 1fr; } }
.config-section { position: sticky; top: 24px; align-self: start; }
.card-header { font-weight: 600; font-size: 16px; }
.progress-card { margin-bottom: 16px; }
.progress-info { display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 14px; color: #606266; }
.plan-card { margin-bottom: 16px; }
.plan-reasoning { background: #f0f9ff; border-left: 4px solid #409eff; padding: 12px 16px; margin-bottom: 12px; border-radius: 4px; font-size: 14px; }
.plan-filters { margin-bottom: 12px; }
.plan-filters .el-tag { margin-right: 8px; }
.creator-card { margin-bottom: 16px; }
.result-table-card { margin-bottom: 24px; }
.table-header { display: flex; justify-content: space-between; align-items: center; }
</style>

<style>
.error-row { background-color: #fef0f0 !important; }
</style>
