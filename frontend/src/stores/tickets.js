import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

export const useTicketsStore = defineStore('tickets', () => {
  const tickets = ref([])
  const requestTypes = ref([])
  const loading = ref(false)
  const error = ref(null)

  async function fetchTickets() {
    loading.value = true
    try {
      const res = await axios.get('/api/tickets/')
      tickets.value = res.data.results
    } catch (e) {
      error.value = 'Failed to load tickets'
    } finally {
      loading.value = false
    }
  }

  async function fetchRequestTypes() {
    const res = await axios.get('/api/tickets/request-types/')
    requestTypes.value = res.data.results
  }

  async function submitTicket(payload) {
    const res = await axios.post('/api/tickets/', payload)
    return res.data
  }

  async function fetchTicket(id) {
    const res = await axios.get(`/api/tickets/${id}/`)
    return res.data
  }

  return { tickets, requestTypes, loading, error, fetchTickets, fetchRequestTypes, submitTicket, fetchTicket }
})
