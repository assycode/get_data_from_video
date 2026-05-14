// =============================================================================
// UI 状态管理 (Pinia)
// =============================================================================

import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUIStore = defineStore('ui', () => {
  // ==========================================================================
  // State
  // ==========================================================================
  
  const loading = ref(false)
  const sidebarCollapsed = ref(false)
  const theme = ref<'light' | 'dark'>('light')

  // ==========================================================================
  // Actions
  // ==========================================================================
  
  function setLoading(value: boolean) {
    loading.value = value
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function setTheme(value: 'light' | 'dark') {
    theme.value = value
  }

  // ==========================================================================
  // Return
  // ==========================================================================
  return {
    loading,
    sidebarCollapsed,
    theme,
    setLoading,
    toggleSidebar,
    setTheme,
  }
})
