import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { apiFetch } from '../lib/http.js'
import { groupByModule, summarise, withoutModules } from '../lib/roster.js'

const api = (p) => `/api${p}`

/**
 * The customer's initial user request form (REV-45).
 *
 * There is only ever one request in play for a signed-in customer, so the store
 * holds one — it never takes an id from the caller. The server resolves it from
 * the session's company, which is also what stops one customer reaching
 * another's roster.
 */
export const useRosterStore = defineStore('roster', () => {
  const request = ref(null)
  const loading = ref(false)
  const loaded = ref(false)
  const error = ref('')

  /** The in-progress import, once a file has been uploaded. */
  const pendingImport = ref(null)
  const importing = ref(false)

  const users = computed(() => request.value?.users || [])
  const moduleOptions = computed(() => request.value?.module_options || [])
  const roleOptions = computed(() => request.value?.role_options || [])
  const editable = computed(() => Boolean(request.value?.editable))
  const counts = computed(() => summarise(users.value))
  const byModule = computed(() => groupByModule(users.value, moduleOptions.value))
  const unassigned = computed(() => withoutModules(users.value))

  /** True while a confirmed import has not finished being applied. */
  const importRunning = computed(() =>
    ['confirmed', 'applying'].includes(pendingImport.value?.state))

  async function load() {
    loading.value = true
    error.value = ''
    try {
      const response = await apiFetch(api('/roster/'))
      if (!response.ok) {
        // 401 before sign-in and 403 for an account with no company are both
        // normal states rather than failures worth shouting about.
        request.value = null
        return
      }
      request.value = (await response.json()).request
      loaded.value = true
    } catch {
      error.value = 'Could not load the form. Try again in a moment.'
    } finally {
      loading.value = false
    }
  }

  async function send(path, options = {}) {
    const response = await apiFetch(api(path), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      ...options,
    })
    const body = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(body.error || 'Something went wrong.')
    return body
  }

  async function addUser(row) {
    const body = await send('/roster/users/', { body: JSON.stringify(row) })
    // Reload rather than splicing the response in: an upsert may have replaced
    // a row rather than added one, and the server is the one that knows which.
    await load()
    return body.user
  }

  async function updateUser(id, patch) {
    const response = await apiFetch(api(`/roster/users/${id}/`), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    })
    const body = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(body.error || 'Could not save that change.')
    await load()
    return body.user
  }

  async function removeUser(id) {
    const response = await apiFetch(api(`/roster/users/${id}/`), { method: 'DELETE' })
    const body = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(body.error || 'Could not remove that person.')
    await load()
  }

  async function submit() {
    const body = await send('/roster/submit/')
    request.value = body.request
    return body.request
  }

  // ── Import ────────────────────────────────────────────────────────────────

  async function uploadFile(file) {
    importing.value = true
    error.value = ''
    try {
      const form = new FormData()
      form.append('file', file)
      // No Content-Type header: the browser has to set the multipart boundary
      // itself, and naming the type by hand omits it.
      const response = await apiFetch(api('/roster/imports/'), {
        method: 'POST',
        body: form,
      })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(body.error || 'Could not read that file.')
      pendingImport.value = body.import
      return body.import
    } finally {
      importing.value = false
    }
  }

  /** Re-map a column and get a fresh preview, without committing anything. */
  async function remap(mapping) {
    const body = await send(`/roster/imports/${pendingImport.value.id}/`,
                            { body: JSON.stringify({ mapping }) })
    pendingImport.value = body.import
    return body.import
  }

  async function confirmImport(mapping) {
    const body = await send(`/roster/imports/${pendingImport.value.id}/`, {
      body: JSON.stringify({ mapping, confirm: true }),
    })
    pendingImport.value = body.import
    return body.import
  }

  async function discardImport() {
    if (!pendingImport.value) return
    await apiFetch(api(`/roster/imports/${pendingImport.value.id}/`),
                   { method: 'DELETE' })
    pendingImport.value = null
  }

  /**
   * Poll a confirmed import until the cron runner has applied it.
   *
   * Polling rather than a socket because the wait is bounded and short — the
   * command runs every minute — and a WebSocket for one screen that is open
   * for ninety seconds is not worth the reconnect logic. Gives up rather than
   * polling forever, so a stuck import shows a message instead of a spinner
   * that never resolves.
   */
  async function watchImport({ intervalMs = 4000, attempts = 45 } = {}) {
    for (let i = 0; i < attempts; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, intervalMs))
      const response = await apiFetch(
        api(`/roster/imports/${pendingImport.value.id}/`))
      if (!response.ok) break
      const body = await response.json()
      pendingImport.value = body.import
      if (['done', 'failed'].includes(body.import.state)) {
        await load()
        return body.import
      }
    }
    return pendingImport.value
  }

  return {
    request, loading, loaded, error, pendingImport, importing,
    users, moduleOptions, roleOptions, editable, counts, byModule,
    unassigned, importRunning,
    load, addUser, updateUser, removeUser, submit,
    uploadFile, remap, confirmImport, discardImport, watchImport,
  }
})
