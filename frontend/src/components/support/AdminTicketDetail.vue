<template>
  <div class="atd">
    <div v-if="loading" class="atd-loading">Loading…</div>

    <div v-else-if="!ticket" class="atd-placeholder">
      <p>Select a ticket from the list to view the conversation.</p>
    </div>

    <template v-else>
      <header class="atd-head">
        <button class="atd-back" aria-label="Back to ticket list" @click="$emit('back')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>
          <span>All tickets</span>
        </button>
        <div class="atd-head-top">
          <p class="atd-number">{{ ticket.display_number }} · {{ ticket.company.name }}</p>
          <span class="atd-status" :class="`status--${statusTone(ticket.status)}`">
            <span class="dot" aria-hidden="true" /> {{ statusLabel(ticket.status) }}
          </span>
        </div>
        <h1 class="atd-subject-h">{{ ticket.subject }}</h1>
      </header>

      <!-- Controls strip (collapsed by default) -->
      <details class="atd-details">
        <summary>
          <svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg>
          <span>Details</span>
          <span class="atd-details-hint">{{ detailsHint }}</span>
        </summary>
        <div class="atd-controls">
          <label class="ctrl"><span>Status</span>
            <select v-model="statusDraft" class="ctrl-input" aria-label="Ticket status" @change="onStatusChange">
              <option v-for="s in STATUS_KEYS" :key="s" :value="s">{{ STATUS_LABELS[s] }}</option>
            </select>
          </label>
          <label class="ctrl"><span>Jira key</span>
            <div class="ctrl-inline">
              <input v-model="jiraDraft" class="ctrl-input" type="text" placeholder="e.g. ECD-123" aria-label="Jira key" />
              <button class="btn-outline sm" :disabled="jiraSaving" @click="onSaveJira">{{ jiraSaving ? 'Saving…' : 'Save' }}</button>
            </div>
            <a v-if="ticket.jira_key" class="jira-link" :href="`https://citemed.atlassian.net/browse/${ticket.jira_key}`" target="_blank" rel="noopener noreferrer">
              View {{ ticket.jira_key }} in Jira ↗
            </a>
          </label>
          <label class="ctrl"><span>CC (comma-separated)</span>
            <div class="ctrl-inline">
              <input v-model="ccDraft" class="ctrl-input" type="text" placeholder="name@example.com, other@example.com" aria-label="CC email addresses" />
              <button class="btn-outline sm" :disabled="ccSaving" @click="onSaveCc">{{ ccSaving ? 'Saving…' : 'Save' }}</button>
            </div>
          </label>
        </div>
      </details>

      <!-- Conversation -->
      <ol class="atd-thread" role="list">
        <li v-for="m in ticket.messages" :key="m.id" class="msg" :class="{ 'msg--staff': m.is_staff, 'msg--internal': m.is_internal }">
          <div class="msg-head">
            <span v-if="m.is_internal" class="msg-badge msg-badge--internal">Internal</span>
            <span v-else-if="m.is_staff" class="msg-badge">CiteMed</span>
            <span class="msg-author">{{ m.author_name }}</span>
            <span class="msg-time">{{ fmtWhen(m.created_at) }}</span>
          </div>
          <p class="msg-body">{{ m.body }}</p>
          <div v-if="m.delivery_status === 'sent'" class="msg-delivery msg-delivery--ok">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>
            Sent
          </div>
          <div v-else-if="m.delivery_status === 'failed'" class="msg-delivery msg-delivery--fail">
            <span>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 9v4m0 4h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"/></svg>
              Not delivered<span v-if="m.delivery_detail" class="msg-delivery-detail"> · {{ m.delivery_detail }}</span>
            </span>
            <button class="msg-retry" :disabled="resendingId === m.id" @click="onResend(m)">
              {{ resendingId === m.id ? 'Retrying…' : 'Retry' }}
            </button>
          </div>
        </li>
        <li v-if="!ticket.messages.length" class="msg-empty">No messages yet.</li>
      </ol>

      <details class="activity-feed">
        <summary>Activity ({{ ticket.activity.length }})</summary>
        <ul>
          <li v-for="(a, i) in ticket.activity" :key="i">
            <span class="dim">{{ fmtWhen(a.created_at) }}</span> — {{ activityLabel(a) }}
            <span v-if="a.actor" class="dim">· {{ a.actor }}</span>
          </li>
        </ul>
      </details>

      <!-- Docked composer -->
      <form class="composer" @submit.prevent="onSendReply">
        <label for="admin-reply-body">Reply to {{ ticket.display_number }}</label>
        <textarea id="admin-reply-body" v-model="replyBody" class="composer-textarea" rows="3" placeholder="Write a reply…" />
        <p v-if="replyError" class="form-error" role="alert">{{ replyError }}</p>
        <div class="composer-actions">
          <label class="internal-toggle">
            <input type="checkbox" v-model="replyInternal" />
            <span>Internal note (not sent to customer)</span>
          </label>
          <button type="submit" class="btn-primary" :class="replyInternal && 'btn-primary--internal'" :disabled="sending || !replyBody.trim()">
            {{ sending ? 'Sending…' : (replyInternal ? 'Add internal note' : 'Send reply') }}
          </button>
        </div>
      </form>
    </template>
  </div>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import { useTicketsStore } from '@/stores/tickets'

const props = defineProps({
  ticket: { type: Object, default: null },
  loading: { type: Boolean, default: false },
})
const emit = defineEmits(['back', 'updated'])

const store = useTicketsStore()

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
function statusLabel(s) { return STATUS_LABELS[s] || s }
function statusTone(s) { return STATUS_TONES[s] || 'muted' }

const ACTIVITY_LABELS = {
  created: 'Ticket created', message_sent: 'Reply sent', note_added: 'Internal note added',
  status_changed: 'Status changed', jira_linked: 'Jira link updated', cc_changed: 'CC list updated',
}
function activityLabel(a) {
  if (a.action === 'status_changed' && a.detail) {
    return `Status: ${statusLabel(a.detail.old)} → ${statusLabel(a.detail.new)}`
  }
  if (a.action === 'jira_linked' && a.detail?.jira_key) {
    return `Jira linked: ${a.detail.jira_key}`
  }
  return ACTIVITY_LABELS[a.action] || a.action
}

function fmtWhen(d) {
  return new Date(d).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

const detailsHint = computed(() => {
  const t = props.ticket
  if (!t) return ''
  const bits = []
  bits.push(t.jira_key ? t.jira_key : 'No Jira link')
  const n = (t.cc_emails || []).length
  bits.push(n ? `${n} CC` : 'No CC')
  return bits.join(' · ')
})

const statusDraft = ref('')
const jiraDraft = ref('')
const ccDraft = ref('')
const jiraSaving = ref(false)
const ccSaving = ref(false)
const replyBody = ref('')
const replyInternal = ref(false)
const sending = ref(false)
const replyError = ref('')
const resendingId = ref(null)

async function onResend(m) {
  if (!props.ticket) return
  resendingId.value = m.id
  try {
    const res = await store.adminResend(props.ticket.number, m.id)
    m.delivery_status = res.delivery_status
    m.delivery_detail = res.delivery_detail
  } finally {
    resendingId.value = null
  }
}

function syncDrafts(t) {
  if (!t) return
  statusDraft.value = t.status
  jiraDraft.value = t.jira_key || ''
  ccDraft.value = (t.cc_emails || []).join(', ')
  replyBody.value = ''
  replyInternal.value = false
  replyError.value = ''
}
watch(() => props.ticket, syncDrafts, { immediate: true })

async function onStatusChange() {
  if (!props.ticket) return
  await store.adminSetStatus(props.ticket.number, statusDraft.value)
  emit('updated', { status: statusDraft.value })
}

async function onSaveJira() {
  if (!props.ticket) return
  jiraSaving.value = true
  try {
    const res = await store.adminSetJira(props.ticket.number, jiraDraft.value.trim())
    emit('updated', { jira_key: res.jira_key })
  } finally {
    jiraSaving.value = false
  }
}

async function onSaveCc() {
  if (!props.ticket) return
  ccSaving.value = true
  try {
    const emails = ccDraft.value.split(',').map((s) => s.trim()).filter(Boolean)
    const res = await store.adminSetCc(props.ticket.number, emails)
    ccDraft.value = res.cc_emails.join(', ')
    emit('updated', { cc_emails: res.cc_emails })
  } finally {
    ccSaving.value = false
  }
}

async function onSendReply() {
  const text = replyBody.value.trim()
  if (!text || !props.ticket) return
  sending.value = true
  replyError.value = ''
  try {
    const res = await store.adminReply(props.ticket.number, text, replyInternal.value)
    replyBody.value = ''
    replyInternal.value = false
    emit('updated', { message: res.message, status: res.status })
    statusDraft.value = res.status
  } catch (e) {
    replyError.value = e.message || 'Failed to send. Please try again.'
  } finally {
    sending.value = false
  }
}
</script>

<style scoped>
.atd { display: flex; flex-direction: column; height: 100%; min-height: 0; }

.atd-loading { color: var(--muted-foreground); font-size: 0.9rem; padding: 48px 0; text-align: center; }
.atd-placeholder { flex: 1 1 auto; display: flex; align-items: center; justify-content: center; color: var(--muted-foreground); font-size: 0.95rem; text-align: center; padding: 48px 24px; }

/* Header */
.atd-head { display: flex; flex-direction: column; gap: 10px; padding: 20px 28px 16px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.atd-back { display: none; align-items: center; gap: 6px; align-self: flex-start; color: var(--muted-foreground); font-size: 13px; font-weight: 550; padding: 4px 8px 4px 4px; border-radius: var(--radius-sm); cursor: pointer; }
.atd-back svg { width: 15px; height: 15px; }
.atd-back:hover { color: var(--foreground); background: var(--muted); }
.atd-head-top { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.atd-number { font-family: var(--font-ui); font-size: 0.78rem; font-weight: 700; color: var(--muted-foreground); margin: 0; }
.atd-subject-h { font-family: var(--font-ui); font-size: 1.3rem; font-weight: 650; letter-spacing: -0.01em; color: var(--foreground); margin: 4px 0 0; }
.atd-status { flex-shrink: 0; display: inline-flex; align-items: center; gap: 6px; font-size: 0.76rem; font-weight: 650; white-space: nowrap; padding: 4px 11px; border-radius: 999px; }
.atd-status .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.status--success { color: var(--success); background: color-mix(in srgb, var(--success) 13%, transparent); }
.status--warning { color: var(--warning); background: color-mix(in srgb, var(--warning) 15%, transparent); }
.status--info { color: var(--info); background: color-mix(in srgb, var(--info) 13%, transparent); }
.status--muted { color: var(--muted-foreground); background: color-mix(in srgb, var(--muted-foreground) 13%, transparent); }

/* Details / controls (collapsed by default) */
.atd-details { flex-shrink: 0; border-bottom: 1px solid var(--border); padding: 0 28px; }
.atd-details summary { display: flex; align-items: center; gap: 8px; cursor: pointer; font-family: var(--font-ui); font-size: 12px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--muted-foreground); padding: 13px 0; list-style: none; }
.atd-details summary::-webkit-details-marker { display: none; }
.atd-details summary:hover { color: var(--foreground); }
.atd-details .chev { width: 13px; height: 13px; flex-shrink: 0; transition: transform 0.18s ease; }
.atd-details[open] .chev { transform: rotate(90deg); }
.atd-details-hint { margin-left: auto; text-transform: none; letter-spacing: 0; font-weight: 500; font-size: 12px; color: var(--muted-foreground); }
.atd-details[open] .atd-details-hint { display: none; }
.atd-controls { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; padding: 4px 0 20px; }
.ctrl { display: block; }
.ctrl > span { display: block; font-family: var(--font-ui); font-size: 11px; font-weight: 700; letter-spacing: 0.03em; text-transform: uppercase; color: var(--muted-foreground); margin-bottom: 6px; }
.ctrl-input { width: 100%; height: 38px; padding: 0 11px; border-radius: var(--radius-md); border: 1px solid var(--input); background: var(--background); color: var(--foreground); font: inherit; font-size: 13.5px; }
.ctrl-input:focus-visible { outline: 2px solid var(--ring); outline-offset: -1px; }
.ctrl-inline { display: flex; gap: 8px; }
.ctrl-inline .ctrl-input { flex: 1 1 auto; min-width: 0; }
.jira-link { display: inline-block; margin-top: 7px; font-size: 12.5px; color: var(--brand-accent, var(--primary)); text-decoration: none; }
.jira-link:hover { text-decoration: underline; }

.btn-outline { display: inline-flex; align-items: center; gap: 6px; background: var(--card); color: var(--foreground); border: 1px solid var(--border); font-family: var(--font-ui); font-size: 13.5px; font-weight: 550; padding: 8px 14px; border-radius: var(--radius-md); cursor: pointer; transition: border-color 0.15s, color 0.15s, background 0.15s; flex-shrink: 0; }
.btn-outline:hover { border-color: var(--primary); color: var(--primary); background: var(--accent); }
.btn-outline.sm { padding: 0 12px; height: 38px; }
.btn-outline:disabled { opacity: 0.6; cursor: default; }

/* Conversation — the hero. A subtle canvas so the pane reads as an
   intentional workspace, not a blank void when a thread is short. */
.atd-thread { list-style: none; margin: 0; padding: 24px 28px; flex: 1 1 auto; min-height: 0; overflow-y: auto; display: grid; gap: 14px; align-content: start; background: color-mix(in srgb, var(--muted) 55%, var(--background)); }
.msg { border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--card); padding: 14px 16px; max-width: min(82%, 640px); box-shadow: 0 1px 2px color-mix(in srgb, var(--foreground) 4%, transparent); }
/* Chat alignment: customer on the left, CiteMed/staff (incl. internal notes) on the right. */
.msg--staff, .msg--internal { margin-left: auto; }
.msg--staff { background: color-mix(in srgb, var(--info) 7%, var(--card)); border-color: color-mix(in srgb, var(--info) 25%, var(--border)); }
.msg--internal { background: color-mix(in srgb, var(--warning) 8%, var(--card)); border-color: color-mix(in srgb, var(--warning) 35%, var(--border)); border-left: 3px solid var(--warning); }
.msg-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 7px; flex-wrap: wrap; }
.msg-badge { font-size: 0.68rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em; padding: 2px 8px; border-radius: 999px; color: var(--info); background: color-mix(in srgb, var(--info) 16%, transparent); }
.msg-badge--internal { color: var(--warning); background: color-mix(in srgb, var(--warning) 18%, transparent); }
.msg-author { font-size: 0.85rem; font-weight: 600; color: var(--foreground); }
.msg-time { font-size: 0.76rem; color: var(--muted-foreground); margin-left: auto; }
.msg-body { font-size: 0.9rem; line-height: 1.6; color: var(--foreground); margin: 0; white-space: pre-wrap; }
.msg-delivery { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 9px; padding-top: 8px; border-top: 1px solid var(--border); font-size: 0.72rem; font-weight: 600; }
.msg-delivery svg { width: 12px; height: 12px; flex-shrink: 0; vertical-align: -1px; margin-right: 3px; }
.msg-delivery--ok { color: var(--muted-foreground); }
.msg-delivery--fail { color: var(--destructive); }
.msg-delivery--fail > span { display: inline-flex; align-items: center; min-width: 0; }
.msg-delivery-detail { font-weight: 400; color: var(--muted-foreground); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.msg-retry { flex-shrink: 0; font: inherit; font-size: 0.72rem; font-weight: 600; color: var(--destructive); background: none; border: 1px solid color-mix(in srgb, var(--destructive) 40%, transparent); border-radius: var(--radius-sm); padding: 2px 9px; cursor: pointer; transition: background 0.15s; }
.msg-retry:hover:not(:disabled) { background: color-mix(in srgb, var(--destructive) 10%, transparent); }
.msg-retry:disabled { opacity: 0.6; cursor: default; }
.msg-empty { text-align: center; color: var(--muted-foreground); font-size: 0.88rem; padding: 24px 0; list-style: none; }

/* Activity feed */
.activity-feed { flex-shrink: 0; border-top: 1px solid var(--border); padding: 12px 28px; }
.activity-feed summary { cursor: pointer; font-size: 0.82rem; font-weight: 600; color: var(--muted-foreground); }
.activity-feed summary:hover { color: var(--foreground); }
.activity-feed ul { list-style: none; margin: 10px 0 0; padding: 0; display: grid; gap: 6px; max-height: 20vh; overflow-y: auto; }
.activity-feed li { font-size: 0.78rem; color: var(--foreground); }
.dim { color: var(--muted-foreground); }

/* Docked composer */
.composer { display: flex; flex-direction: column; gap: 10px; border-top: 1px solid var(--border); padding: 18px 28px 22px; flex-shrink: 0; background: var(--card); }
.composer label[for="admin-reply-body"] { font-size: 0.82rem; font-weight: 550; color: var(--foreground); }
.composer-textarea { padding: 0.65rem 0.8rem; border: 1px solid var(--input); border-radius: var(--radius-md); font-size: 0.9rem; font-family: inherit; color: var(--foreground); background: var(--background); resize: vertical; min-height: 76px; line-height: 1.5; outline: none; transition: border-color 0.15s, box-shadow 0.15s; }
.composer-textarea:focus-visible { border-color: var(--brand-accent, var(--primary)); box-shadow: 0 0 0 3px color-mix(in srgb, var(--brand-accent, var(--primary)) 15%, transparent); }
.form-error { color: var(--destructive); font-size: 0.85rem; margin: 0; }
.composer-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.internal-toggle { display: inline-flex; align-items: center; gap: 8px; font-size: 0.84rem; color: var(--foreground); cursor: pointer; }
.internal-toggle input { accent-color: var(--warning); width: 16px; height: 16px; cursor: pointer; }
.btn-primary { display: inline-flex; align-items: center; gap: 6px; background: var(--primary); color: var(--primary-foreground); font-family: var(--font-ui); font-size: 13.5px; font-weight: 600; padding: 9px 16px; border-radius: var(--radius-md); cursor: pointer; border: 1px solid var(--primary); transition: filter 0.15s, background 0.15s, border-color 0.15s; }
.btn-primary:hover { filter: brightness(0.94); }
.btn-primary:disabled { opacity: 0.6; }
.btn-primary--internal { background: var(--warning); border-color: var(--warning); color: #fff; }

@media (max-width: 860px) {
  .atd-back { display: inline-flex; }
}
</style>
