import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { apiFetch } from '../lib/http.js'
import { orderNotices } from '../lib/notices.js'

const api = (p) => `/api${p}`

export const useNoticesStore = defineStore('notices', () => {
  const notices = ref([])
  const history = ref([])
  const loading = ref(false)
  const loaded = ref(false)

  /** Live, in-scope, undismissed — severity first. */
  const banner = computed(() => orderNotices(notices.value))

  /**
   * Fetch the banner's notices.
   *
   * Failures are swallowed on purpose. This runs on every app boot for every
   * signed-in user, and a notices outage must not take out the page around it —
   * the banner is supplementary (EC-SOP-07 §5.2 names email as the channel), so
   * degrading to "no banner" is the right failure mode. A 401 is the normal
   * response before sign-in, not an error worth surfacing.
   */
  async function load() {
    loading.value = true
    try {
      const response = await apiFetch(api('/notices/'))
      if (!response.ok) {
        notices.value = []
        return
      }
      notices.value = (await response.json()).notices || []
      loaded.value = true
    } catch {
      notices.value = []
    } finally {
      loading.value = false
    }
  }

  /** Past and present notices — the customer-visible incident log. */
  async function loadHistory() {
    const response = await apiFetch(api('/notices/history/'))
    if (!response.ok) throw new Error('Could not load notice history')
    history.value = (await response.json()).notices || []
  }

  async function dismiss(id) {
    // Optimistic: the banner should go the moment it's clicked. A failed
    // dismissal reappears on the next load, which is the safe direction to
    // be wrong in — better a notice shown twice than one silently suppressed.
    const previous = notices.value
    notices.value = notices.value.filter((n) => n.id !== id)
    const response = await apiFetch(api(`/notices/${id}/dismiss`), { method: 'POST' })
    if (!response.ok) notices.value = previous
  }

  return { notices, history, loading, loaded, banner, load, loadHistory, dismiss }
})
