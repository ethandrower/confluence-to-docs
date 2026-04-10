import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

export const useDocsStore = defineStore('docs', () => {
  const tree = ref([])
  const currentPage = ref(null)
  const searchResults = ref([])
  const loading = ref(false)
  const error = ref(null)

  async function fetchTree() {
    if (tree.value.length > 0) return
    loading.value = true
    try {
      const res = await axios.get('/api/docs/')
      tree.value = res.data.results
    } catch (e) {
      error.value = 'Failed to load navigation'
    } finally {
      loading.value = false
    }
  }

  async function fetchPage(slug) {
    loading.value = true
    error.value = null
    try {
      const res = await axios.get(`/api/docs/${slug}/`)
      currentPage.value = res.data
    } catch (e) {
      error.value = e.response?.status === 404 ? 'Page not found' : 'Failed to load page'
      currentPage.value = null
    } finally {
      loading.value = false
    }
  }

  async function search(q) {
    if (!q.trim()) {
      searchResults.value = []
      return
    }
    const res = await axios.get('/api/docs/search/', { params: { q } })
    searchResults.value = res.data.results
  }

  return { tree, currentPage, searchResults, loading, error, fetchTree, fetchPage, search }
})
