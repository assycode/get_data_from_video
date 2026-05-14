<script setup lang="ts">
// =============================================================================
// 文件上传组件
// =============================================================================

import { UploadFilled } from '@element-plus/icons-vue'
import { useExcel } from '../../composables'

interface Props {
  disabled?: boolean
}

defineProps<Props>()

const emit = defineEmits<{
  change: [file: File]
  remove: []
  parsed: [creators: any[]]
}>()

const { fileList, parsedCreators, isParsing, parseExcel } = useExcel()

async function handleChange(uploadFile: any) {
  const file = uploadFile.raw as File
  if (file) {
    emit('change', file)
    // 自动解析 Excel
    try {
      const creators = await parseExcel(file)
      emit('parsed', creators)
    } catch (e) {
      // 解析错误已在 useExcel 中处理
    }
  }
}

function handleRemove() {
  fileList.value = []
  parsedCreators.value = []
  emit('remove')
}
</script>

<template>
  <el-form-item label="达人列表（Excel）">
    <el-upload 
      drag 
      action="#" 
      :auto-upload="false" 
      :on-change="handleChange"
      :on-remove="handleRemove" 
      v-model:file-list="fileList"
      accept=".xlsx,.xls" 
      :limit="1"
      :disabled="disabled"
    >
      <el-icon class="el-icon--upload"><upload-filled /></el-icon>
      <div class="el-upload__text">拖拽文件到此处或 <em>点击上传</em></div>
      <template #tip>
        <div class="el-upload__tip">支持 .xlsx / .xls</div>
      </template>
    </el-upload>

    <el-alert 
      v-if="parsedCreators.length > 0"
      :title="`已解析 ${parsedCreators.length} 个达人`" 
      type="success" 
      :closable="false" 
      show-icon
      style="margin-top: 12px;" 
    />
  </el-form-item>
</template>
