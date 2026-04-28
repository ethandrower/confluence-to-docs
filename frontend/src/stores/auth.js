import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const loading = ref(false)

  async function fetchMe() {
    try {
      const res = await axios.get('/api/auth/me/')
      user.value = res.data.user
    } catch {
      user.value = null
    }
  }

  async function requestMagicLink(email) {
    const res = await axios.post('/api/auth/request-magic-link/', { email })
    return res.data
  }

  async function verifyToken(token) {
    const res = await axios.get('/api/auth/verify/', { params: { token } })
    user.value = res.data.user
    return res.data
  }

  async function logout() {
    await axios.post('/api/auth/logout/')
    user.value = null
  }

  return { user, loading, fetchMe, requestMagicLink, verifyToken, logout }
})
