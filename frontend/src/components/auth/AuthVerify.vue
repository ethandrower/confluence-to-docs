<template>
  <div class="verify-page">
    <div class="verify-card">
      <div v-if="loading" class="state-loading">
        <p>Verifying your login link...</p>
      </div>
      <div v-else-if="error" class="state-error">
        <h2>Link expired or invalid</h2>
        <p>{{ error }}</p>
        <RouterLink to="/login" class="btn-link">Request a new link</RouterLink>
      </div>
      <div v-else class="state-success">
        <h2>Logged in!</h2>
        <p>Redirecting you now...</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth.js'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  const token = route.query.token
  if (!token) {
    error.value = 'No token provided.'
    loading.value = false
    return
  }
  try {
    await auth.verifyToken(token)
    loading.value = false
    const redirect = route.query.redirect || '/docs'
    router.push(redirect)
  } catch (e) {
    loading.value = false
    error.value = e.response?.data?.error || 'This link has expired or already been used.'
  }
})
</script>

<style scoped>
.verify-page { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: var(--surface-1); }
.verify-card { background: white; border-radius: 12px; padding: 2.5rem 2rem; width: 100%; max-width: 400px; text-align: center; box-shadow: 0 4px 24px rgba(0,0,0,0.08); }
.state-error h2 { color: #ef4444; margin-bottom: 0.5rem; }
.state-error p { color: var(--text-secondary); margin-bottom: 1rem; }
.btn-link { color: var(--accent); text-decoration: underline; }
.state-success h2 { color: #22c55e; }
.state-loading p { color: var(--text-secondary); }
</style>
