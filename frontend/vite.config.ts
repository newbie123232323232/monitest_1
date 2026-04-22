import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Dev: gọi API qua cùng origin (/api → backend) — tránh CORS trên trình duyệt.
// Prod: đặt VITE_API_BASE_URL trỏ thẳng API; không dùng proxy.
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
      },
    },
  },
})
