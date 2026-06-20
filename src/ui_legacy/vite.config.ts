import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  server: {
    proxy: {
      '/api': 'http://localhost:8001',
      '/chat': 'http://localhost:8001',
      '/pipelines': 'http://localhost:8001',
      '/runs': 'http://localhost:8001',
      '/proposals': 'http://localhost:8001',
      '/health': 'http://localhost:8001',
    },
  },
  base: './',
  build: { outDir: 'dist' },
})
