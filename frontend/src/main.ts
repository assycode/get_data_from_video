// =============================================================================
// 应用入口
// =============================================================================

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'

const app = createApp(App)

// 注册 Pinia 状态管理
app.use(createPinia())

// 注册 Element Plus
app.use(ElementPlus)

app.mount('#app')
