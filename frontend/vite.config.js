import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

// Where the dev server forwards /api, /media and /ws. Host-native dev talks to
// a runserver on localhost; under docker compose the API is a separate service,
// so VITE_PROXY_TARGET points at http://web:8001.
const proxyTarget = process.env.VITE_PROXY_TARGET || 'http://localhost:8001'
const wsTarget = proxyTarget.replace(/^http/, 'ws')

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
        target: proxyTarget,
        changeOrigin: true,
      },
      '/media': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/ws': {
        target: wsTarget,
        ws: true,
        changeOrigin: true,
      }
    }
  }
}))
