import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
      },
      // Раздаём и файлы из uploads. Без этого аватары и фоны проекта
      // в разработке не показывались: бэкенд отдаёт их по /uploads, а
      // проксировался только /api, и картинки просто не находились.
      '/uploads': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
      },
      // Руководства лежат в docs/ рядом с backend и отдаются им же.
      // Прокси нужен по той же причине, что и для /uploads: в
      // разработке фронтенд живёт на :3000, а тексты — на :8000.
      // Адрес не /docs: он занят встроенной документацией API.
      '/manuals': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
      }
    }
  }
})
