import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

export const useAdminStore = defineStore('admin', () => {
  const companies = ref([])
  const users = ref([])
  const loading = ref(false)
  const error = ref(null)

  async function fetchAll() {
    loading.value = true
    error.value = null
    try {
      const [c, u] = await Promise.all([
        axios.get('/api/admin/companies/'),
        axios.get('/api/admin/users/'),
      ])
      companies.value = c.data.companies || []
      users.value = u.data.users || []
    } catch (e) {
      error.value = e.response?.data?.error || 'Failed to load admin data'
    } finally {
      loading.value = false
    }
  }

  // Companies
  async function createCompany(payload) {
    const { data } = await axios.post('/api/admin/companies/', payload)
    companies.value.push(data.company)
    companies.value.sort((a, b) => a.name.localeCompare(b.name))
    return data.company
  }
  async function updateCompany(id, payload) {
    const { data } = await axios.patch(`/api/admin/companies/${id}/`, payload)
    const i = companies.value.findIndex(c => c.id === id)
    if (i !== -1) companies.value[i] = data.company
    return data.company
  }
  async function deleteCompany(id) {
    await axios.delete(`/api/admin/companies/${id}/`)
    companies.value = companies.value.filter(c => c.id !== id)
    // Unlink locally
    users.value.forEach(u => { if (u.company_id === id) { u.company_id = null; u.company_name = null } })
  }

  // Users
  async function createUser(payload) {
    const { data } = await axios.post('/api/admin/users/', payload)
    users.value.push(data.user)
    users.value.sort((a, b) => a.email.localeCompare(b.email))
    return data.user
  }
  async function updateUser(id, payload) {
    const { data } = await axios.patch(`/api/admin/users/${id}/`, payload)
    const i = users.value.findIndex(u => u.id === id)
    if (i !== -1) users.value[i] = data.user
    return data.user
  }
  async function deleteUser(id) {
    await axios.delete(`/api/admin/users/${id}/`)
    users.value = users.value.filter(u => u.id !== id)
  }

  async function syncDocs() {
    const { data } = await axios.post('/api/admin/sync/')
    return data.message || 'Sync started.'
  }

  return {
    companies, users, loading, error,
    fetchAll,
    createCompany, updateCompany, deleteCompany,
    createUser, updateUser, deleteUser,
    syncDocs,
  }
})
