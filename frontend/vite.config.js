import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        douyin: resolve(__dirname, 'douyin-test.html'),
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // SSE 长连接支持 + LLM 选型超时（10分钟）
        timeout: 600000,
        proxyTimeout: 600000,
        // 禁用缓存，确保 SSE 实时性
        bypass: (req) => {
          if (req.url?.includes('/task-progress/')) {
            req.headers['cache-control'] = 'no-cache'
          }
        }
      }
    }
  }
})
