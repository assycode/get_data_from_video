<script setup lang="ts">
// =============================================================================
// 应用头部组件
// =============================================================================

interface Props {
  title: string
  subtitle?: string
}

withDefaults(defineProps<Props>(), {
  subtitle: '',
})
</script>

<template>
  <header class="app-header">
    <h1>{{ title }}</h1>
    <p v-if="subtitle" class="subtitle">{{ subtitle }}</p>
    <slot />
  </header>
</template>

<style scoped>
.app-header {
  text-align: center;
  padding: 32px 20px 20px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  position: relative;
}

.app-header h1 {
  margin: 0;
  font-size: 28px;
  color: #303133;
  font-weight: 600;
}

.subtitle {
  margin: 8px 0 0;
  color: #909399;
  font-size: 14px;
}
</style>
