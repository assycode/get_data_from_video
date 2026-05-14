<script setup lang="ts">
// =============================================================================
// 工作流时间线组件
// =============================================================================

import { generateWorkflowSteps } from '../../utils'
import { computed } from 'vue'
import type { LLMWorkflowPlan } from '../../types'

interface Props {
  llmPlan?: LLMWorkflowPlan | null
}

const props = withDefaults(defineProps<Props>(), {
  llmPlan: null,
})

const steps = computed(() => {
  if (!props.llmPlan?.workflows) return []
  return generateWorkflowSteps(props.llmPlan.workflows)
})

const hasPlan = computed(() => !!props.llmPlan)
const globalFilter = computed(() => props.llmPlan?.global_filter)
const reasoning = computed(() => props.llmPlan?.reasoning)
const workflows = computed(() => props.llmPlan?.workflows)
const exportFields = computed(() => props.llmPlan?.export_fields || [])
</script>

<template>
  <el-card v-if="hasPlan" shadow="hover" class="plan-card">
    <template #header><span>AI 执行计划</span></template>
    
    <div v-if="reasoning" class="plan-reasoning">
      <strong>推理：</strong>{{ reasoning }}
    </div>
    
    <div v-if="globalFilter" class="plan-filters">
      <el-tag type="primary">话题: {{ globalFilter.topic || '无' }}</el-tag>
      <el-tag type="info">开始: {{ globalFilter.start_date || '无' }}</el-tag>
      <el-tag type="info">结束: {{ globalFilter.end_date || '无' }}</el-tag>
    </div>
    
    <div v-if="workflows" style="margin-top: 12px;">
      <div style="font-weight: 600; margin-bottom: 8px;">工作流</div>
      <el-timeline v-if="steps.length">
        <el-timeline-item
          v-for="(step, idx) in steps"
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
      
      <!-- 导出字段 -->
      <div v-if="exportFields.length" style="margin-top: 12px;">
        <div style="font-weight: 600; margin-bottom: 8px;">导出字段 ({{ exportFields.length }}个)</div>
        <div style="font-size: 12px; color: #666;">
          <el-tag v-for="field in exportFields.slice(0, 10)" :key="field" size="small" style="margin-right: 4px; margin-bottom: 4px;">
            {{ field }}
          </el-tag>
          <span v-if="exportFields.length > 10">+{{ exportFields.length - 10 }} more</span>
        </div>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.plan-card {
  margin-bottom: 16px;
}

.plan-reasoning {
  background: #f0f9ff;
  border-left: 4px solid #409eff;
  padding: 12px 16px;
  margin-bottom: 12px;
  border-radius: 4px;
  font-size: 14px;
}

.plan-filters {
  margin-bottom: 12px;
}

.plan-filters .el-tag {
  margin-right: 8px;
}
</style>
