import { createApp } from 'vue'
import { createPinia } from 'pinia'
import axios from 'axios'
import App from './App.vue'
import router from './router/index.js'
import { useTheme } from './lib/useTheme.js'
import { ensureCsrfToken } from './lib/http.js'
import '@fontsource-variable/inter'
import '@fontsource-variable/source-sans-3'
import './assets/confluence-content.css'
import './assets/main.css'

// CSRF for the axios call sites (auth, docs, admin stores). Django's cookie and
// header are named differently from axios's defaults, so both must be set.
axios.defaults.withCredentials = true
axios.defaults.xsrfCookieName = 'csrftoken'
axios.defaults.xsrfHeaderName = 'X-CSRFToken'
// axios reads the cookie at send time, so it just has to exist by then. On a
// cold load the login POST can outrun App.vue's /auth/me/ call, so guarantee
// it here rather than depending on mount ordering.
axios.interceptors.request.use(async (config) => {
  const method = (config.method || 'get').toUpperCase()
  if (!['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
    await ensureCsrfToken()
  }
  return config
})

// Apply persisted theme (light default) before mount to avoid a flash.
useTheme().initTheme()

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
