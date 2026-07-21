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

  // Monotonic request-sequence guards: when a silent poll for one ticket/list
  // resolves after a newer navigation-driven fetch has already started, its
  // response must not stomp the newer one's state.
  let ticketReqSeq = 0
  let ticketsReqSeq = 0

  async function fetchTickets({ silent = false } = {}) {
    const seq = ++ticketsReqSeq
    if (!silent) loading.value = true
    if (!silent) error.value = ''
    try {
      const data = await api('/tickets/')
      if (seq === ticketsReqSeq) tickets.value = data.tickets
    } catch (e) {
      if (seq === ticketsReqSeq && !silent) error.value = e.message
    } finally {
      // loading tracks THIS non-silent request's lifecycle — reset it whenever
      // it finishes. Never gate this on seq: a concurrent silent poll/WS fetch
      // bumps the counter and would otherwise strand the spinner forever.
      if (!silent) loading.value = false
    }
  }

  async function fetchTicket(number, { silent = false } = {}) {
    const seq = ++ticketReqSeq
    if (!silent) loading.value = true
    if (!silent) error.value = ''
    try {
      const data = await api(`/tickets/${number}/`)
      // data.prev_read_at (pre-open last_read_at, or null on first-ever open)
      // rides along here unwhitelisted — the thread uses it for the "New" divider.
      if (seq === ticketReqSeq) current.value = data
    } catch (e) {
      if (seq === ticketReqSeq && !silent) {
        error.value = e.message
        current.value = null
      }
    } finally {
      // loading tracks THIS non-silent request's lifecycle — reset it whenever
      // it finishes. Never gate this on seq: a concurrent silent poll/WS fetch
      // bumps the counter and would otherwise strand the spinner forever.
      if (!silent) loading.value = false
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

  // ── Admin actions ──
  async function adminInbox() {
    return api('/admin/tickets/inbox/')
  }

  async function adminList({ company, status } = {}) {
    const params = new URLSearchParams()
    if (company) params.set('company', company)
    if (status) params.set('status', status)
    const qs = params.toString()
    return api(`/admin/tickets/${qs ? `?${qs}` : ''}`)
  }

  async function adminTicket(number) {
    return api(`/admin/tickets/${number}/`)
  }

  async function adminReply(number, body, isInternal = false) {
    return api(`/admin/tickets/${number}/messages/`, {
      method: 'POST', body: JSON.stringify({ body, is_internal: isInternal }),
    })
  }

  async function adminSetStatus(number, status) {
    return api(`/admin/tickets/${number}/status/`, {
      method: 'POST', body: JSON.stringify({ status }),
    })
  }

  async function adminJiraLink(number, action, key) {
    return api(`/admin/tickets/${number}/jira/`, {
      method: 'POST', body: JSON.stringify({ action, key }),
    })
  }

  async function adminSetCc(number, ccEmails) {
    return api(`/admin/tickets/${number}/cc/`, {
      method: 'POST', body: JSON.stringify({ cc_emails: ccEmails }),
    })
  }

  async function adminCreate(payload) {
    return api('/admin/tickets/', { method: 'POST', body: JSON.stringify(payload) })
  }

  async function adminResend(number, messageId) {
    return api(`/admin/tickets/${number}/messages/${messageId}/resend/`, { method: 'POST' })
  }

  return {
    tickets, current, loading, error, fetchTickets, fetchTicket, createTicket, reply,
    adminInbox, adminList, adminTicket, adminReply, adminSetStatus, adminJiraLink, adminSetCc, adminCreate,
    adminResend,
  }
})
