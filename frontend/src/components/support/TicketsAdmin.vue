<template>
  <div class="tickets-admin-root">
    <div class="files-modes" role="tablist">
      <button role="tab" :aria-selected="mode==='inbox'" class="seg" :class="mode==='inbox' && 'seg--active'" @click="openInbox">
        Inbox <span v-if="inboxTotal" class="seg-badge">{{ inboxTotal }}</span>
      </button>
      <button role="tab" :aria-selected="mode==='all'" class="seg" :class="mode==='all' && 'seg--active'" @click="openAll">
        All
      </button>
      <button class="btn-primary fm-new" @click="openNewTicket">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>
        New ticket
      </button>
      <button class="refresh-btn" :class="refreshing && 'is-spinning'" :disabled="refreshing" title="Refresh" aria-label="Refresh" @click="refresh">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v5h-5"/></svg>
        {{ refreshing ? 'Refreshing…' : 'Refresh' }}
      </button>
    </div>

    <!-- ALL: filters -->
    <div v-show="mode==='all'" class="inbox-bar">
      <span class="panel-hint">Every ticket across all clients, most recently updated first.</span>
      <div class="inbox-filters">
        <select v-model="allCompany" class="inbox-select" @change="loadAll" aria-label="Filter by company">
          <option :value="''">All clients</option>
          <option v-for="c in companies" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
        <select v-model="allStatus" class="inbox-select" @change="loadAll" aria-label="Filter by status">
          <option :value="''">All statuses</option>
          <option v-for="s in STATUS_KEYS" :key="s" :value="s">{{ STATUS_LABELS[s] }}</option>
        </select>
      </div>
    </div>
    <div v-show="mode==='inbox'" class="inbox-bar">
      <span class="panel-hint">Tickets waiting on a CiteMed reply, oldest first.</span>
    </div>

    <div class="split" :class="{ 'has-detail': selected }">
      <div class="table-wrap">
        <table>
          <thead>
            <tr v-if="selected"><th>Ticket</th><th>Status</th><th></th></tr>
            <tr v-else><th>Ticket</th><th>Company</th><th>Subject</th><th>Status</th><th>Updated</th></tr>
          </thead>
          <tbody v-if="listLoading">
            <tr v-for="n in 4" :key="'sk'+n" class="sk-row"><td :colspan="selected ? 3 : 5"><span class="sk-bar" /></td></tr>
          </tbody>
          <tbody v-else>
            <tr v-for="t in list" :key="t.number" class="row-clickable" :class="selected && selected.number===t.number && 'row-active'" @click="selectTicket(t.number)">
              <td>
                <span class="row-number">{{ t.display_number }}</span>
                <span v-if="selected" class="row-subject-inline">{{ t.subject }}</span>
              </td>
              <template v-if="!selected">
                <td>{{ t.company.name }}</td>
                <td class="row-subject">{{ t.subject }}</td>
              </template>
              <td>
                <span class="status-pill" :class="`status-pill--${adminStatusTone(t.status)}`">
                  <span class="dot" aria-hidden="true" /> {{ adminStatusLabel(t.status) }}
                </span>
              </td>
              <td v-if="!selected" class="dim">{{ fmtWhen(t.updated_at) }}</td>
              <td v-else class="ta-r dim">{{ fmtWhen(t.updated_at) }}</td>
            </tr>
            <tr v-if="!list.length"><td :colspan="selected ? 3 : 5" class="empty">{{ mode==='inbox' ? 'Nothing waiting on support — all caught up. 🎉' : 'No tickets yet.' }}</td></tr>
          </tbody>
        </table>
      </div>

      <!-- Detail pane -->
      <Transition name="pane">
        <aside v-if="selected" class="detail-pane">
          <button class="detail-close" title="Close" aria-label="Close ticket detail" @click="selected = null">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 18 18 6M6 6l12 12"/></svg>
          </button>

          <div v-if="detailLoading" class="detail-loading">Loading…</div>
          <template v-else-if="selected">
            <header class="detail-head">
              <div>
                <p class="detail-number">{{ selected.display_number }} · {{ selected.company.name }}</p>
                <h3>{{ selected.subject }}</h3>
              </div>
            </header>

            <div class="detail-controls">
              <label class="ctrl"><span>Status</span>
                <select v-model="statusDraft" class="ctrl-input" aria-label="Ticket status" @change="saveStatus">
                  <option v-for="s in STATUS_KEYS" :key="s" :value="s">{{ STATUS_LABELS[s] }}</option>
                </select>
              </label>
              <label class="ctrl"><span>Jira key</span>
                <div class="ctrl-inline">
                  <input v-model="jiraDraft" class="ctrl-input" type="text" placeholder="e.g. ECD-123" aria-label="Jira key" />
                  <button class="btn-outline sm" :disabled="jiraSaving" @click="saveJira">{{ jiraSaving ? 'Saving…' : 'Save' }}</button>
                </div>
                <a v-if="selected.jira_key" class="jira-link" :href="`https://citemed.atlassian.net/browse/${selected.jira_key}`" target="_blank" rel="noopener noreferrer">
                  View {{ selected.jira_key }} in Jira ↗
                </a>
              </label>
              <label class="ctrl"><span>CC (comma-separated)</span>
                <div class="ctrl-inline">
                  <input v-model="ccDraft" class="ctrl-input" type="text" placeholder="name@example.com, other@example.com" aria-label="CC email addresses" />
                  <button class="btn-outline sm" :disabled="ccSaving" @click="saveCc">{{ ccSaving ? 'Saving…' : 'Save' }}</button>
                </div>
              </label>
            </div>

            <ol class="thread" role="list">
              <li v-for="m in selected.messages" :key="m.id" class="msg" :class="{ 'msg--staff': m.is_staff, 'msg--internal': m.is_internal }">
                <div class="msg-head">
                  <span v-if="m.is_internal" class="msg-badge msg-badge--internal">Internal</span>
                  <span v-else-if="m.is_staff" class="msg-badge">CiteMed</span>
                  <span class="msg-author">{{ m.author_name }}</span>
                  <span class="msg-time">{{ fmtWhen(m.created_at) }}</span>
                </div>
                <p class="msg-body">{{ m.body }}</p>
              </li>
              <li v-if="!selected.messages.length" class="msg-empty">No messages yet.</li>
            </ol>

            <form class="composer" @submit.prevent="sendReply">
              <label for="admin-reply-body">Reply to {{ selected.display_number }}</label>
              <textarea id="admin-reply-body" v-model="replyBody" class="composer-textarea" rows="4" placeholder="Write a reply…" />
              <p v-if="replyError" class="form-error" role="alert">{{ replyError }}</p>
              <div class="composer-actions">
                <label class="internal-toggle">
                  <input type="checkbox" v-model="replyInternal" />
                  <span>Internal note (not sent to customer)</span>
                </label>
                <button type="submit" class="btn-primary" :disabled="sending || !replyBody.trim()">
                  {{ sending ? 'Sending…' : (replyInternal ? 'Add note' : 'Send reply') }}
                </button>
              </div>
            </form>

            <details class="activity-feed">
              <summary>Activity ({{ selected.activity.length }})</summary>
              <ul>
                <li v-for="(a, i) in selected.activity" :key="i">
                  <span class="dim">{{ fmtWhen(a.created_at) }}</span> — {{ activityLabel(a) }}
                  <span v-if="a.actor" class="dim">· {{ a.actor }}</span>
                </li>
              </ul>
            </details>
          </template>
        </aside>
      </Transition>
    </div>

    <!-- New ticket modal -->
    <Transition name="modal">
      <div v-if="newModal" class="modal-overlay" @click.self="newModal=false">
        <div class="modal" role="dialog" aria-modal="true">
          <h2 class="modal-title">New ticket</h2>
          <p v-if="newError" class="form-error">{{ newError }}</p>
          <label class="field"><span>Client</span>
            <select v-model="newForm.company_id">
              <option value="">Select a client…</option>
              <option v-for="c in companies" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
          </label>
          <label class="field"><span>Customer email</span>
            <input v-model="newForm.customer_email" type="email" placeholder="customer@example.com" />
          </label>
          <label class="field"><span>Subject</span>
            <input v-model="newForm.subject" type="text" placeholder="e.g. Question about report submission" />
          </label>
          <label class="field"><span>Category</span>
            <select v-model="newForm.category">
              <option value="question">Question</option>
              <option value="bug">Bug Report</option>
              <option value="feature">Feature Request</option>
              <option value="docs">Documentation Issue</option>
              <option value="other">Other</option>
            </select>
          </label>
          <label class="field"><span>Message</span>
            <textarea v-model="newForm.body" rows="4" placeholder="Describe the issue or request…"></textarea>
          </label>
          <div class="modal-actions">
            <button class="btn-ghost" @click="newModal=false">Cancel</button>
            <button class="btn-primary" :disabled="newSaving" @click="saveNewTicket">{{ newSaving ? 'Creating…' : 'Create ticket' }}</button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useTicketsStore } from '@/stores/tickets'

const store = useTicketsStore()

// Admin status labels differ from the customer-facing ones.
const STATUS_LABELS = {
  waiting_on_support: 'Needs reply',
  waiting_on_customer: 'Waiting on customer',
  resolved: 'Resolved',
  closed: 'Closed',
  open: 'Open',
}
const STATUS_TONES = {
  waiting_on_support: 'warning',
  waiting_on_customer: 'info',
  resolved: 'success',
  closed: 'muted',
  open: 'info',
}
const STATUS_KEYS = ['open', 'waiting_on_support', 'waiting_on_customer', 'resolved', 'closed']
function adminStatusLabel(s) { return STATUS_LABELS[s] || s }
function adminStatusTone(s) { return STATUS_TONES[s] || 'muted' }

const ACTIVITY_LABELS = {
  created: 'Ticket created', message_sent: 'Reply sent', note_added: 'Internal note added',
  status_changed: 'Status changed', jira_linked: 'Jira link updated', cc_changed: 'CC list updated',
}
function activityLabel(a) {
  if (a.action === 'status_changed' && a.detail) {
    return `Status: ${adminStatusLabel(a.detail.old)} → ${adminStatusLabel(a.detail.new)}`
  }
  if (a.action === 'jira_linked' && a.detail?.jira_key) {
    return `Jira linked: ${a.detail.jira_key}`
  }
  return ACTIVITY_LABELS[a.action] || a.action
}

function fmtWhen(d) {
  return new Date(d).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

// Companies for filters + the new-ticket picker (reused from files admin pattern).
const companies = ref([])
async function loadCompanies(force = false) {
  if (!force && companies.value.length) return
  const r = await fetch('/api/admin/files/companies/', { credentials: 'include' })
  if (r.ok) companies.value = (await r.json()).companies
}

const mode = ref('inbox')
const list = ref([])
const listLoading = ref(false)
const inboxTotal = ref(0)
const allCompany = ref('')
const allStatus = ref('')
const selected = ref(null)
const detailLoading = ref(false)

async function loadInbox() {
  listLoading.value = true
  try {
    const data = await store.adminInbox()
    list.value = data.tickets
    inboxTotal.value = data.awaiting_total
  } finally {
    listLoading.value = false
  }
}
async function loadAll() {
  listLoading.value = true
  try {
    const data = await store.adminList({ company: allCompany.value, status: allStatus.value })
    list.value = data.tickets
  } finally {
    listLoading.value = false
  }
}
function openInbox() {
  selected.value = null
  mode.value = 'inbox'
  loadInbox()
}
function openAll() {
  selected.value = null
  mode.value = 'all'
  loadAll()
}

async function selectTicket(number) {
  detailLoading.value = true
  try {
    const t = await store.adminTicket(number)
    selected.value = t
    statusDraft.value = t.status
    jiraDraft.value = t.jira_key || ''
    ccDraft.value = (t.cc_emails || []).join(', ')
  } finally {
    detailLoading.value = false
  }
}

// Status
const statusDraft = ref('')
async function saveStatus() {
  if (!selected.value) return
  await store.adminSetStatus(selected.value.number, statusDraft.value)
  selected.value.status = statusDraft.value
  const row = list.value.find((t) => t.number === selected.value.number)
  if (row) row.status = statusDraft.value
}

// Jira
const jiraDraft = ref('')
const jiraSaving = ref(false)
async function saveJira() {
  if (!selected.value) return
  jiraSaving.value = true
  try {
    const res = await store.adminSetJira(selected.value.number, jiraDraft.value.trim())
    selected.value.jira_key = res.jira_key
  } finally {
    jiraSaving.value = false
  }
}

// CC
const ccDraft = ref('')
const ccSaving = ref(false)
async function saveCc() {
  if (!selected.value) return
  ccSaving.value = true
  try {
    const emails = ccDraft.value.split(',').map((s) => s.trim()).filter(Boolean)
    const res = await store.adminSetCc(selected.value.number, emails)
    selected.value.cc_emails = res.cc_emails
    ccDraft.value = res.cc_emails.join(', ')
  } finally {
    ccSaving.value = false
  }
}

// Reply / internal note composer
const replyBody = ref('')
const replyInternal = ref(false)
const sending = ref(false)
const replyError = ref('')
async function sendReply() {
  const text = replyBody.value.trim()
  if (!text || !selected.value) return
  sending.value = true
  replyError.value = ''
  try {
    const res = await store.adminReply(selected.value.number, text, replyInternal.value)
    selected.value.messages.push(res.message)
    selected.value.status = res.status
    const row = list.value.find((t) => t.number === selected.value.number)
    if (row) row.status = res.status
    statusDraft.value = res.status
    replyBody.value = ''
    replyInternal.value = false
  } catch (e) {
    replyError.value = e.message || 'Failed to send. Please try again.'
  } finally {
    sending.value = false
  }
}

// New ticket modal
const newModal = ref(false)
const newSaving = ref(false)
const newError = ref('')
const newForm = ref({ company_id: '', customer_email: '', subject: '', category: 'question', body: '' })
function openNewTicket() {
  newError.value = ''
  newForm.value = { company_id: '', customer_email: '', subject: '', category: 'question', body: '' }
  newModal.value = true
  loadCompanies()
}
async function saveNewTicket() {
  if (!newForm.value.company_id || !newForm.value.subject.trim() || !newForm.value.body.trim()) {
    newError.value = 'Client, subject and message are required.'
    return
  }
  newSaving.value = true
  newError.value = ''
  try {
    await store.adminCreate({
      company_id: newForm.value.company_id,
      subject: newForm.value.subject.trim(),
      category: newForm.value.category,
      body: newForm.value.body.trim(),
      customer_email: newForm.value.customer_email.trim(),
      cc_emails: [],
    })
    newModal.value = false
    mode.value = 'all'
    await loadAll()
  } catch (e) {
    newError.value = e.message || 'Could not create ticket'
  } finally {
    newSaving.value = false
  }
}

const refreshing = ref(false)
async function refresh() {
  refreshing.value = true
  try {
    if (mode.value === 'inbox') await loadInbox()
    else await loadAll()
    if (selected.value) await selectTicket(selected.value.number)
  } finally {
    refreshing.value = false
  }
}

onMounted(() => {
  loadCompanies()
  loadInbox()
})

defineExpose({ loadInbox })
</script>

<style scoped>
/* ── Shared primitives (mirrors FilesAdmin.vue tokens/patterns) ── */
.panel-hint { font-size: 12.5px; color: var(--muted-foreground); }
.table-wrap { border: 1px solid var(--border); border-radius: 12px; overflow: hidden; background: var(--card); }
table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13.5px; }
th { text-align: left; font-family: var(--font-ui); font-size: 11px; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; color: var(--muted-foreground); padding: 11px 14px; background: var(--muted); border-bottom: 1px solid var(--border); }
td { padding: 11px 14px; border-bottom: 1px solid var(--border-subtle); color: var(--foreground); vertical-align: middle; }
tbody tr:last-child td { border-bottom: none; }
tbody tr:hover td { background: var(--accent); }
.ta-r { text-align: right; white-space: nowrap; }
.empty { text-align: center; color: var(--muted-foreground); padding: 28px; }
.dim { color: var(--muted-foreground); font-size: 12px; }
.btn-primary { display: inline-flex; align-items: center; gap: 6px; background: var(--primary); color: var(--primary-foreground); font-family: var(--font-ui); font-size: 13.5px; font-weight: 600; padding: 8px 14px; border-radius: 8px; cursor: pointer; border: 1px solid var(--primary); transition: filter 0.15s; }
.btn-primary:hover { filter: brightness(0.94); }
.btn-primary:disabled { opacity: 0.6; }
.btn-primary svg { width: 15px; height: 15px; }
.btn-outline { display: inline-flex; align-items: center; gap: 6px; background: var(--card); color: var(--foreground); border: 1px solid var(--border); font-family: var(--font-ui); font-size: 13.5px; font-weight: 550; padding: 8px 14px; border-radius: 8px; cursor: pointer; transition: border-color 0.15s, color 0.15s, background 0.15s; }
.btn-outline:hover { border-color: var(--primary); color: var(--primary); background: var(--accent); }
.btn-outline.sm { padding: 0 12px; height: 36px; flex-shrink: 0; }
.btn-outline:disabled { opacity: 0.6; cursor: default; }
.btn-ghost { color: var(--muted-foreground); font-family: var(--font-ui); font-size: 13.5px; font-weight: 500; padding: 8px 14px; border-radius: 8px; cursor: pointer; }
.btn-ghost:hover { background: var(--muted); color: var(--foreground); }

/* Modal */
.modal-overlay { position: fixed; inset: 0; z-index: 60; background: oklch(0 0 0 / 0.45); display: flex; align-items: center; justify-content: center; padding: 20px; }
.modal { width: 100%; max-width: 440px; background: var(--popover); border: 1px solid var(--border); border-radius: 14px; padding: 22px; box-shadow: 0 20px 50px oklch(0 0 0 / 0.25); }
.modal-title { font-family: var(--font-ui); font-size: 1.15rem; font-weight: 600; color: var(--foreground); margin: 0 0 14px; }
.form-error { color: var(--destructive); font-size: 0.85rem; margin: 0 0 10px; }
.field { display: block; margin-bottom: 13px; }
.field > span { display: block; font-family: var(--font-ui); font-size: 12px; font-weight: 600; color: var(--muted-foreground); margin-bottom: 5px; }
.field input, .field select { width: 100%; height: 38px; padding: 0 11px; border-radius: 8px; border: 1px solid var(--input); background: var(--background); color: var(--foreground); font-size: 14px; }
.field input:focus, .field select:focus { outline: 2px solid var(--ring); outline-offset: -1px; border-color: var(--ring); }
.field textarea { width: 100%; padding: 8px 11px; border-radius: 8px; border: 1px solid var(--input); background: var(--background); color: var(--foreground); font: inherit; font-size: 14px; resize: vertical; }
.field textarea:focus { outline: 2px solid var(--ring); outline-offset: -1px; border-color: var(--ring); }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 18px; }
.modal-enter-active, .modal-leave-active { transition: opacity 0.18s; }
.modal-enter-from, .modal-leave-to { opacity: 0; }

/* ── Tickets: segmented modes + inbox bar ── */
.files-modes { display: flex; align-items: center; gap: 6px; margin-bottom: 16px; }
.refresh-btn { display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--card); color: var(--muted-foreground); font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; transition: color 0.15s, border-color 0.15s; }
.refresh-btn svg { width: 15px; height: 15px; }
.refresh-btn:hover { color: var(--primary); border-color: var(--primary); }
.refresh-btn:disabled { opacity: 0.6; cursor: default; }
.files-modes .fm-new { margin-left: auto; }
.files-modes .fm-new svg { width: 15px; height: 15px; }
.refresh-btn.is-spinning svg { animation: rspin 0.7s linear infinite; }
@keyframes rspin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .refresh-btn.is-spinning svg { animation: none; } }
.seg { display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; border: 1px solid var(--border); border-radius: 8px; background: var(--card); color: var(--muted-foreground); font: inherit; font-size: 13.5px; font-weight: 550; cursor: pointer; }
.seg:hover { color: var(--foreground); }
.seg--active { border-color: var(--primary); background: color-mix(in srgb, var(--primary) 8%, var(--card)); color: var(--primary); }
.seg-badge { font-size: 11px; font-weight: 700; background: var(--primary); color: var(--primary-foreground); border-radius: 999px; padding: 1px 7px; }
.inbox-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.inbox-filters { display: flex; align-items: center; gap: 10px; }
.inbox-select { height: 34px; padding: 0 10px; border-radius: 8px; border: 1px solid var(--input); background: var(--background); color: var(--foreground); font: inherit; font-size: 13px; }

/* Status pill — admin labels, text + color (not color-only) */
.status-pill { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 600; white-space: nowrap; }
.status-pill .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
.status-pill--success { color: var(--success); }
.status-pill--warning { color: var(--warning); }
.status-pill--info { color: var(--info); }
.status-pill--muted { color: var(--muted-foreground); }

/* Table rows */
.row-clickable { cursor: pointer; }
.row-active > td { background: color-mix(in srgb, var(--primary) 8%, var(--card)); }
.row-number { font-family: var(--font-ui); font-weight: 700; font-size: 12.5px; color: var(--muted-foreground); }
.row-subject { font-weight: 550; }
.row-subject-inline { display: block; font-size: 12.5px; color: var(--muted-foreground); font-weight: 400; margin-top: 2px; }

/* Loading skeleton */
.sk-row td { padding: 10px; }
.sk-bar { display: block; height: 16px; border-radius: 6px; background: linear-gradient(90deg, var(--muted) 25%, var(--secondary) 37%, var(--muted) 63%); background-size: 400% 100%; animation: sk-shimmer 1.4s ease infinite; }
@keyframes sk-shimmer { 0% { background-position: 100% 0; } 100% { background-position: 0 0; } }

/* Split list/detail */
.split { display: flex; gap: 16px; align-items: flex-start; }
.split > .table-wrap { flex: 1 1 auto; min-width: 0; }
.split.has-detail > .table-wrap { flex: 0 0 clamp(280px, 38%, 420px); }
.pane-enter-active, .pane-leave-active { transition: max-width 0.34s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.3s ease, transform 0.34s cubic-bezier(0.4, 0, 0.2, 1); overflow: hidden; }
.pane-enter-from, .pane-leave-to { max-width: 0; opacity: 0; transform: translateX(18px); }
.pane-enter-to, .pane-leave-from { max-width: 760px; }
@media (prefers-reduced-motion: reduce) {
  .sk-bar { animation: none; }
  .pane-enter-active, .pane-leave-active { transition: none; }
  .pane-enter-from, .pane-leave-to { max-width: 760px; transform: none; }
}
@media (max-width: 900px) { .split { flex-direction: column; } .split.has-detail > .table-wrap { flex: 1 1 auto; } }

/* Detail pane */
.detail-pane { position: relative; flex: 1 1 auto; min-width: 0; border: 1px solid var(--border); border-radius: 12px; background: var(--card); padding: 18px; display: flex; flex-direction: column; gap: 16px; }
.detail-close { position: absolute; top: 12px; right: 12px; width: 28px; height: 28px; display: inline-grid; place-items: center; border: none; background: none; color: var(--muted-foreground); border-radius: 7px; cursor: pointer; }
.detail-close svg { width: 15px; height: 15px; }
.detail-close:hover { background: var(--secondary); color: var(--foreground); }
.detail-loading { color: var(--muted-foreground); font-size: 0.9rem; padding: 24px 0; text-align: center; }
.detail-head { padding-right: 30px; }
.detail-number { font-family: var(--font-ui); font-size: 0.76rem; font-weight: 700; color: var(--muted-foreground); margin: 0 0 3px; }
.detail-head h3 { font-family: var(--font-ui); font-size: 1.1rem; font-weight: 650; color: var(--foreground); margin: 0; }

/* Controls: status / jira / cc */
.detail-controls { display: grid; gap: 12px; padding: 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--muted); }
.ctrl { display: block; }
.ctrl > span { display: block; font-family: var(--font-ui); font-size: 11px; font-weight: 700; letter-spacing: 0.03em; text-transform: uppercase; color: var(--muted-foreground); margin-bottom: 5px; }
.ctrl-input { width: 100%; height: 36px; padding: 0 10px; border-radius: 7px; border: 1px solid var(--input); background: var(--background); color: var(--foreground); font: inherit; font-size: 13.5px; }
.ctrl-input:focus { outline: 2px solid var(--ring); outline-offset: -1px; }
.ctrl-inline { display: flex; gap: 8px; }
.ctrl-inline .ctrl-input { flex: 1 1 auto; min-width: 0; }
.jira-link { display: inline-block; margin-top: 6px; font-size: 12.5px; color: var(--brand-accent); text-decoration: none; }
.jira-link:hover { text-decoration: underline; }

/* Thread */
.thread { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; max-height: 44vh; overflow-y: auto; }
.msg { border: 1px solid var(--border); border-radius: 10px; background: var(--card); padding: 10px 12px; }
.msg--staff { background: color-mix(in srgb, var(--info) 7%, var(--card)); border-color: color-mix(in srgb, var(--info) 25%, var(--border)); }
.msg--internal { background: color-mix(in srgb, var(--warning) 8%, var(--card)); border-color: color-mix(in srgb, var(--warning) 35%, var(--border)); border-left: 3px solid var(--warning); }
.msg-head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 5px; flex-wrap: wrap; }
.msg-badge { font-size: 0.66rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em; padding: 1px 7px; border-radius: 999px; color: var(--info); background: color-mix(in srgb, var(--info) 16%, transparent); }
.msg-badge--internal { color: var(--warning); background: color-mix(in srgb, var(--warning) 18%, transparent); }
.msg-author { font-size: 0.83rem; font-weight: 600; color: var(--foreground); }
.msg-time { font-size: 0.74rem; color: var(--muted-foreground); margin-left: auto; }
.msg-body { font-size: 0.87rem; line-height: 1.55; color: var(--foreground); margin: 0; white-space: pre-wrap; }
.msg-empty { text-align: center; color: var(--muted-foreground); font-size: 0.85rem; padding: 16px 0; list-style: none; }

/* Composer */
.composer { display: flex; flex-direction: column; gap: 8px; border-top: 1px solid var(--border); padding-top: 14px; }
.composer label[for="admin-reply-body"] { font-size: 0.8rem; font-weight: 550; color: var(--foreground); }
.composer-textarea { padding: 0.55rem 0.7rem; border: 1px solid var(--input); border-radius: 8px; font-size: 0.87rem; font-family: inherit; color: var(--foreground); background: var(--background); resize: vertical; min-height: 80px; line-height: 1.5; outline: none; transition: border-color 0.15s, box-shadow 0.15s; }
.composer-textarea:focus-visible { border-color: var(--brand-accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--brand-accent) 15%, transparent); }
.composer-actions { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.internal-toggle { display: inline-flex; align-items: center; gap: 7px; font-size: 0.82rem; color: var(--foreground); cursor: pointer; }
.internal-toggle input { accent-color: var(--warning); width: 16px; height: 16px; cursor: pointer; }

/* Activity feed */
.activity-feed { border-top: 1px solid var(--border); padding-top: 12px; }
.activity-feed summary { cursor: pointer; font-size: 0.82rem; font-weight: 600; color: var(--muted-foreground); }
.activity-feed summary:hover { color: var(--foreground); }
.activity-feed ul { list-style: none; margin: 10px 0 0; padding: 0; display: grid; gap: 6px; max-height: 26vh; overflow-y: auto; }
.activity-feed li { font-size: 0.78rem; color: var(--foreground); }
</style>
