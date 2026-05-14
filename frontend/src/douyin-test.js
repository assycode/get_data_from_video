import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import DouyinTest from './DouyinTest.vue'

const app = createApp(DouyinTest)
app.use(ElementPlus)
app.mount('#app')
