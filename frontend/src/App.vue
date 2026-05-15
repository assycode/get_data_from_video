<script setup lang="ts">
// =============================================================================
// 根组件 - 只保留主页面
// =============================================================================

import { defineAsyncComponent } from 'vue'

// 只加载主页面
const Home = defineAsyncComponent(() => import('./views/Home.vue'))
</script>

<template>
  <Home />
</template>
