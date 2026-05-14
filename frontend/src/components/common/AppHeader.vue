<script setup lang="ts">
// =============================================================================
// 应用头部组件
// =============================================================================

interface Props {
  title: string
  subtitle?: string
  showDouyinLink?: boolean
  showXiaoHongShuLink?: boolean
}

withDefaults(defineProps<Props>(), {
  subtitle: '',
  showDouyinLink: false,
  showXiaoHongShuLink: false,
})

const emit = defineEmits<{
  goToDouyin: []
  goToXiaoHongShu: []
}>()
</script>

<template>
  <header class="app-header">
    <div v-if="showDouyinLink || showXiaoHongShuLink" class="header-actions">
      <el-button 
        v-if="showDouyinLink"
        type="warning" 
        size="small" 
        @click="emit('goToDouyin')"
        style="background: #000; border-color: #000; margin-right: 8px;"
      >
        🎵 抖音接口测试
      </el-button>
      <el-button 
        v-if="showXiaoHongShuLink"
        type="danger" 
        size="small" 
        @click="emit('goToXiaoHongShu')"
        style="background: #ff2442; border-color: #ff2442;"
      >
        📕 小红书接口测试
      </el-button>
    </div>
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

.header-actions {
  position: absolute;
  right: 20px;
  top: 50%;
  transform: translateY(-50%);
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
