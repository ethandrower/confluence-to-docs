import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

export const useDocsStore = defineStore('docs', () => {
  const sections = ref([])
  const tree = ref([])
  const currentPage = ref(null)
  const searchResults = ref([])
  const loading = ref(false)
  const error = ref(null)

  // Version state: keyed by space_key → selected version label (e.g. "v5.5.8")
  const selectedVersions = ref({})

  async function fetchTree() {
    if (sections.value.length > 0) return
    loading.value = true
    try {
      const res = await axios.get('/api/docs/')
      if (res.data.sections) {
        sections.value = res.data.sections
        tree.value = res.data.sections.flatMap(s => s.pages)

        // Auto-select latest version for any space that has versions
        for (const section of res.data.sections) {
          if (section.versions?.length) {
            const latest = section.versions.find(v => v.is_latest) || section.versions[0]
            selectedVersions.value[section.space_key] = latest.label
          }
        }
      } else if (res.data.results) {
        tree.value = res.data.results
        sections.value = [{ space_key: 'all', label: 'Documentation', pages: res.data.results }]
      }
    } catch (e) {
      error.value = 'Failed to load navigation'
    } finally {
      loading.value = false
    }
  }

  function selectVersion(spaceKey, versionLabel) {
    selectedVersions.value[spaceKey] = versionLabel
  }

  function getSelectedVersion(spaceKey) {
    return selectedVersions.value[spaceKey] || null
  }

  function getVersionsForSpace(spaceKey) {
    const section = sections.value.find(s => s.space_key === spaceKey)
    return section?.versions || []
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

  return {
    sections, tree, currentPage, searchResults, loading, error,
    selectedVersions,
    fetchTree, fetchPage, search,
    selectVersion, getSelectedVersion, getVersionsForSpace,
  }
})
