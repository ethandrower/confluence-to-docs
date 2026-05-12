import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig(({ command }) => ({
  // Production (vite build): assets are served through Django's /static/ URL
  // via WhiteNoise after collectstatic. With base: '/static/' the generated
  // index.html references /static/assets/*.{js,css} which actually hit the
  // static pipeline (instead of falling through the SPA catch-all and
  // getting HTML returned in place of JS — which manifests as a blank
  // page in prod).
  //
  // Dev (vite dev server) keeps the root '/' so HMR and module loading
  // work without rewriting paths.
  base: command === 'build' ? '/static/' : '/',
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port: 5174,
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      '/media': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      }
    }
  }
}))
