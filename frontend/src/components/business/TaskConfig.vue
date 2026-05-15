<script setup lang="ts">
// =============================================================================
// 任务配置表单组件
// =============================================================================

import { reactive, withDefaults, defineProps } from 'vue'
import FileUploader from './FileUploader.vue'

interface FormState {
  question: string
  topic: string
  startDate: string
  file: File | null
}

interface Props {
  isRunning?: boolean
  isPlanning?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isRunning: false,
  isPlanning: false,
})

const emit = defineEmits<{
  submit: [form: FormState]
  cancel: []
  fileChange: [file: File]
  fileParsed: [creators: any[]]
}>()

const form = reactive<FormState>({
  question: '抓取这些达人发布的带星布谷地话题的视频，从2026年4月21日开始',
  topic: '星布谷地',
  startDate: '2026-04-21',
  file: null,
})

function handleFileChange(file: File) {
  form.file = file
  emit('fileChange', file)
}

function handleFileParsed(creators: any[]) {
  emit('fileParsed', creators)
}

function handleFileRemove() {
  form.file = null
}

function handleSubmit() {
  if (!form.file) return
  emit('submit', { ...form })
}
</script>

<template>
  <el-card shadow="hover">
    <template #header>
      <div class="card-header"><span>任务配置</span></div>
    </template>

    <el-form label-position="top">
      <el-form-item label="抓取需求描述">
        <el-input v-model="form.question" type="textarea" :rows="3" />
      </el-form-item>

      <FileUploader 
        @change="handleFileChange"
        @remove="handleFileRemove"
        @parsed="handleFileParsed"
      />

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="话题关键词">
            <el-input v-model="form.topic" placeholder="例如：星布谷地" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="开始日期">
            <el-date-picker 
              v-model="form.startDate" 
              type="date" 
              placeholder="选择开始日期"
              value-format="YYYY-MM-DD" 
              style="width: 100%;" 
            />
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item>
        <el-button 
          v-if="!isRunning && !isPlanning"
          type="primary" 
          size="large" 
          @click="handleSubmit"
          :disabled="!form.file"
        >
          开始批量抓取
        </el-button>
        <el-button 
          v-else
          type="danger" 
          size="large" 
          @click="emit('cancel')"
        >
          取消任务
        </el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<style scoped>
.card-header {
  font-weight: 600;
  font-size: 16px;
}
</style>
