import { defineStore } from 'pinia'
import { ref } from 'vue'

const api = (path, opts = {}) =>
  fetch(`/api${path}`, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  }).then(async (r) => {
    const body = await r.json().catch(() => ({}))
    if (!r.ok) throw new Error(body.error || `Request failed (${r.status})`)
    return body
  })

export const useTicketsStore = defineStore('tickets', () => {
  const tickets = ref([])
  const current = ref(null)
  const loading = ref(false)
  const error = ref('')

  async function fetchTickets() {
    loading.value = true
    error.value = ''
    try {
      const data = await api('/tickets/')
      tickets.value = data.tickets
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function fetchTicket(number) {
    loading.value = true
    error.value = ''
    try {
      current.value = await api(`/tickets/${number}/`)
    } catch (e) {
      error.value = e.message
      current.value = null
    } finally {
      loading.value = false
    }
  }

  async function createTicket(payload) {
    const t = await api('/tickets/', { method: 'POST', body: JSON.stringify(payload) })
    await fetchTickets()
    return t
  }

  async function reply(number, body) {
    const res = await api(`/tickets/${number}/messages/`, {
      method: 'POST', body: JSON.stringify({ body }),
    })
    if (current.value?.number === number) {
      current.value.messages.push(res.message)
      current.value.status = res.status
    }
    return res
  }

  return { tickets, current, loading, error, fetchTickets, fetchTicket, createTicket, reply }
})
