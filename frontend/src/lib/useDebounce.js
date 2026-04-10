import { ref } from 'vue'

/**
 * Shared debounced search composable.
 * Used by DocSearch and SearchCommand to avoid duplicating the pattern.
 */
export function useDebouncedSearch(searchFn, delay = 200) {
  const results = ref([])
  const loading = ref(false)
  const hasSearched = ref(false)
  let timer = null

  function search(query) {
    clearTimeout(timer)
    if (!query || !query.trim()) {
      results.value = []
      loading.value = false
      hasSearched.value = false
      return
    }
    loading.value = true
    timer = setTimeout(async () => {
      hasSearched.value = true
      const res = await searchFn(query)
      results.value = res || []
      loading.value = false
    }, delay)
  }

  function reset() {
    clearTimeout(timer)
    results.value = []
    loading.value = false
    hasSearched.value = false
  }

  return { results, loading, hasSearched, search, reset }
}
