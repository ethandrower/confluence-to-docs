import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const canSubmitTickets = ref(false)
  const loading = ref(false)

  async function fetchMe() {
    try {
      const res = await axios.get('/api/auth/me/')
      user.value = res.data.user
      canSubmitTickets.value = res.data.can_submit_tickets
    } catch {
      user.value = null
      canSubmitTickets.value = false
    }
  }

  async function requestMagicLink(email) {
    const res = await axios.post('/api/auth/request-magic-link/', { email })
    return res.data
  }

  async function verifyToken(token) {
    const res = await axios.get('/api/auth/verify/', { params: { token } })
    user.value = res.data.user
    canSubmitTickets.value = res.data.can_submit_tickets
    return res.data
  }

  async function logout() {
    await axios.post('/api/auth/logout/')
    user.value = null
    canSubmitTickets.value = false
  }

  return { user, canSubmitTickets, loading, fetchMe, requestMagicLink, verifyToken, logout }
})
