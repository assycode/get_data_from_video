<script setup>
import { ref, reactive, computed } from 'vue'
import { fetchEventSource } from '@microsoft/fetch-event-source'
import * as XLSX from 'xlsx'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'

// =============================================================================
// 响应式状态
// =============================================================================

const loading = ref(false)
const isPlanning = ref(false)
const abortController = ref(null)

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
})

// 进度
const progress = reactive({
  completed: 0,
  total: 0,
  percent: 0,
})

// 错误信息
const errorMsg = ref('')


// =============================================================================
// 计算属性
// =============================================================================

const hasResult = computed(() => result.videos.length > 0)

const successCount = computed(() => creatorResults.value.filter(r => r.status === 'success').length)
const errorCount = computed(() => creatorResults.value.filter(r => r.status === 'error').length)

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
  if (loading.value) { ElMessage.warning('任务正在进行中，请勿重复点击'); return }

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

  // Step 1: 先通过同步接口拿到 LLM 执行计划（避免 SSE 内长时间无数据导致断连重试）
  let plan = null
  try {
    const planRes = await fetch('/api/plan-task', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question: form.question,
        topic: form.topic,
        start_date: form.startDate,
      }),
    })
    const planJson = await planRes.json()
    if (!planRes.ok || planJson.code !== 0) {
      throw new Error(planJson.detail || planJson.message || '接口选型失败')
    }
    plan = planJson.plan
    llmPlan.value = plan
    ElMessage.success('AI 接口选型完成')
  } catch (e) {
    errorMsg.value = e.message || '接口选型失败'
    ElMessage.error(errorMsg.value)
    loading.value = false
    isPlanning.value = false
    return
  }

  isPlanning.value = false

  // Step 2: 拿到 plan 后再开 SSE 执行批量任务，并把 plan_json 传给后端
  const data = new FormData()
  data.append('question', form.question)
  data.append('file', form.file)
  if (form.topic) data.append('topic', form.topic)
  if (form.startDate) data.append('start_date', form.startDate)
  data.append('plan_json', JSON.stringify(plan))

  abortController.value = new AbortController()

  fetchEventSource('/api/batch-task-from-excel', {
    method: 'POST',
    body: data,
    signal: abortController.value.signal,
    onmessage(msg) {
      if (!msg.data) return
      try {
        const payload = JSON.parse(msg.data)
        handleEvent(payload)
      } catch (e) { console.warn('解析失败:', msg.data) }
    },
    onclose() {
      loading.value = false
    },
    onerror(err) {
      loading.value = false
      // 用户主动取消时不报错误
      if (abortController.value && abortController.value.signal.aborted) {
        return
      }
      errorMsg.value = '连接中断: ' + (err.message || '未知错误')
      ElMessage.error(errorMsg.value)
      throw err
    },
  })
}

function stopTask() {
  if (abortController.value) {
    abortController.value.abort()
    loading.value = false
    ElMessage.info('已取消')
  }
}

// =============================================================================
// SSE 事件处理
// =============================================================================

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
      break

    case 'error':
      errorMsg.value = payload.content.message || '未知错误'
      ElMessage.error(errorMsg.value)
      break

    case 'done':
      loading.value = false
      break
  }
}

// =============================================================================
// 导出 Excel
// =============================================================================

function exportExcel() {
  if (!result.videos.length) { ElMessage.warning('没有可导出的数据'); return }
  const rows = result.videos.map(v => ({
    'UP主昵称': v.creator_nickname,
    'UP主MID': v.creator_mid,
    'BV号': v.bvid,
    '标题': v.title,
    '发布时间': formatDate(v.pubdate),
    '描述': v.description,
    '动态': v.dynamic,
    '时长(秒)': v.duration,
    '播放量': v.stat?.view || 0,
    '点赞': v.stat?.like || 0,
    '投币': v.stat?.coin || 0,
    '收藏': v.stat?.favorite || 0,
    '分享': v.stat?.share || 0,
    '评论': v.stat?.reply || 0,
    '弹幕': v.stat?.danmaku || 0,
    '标签': (v.tags || []).join('、'),
    '话题': (v.participle || []).join('、'),
    '链接': v.url,
  }))
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
          <div v-if="llmPlan.filters" class="plan-filters">
            <el-tag type="primary">话题: {{ llmPlan.filters.topic || '无' }}</el-tag>
            <el-tag type="info">日期: {{ llmPlan.filters.start_date || '无' }}</el-tag>
          </div>
          <el-timeline v-if="llmPlan.tool_calls">
            <el-timeline-item v-for="(tc, idx) in llmPlan.tool_calls" :key="idx">
              <strong>{{ tc.tool }}</strong>
              <p style="margin: 4px 0 0; color: #666; font-size: 13px;">{{ tc.purpose }}</p>
            </el-timeline-item>
          </el-timeline>
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
          <el-table :data="result.videos" stripe border height="500" style="width: 100%;">
            <el-table-column type="index" width="50" />
            <el-table-column prop="creator_nickname" label="UP主" width="120" />
            <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
            <el-table-column label="发布时间" width="160">
              <template #default="{ row }">{{ formatDate(row.pubdate) }}</template>
            </el-table-column>
            <el-table-column label="播放量" width="100" align="right">
              <template #default="{ row }">{{ (row.stat?.view || 0).toLocaleString() }}</template>
            </el-table-column>
            <el-table-column label="点赞" width="90" align="right">
              <template #default="{ row }">{{ (row.stat?.like || 0).toLocaleString() }}</template>
            </el-table-column>
            <el-table-column label="标签" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">
                <el-tag v-for="tag in (row.tags || []).slice(0, 3)" :key="tag" size="small"
                  style="margin-right: 4px;">{{ tag }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="链接" width="80">
              <template #default="{ row }">
                <el-link :href="row.url" target="_blank" type="primary">查看</el-link>
              </template>
            </el-table-column>
          </el-table>
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
