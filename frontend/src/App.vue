<script setup lang="ts">
// =============================================================================
// 根组件 - 路由控制
// =============================================================================

import { computed, defineAsyncComponent } from 'vue'

// 使用动态导入，避免在启动时加载所有组件
const Home = defineAsyncComponent(() => import('./views/Home.vue'))
const DouyinTest = defineAsyncComponent(() => import('./views/DouyinTest.vue'))
const XiaoHongShuTest = defineAsyncComponent(() => import('./views/XiaoHongShuTest.vue'))

// 简单的路由控制（根据路径）
const currentRoute = computed(() => {
  return window.location.pathname
})

const isDouyinTest = computed(() => {
  return currentRoute.value === '/douyin-test'
})

const isXiaoHongShuTest = computed(() => {
  return currentRoute.value === '/xiaohongshu-test'
})
</script>

<template>
  <DouyinTest v-if="isDouyinTest" />
  <XiaoHongShuTest v-else-if="isXiaoHongShuTest" />
  <Home v-else />
</template>
