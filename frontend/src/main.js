import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router/index.js'
import { useTheme } from './lib/useTheme.js'
import '@fontsource-variable/inter'
import '@fontsource-variable/source-sans-3'
import './assets/confluence-content.css'
import './assets/main.css'

// Apply persisted theme (light default) before mount to avoid a flash.
useTheme().initTheme()

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
