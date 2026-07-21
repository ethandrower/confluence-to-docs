<template>
  <div class="atd">
    <div v-if="loading" class="atd-loading">Loading…</div>

    <div v-else-if="notFound" class="atd-placeholder">
      <p>That ticket couldn’t be loaded — it may have been deleted, or you may not have access. Pick another from the list.</p>
    </div>

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
          <span class="atd-status" :class="`status--${statusTone(ticket.status, 'staff')}`"
                title="Ticket status — set in CiteMed Support and shown to the customer. Independent of any linked Jira issue.">
            <span class="dot" aria-hidden="true" /> {{ statusLabel(ticket.status, 'staff') }}
          </span>
        </div>
        <h1 ref="subjectHeadingEl" tabindex="-1" class="atd-subject-h">{{ ticket.subject }}</h1>
      </header>

      <p v-if="actionError" class="atd-action-error" role="alert">
        {{ actionError }}
        <button class="atd-action-error-x" aria-label="Dismiss" @click="actionError = ''">×</button>
      </p>

      <!-- Controls strip (collapsed by default) -->
      <details class="atd-details">
        <summary>
          <svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg>
          <span>Details</span>
          <span class="atd-details-hint">{{ detailsHint }}</span>
        </summary>
        <div class="atd-controls">
          <label class="ctrl"><span>Ticket status</span>
            <select v-model="statusDraft" class="ctrl-input" aria-label="Ticket status" @change="onStatusChange">
              <option v-for="s in STATUS_KEYS" :key="s" :value="s">{{ statusLabel(s, 'staff') }}</option>
            </select>
            <p class="ctrl-hint">Set here and shown to the customer — not pulled from Jira.</p>
          </label>
          <div class="ctrl"><span>Jira (internal)</span>
            <ul v-if="ticket.jira_links && ticket.jira_links.length" class="jira-list">
              <li v-for="jl in ticket.jira_links" :key="jl.key" class="jira-item">
                <a class="jira-key" :href="jl.url" target="_blank" rel="noopener noreferrer">{{ jl.key }} ↗</a>
                <span v-if="jl.status" class="jira-status" :class="`jira-status--${jl.status_category || 'new'}`">{{ jl.status }}</span>
                <span v-else class="jira-status jira-status--muted">status unavailable</span>
                <button class="jira-remove" :aria-label="`Unlink ${jl.key}`" :disabled="jiraSaving" @click="onJira('remove', jl.key)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>
                </button>
              </li>
            </ul>
            <div class="ctrl-inline">
              <input v-model="jiraDraft" class="ctrl-input" type="text" placeholder="SUP-374 or paste a Jira URL" aria-label="Add Jira key or URL" @keydown.enter.prevent="onJira('add', jiraDraft)" />
              <button class="btn-outline sm" :disabled="jiraSaving || !jiraDraft.trim()" @click="onJira('add', jiraDraft)">{{ jiraSaving ? '…' : 'Link' }}</button>
            </div>
            <p class="ctrl-hint">Read-only status from Jira, for internal tracking. Never shown to the customer.</p>
          </div>
          <label class="ctrl"><span>CC</span>
            <div class="ctrl-inline">
              <div class="ctrl-inline-grow">
                <EmailChipsInput v-model="ccDraft" aria-label="CC email addresses" />
              </div>
              <button class="btn-outline sm" :disabled="ccSaving" @click="onSaveCc">{{ ccSaving ? 'Saving…' : 'Save' }}</button>
            </div>
          </label>
        </div>
      </details>

      <!-- Conversation -->
      <MessageThread
        ref="threadRef"
        :messages="renderMessages"
        perspective="admin"
        :fresh-ids="freshIds"
        :resending-id="resendingId"
        @resend="onResend"
      />

      <details class="activity-feed">
        <summary>Activity ({{ ticket.activity.length }})</summary>
        <ul>
          <li v-for="(a, i) in ticket.activity" :key="i">
            <span class="dim">{{ fullDate(a.created_at) }}</span> — {{ activityLabel(a) }}
            <span v-if="a.actor" class="dim">· {{ a.actor }}</span>
          </li>
        </ul>
      </details>

      <!-- Docked composer -->
      <form class="composer" @submit.prevent="onSendReply">
        <label for="admin-reply-body">Reply to {{ ticket.display_number }}</label>
        <textarea id="admin-reply-body" v-model="replyBody" class="composer-textarea" rows="3" placeholder="Write a reply…" @focus="replyFocused = true" @blur="replyFocused = false" @keydown="onComposerKeydown" />
        <p v-if="replyError" class="form-error" role="alert">{{ replyError }}</p>
        <div class="composer-actions">
          <label class="internal-toggle">
            <input type="checkbox" v-model="replyInternal" />
            <span>Internal note (not sent to customer)</span>
          </label>
          <div class="composer-send">
            <span class="composer-hint">⌘↵ to send</span>
            <button type="submit" class="btn-primary" :class="replyInternal && 'btn-primary--internal'" :disabled="sending || !replyBody.trim()">
              {{ sending ? 'Sending…' : (replyInternal ? 'Add internal note' : 'Send reply') }}
            </button>
          </div>
        </div>
      </form>
    </template>
  </div>
</template>

<script setup>
import { ref, watch, computed, nextTick } from 'vue'
import { useTicketsStore } from '@/stores/tickets'
import EmailChipsInput from '@/components/support/EmailChipsInput.vue'
import MessageThread from '@/components/support/MessageThread.vue'
import { usePolling } from '@/lib/usePolling'
import { useTicketChannel } from '@/lib/useTicketChannel'
import { statusLabel, statusTone, STATUS_KEYS, fullDate } from '@/lib/ticketStatus'

const props = defineProps({
  ticket: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  notFound: { type: Boolean, default: false },
})
const emit = defineEmits(['back', 'updated', 'refreshed'])

const store = useTicketsStore()

const ACTIVITY_LABELS = {
  created: 'Ticket created', message_sent: 'Reply sent', note_added: 'Internal note added',
  status_changed: 'Status changed', jira_linked: 'Jira linked', jira_unlinked: 'Jira unlinked',
  cc_changed: 'CC list updated',
}
function activityLabel(a) {
  if (a.action === 'status_changed' && a.detail) {
    return `Status: ${statusLabel(a.detail.old, 'staff')} → ${statusLabel(a.detail.new, 'staff')}`
  }
  if ((a.action === 'jira_linked' || a.action === 'jira_unlinked') && a.detail?.key) {
    return `${a.action === 'jira_linked' ? 'Jira linked' : 'Jira unlinked'}: ${a.detail.key}`
  }
  return ACTIVITY_LABELS[a.action] || a.action
}

const detailsHint = computed(() => {
  const t = props.ticket
  if (!t) return ''
  const bits = []
  const jn = (t.jira_links || []).length
  bits.push(jn ? `${jn} Jira` : 'No Jira link')
  const n = (t.cc_emails || []).length
  bits.push(n ? `${n} CC` : 'No CC')
  return bits.join(' · ')
})

const statusDraft = ref('')
const jiraDraft = ref('')
const ccDraft = ref([])
const jiraSaving = ref(false)
const ccSaving = ref(false)
const replyBody = ref('')
const replyInternal = ref(false)
const sending = ref(false)
const replyError = ref('')
const resendingId = ref(null)
// Surfaces failures from the control-strip actions (status / Jira / CC /
// resend) so a save that silently fails can never leave the operator
// believing it stuck.
const actionError = ref('')

const threadRef = ref(null)
const pending = ref([])   // optimistic staff messages not yet confirmed
const freshIds = ref(new Set())
const renderMessages = computed(() => (props.ticket ? [...props.ticket.messages, ...pending.value] : []))

const replyFocused = ref(false)
const isComposing = computed(() => replyFocused.value || replyBody.value.trim() !== '')

// Mark messages that appear after the operator opened the ticket (arrived-while-viewing highlight).
// `freshForNumber` tracks which ticket the previous message count ("old" below)
// belongs to. Vue does not guarantee this watch runs after the ticket-switch
// reset watch below on the same reactive flush, so on a ticket switch this
// callback can otherwise fire with `old` still holding the previously-open
// ticket's message count — comparing it against the newly-opened ticket's
// count would wrongly flag that ticket's pre-existing customer messages as
// "fresh" before the reset watch has a chance to clear them. Guarding on the
// ticket number (rather than relying on watcher order) makes this robust: if
// the number changed since we last saw it, just resync the tracked number
// and skip marking anything fresh this round.
let freshForNumber = null
watch(() => props.ticket?.messages?.length, (n, old) => {
  const currentNumber = props.ticket?.number ?? null
  if (currentNumber !== freshForNumber) {
    freshForNumber = currentNumber
    return
  }
  if (props.ticket && old != null && n > old) {
    const known = new Set(props.ticket.messages.slice(0, old).map(m => m.id))
    props.ticket.messages.forEach(m => { if (!known.has(m.id) && !m.is_staff) freshIds.value.add(m.id) })
  }
})

// Reset scroll to newest (and clear per-ticket state) when a different ticket is opened.
watch(() => props.ticket?.number, () => {
  pending.value = []
  freshIds.value = new Set()
  nextTick(() => threadRef.value?.resetToBottom())
})

async function refreshFromServer() {
  if (!props.ticket || isComposing.value) return
  const fresh = await store.adminTicket(props.ticket.number)
  emit('refreshed', fresh)
}
const { connected } = useTicketChannel(
  () => (props.ticket ? `/ws/tickets/${props.ticket.number}/` : null),
  () => { refreshFromServer() },
)
usePolling(refreshFromServer, {
  intervalMs: 30000,
  enabled: () => !!props.ticket && !connected.value && !isComposing.value,
})

async function onResend(m) {
  if (!props.ticket) return
  resendingId.value = m.id
  actionError.value = ''
  try {
    const res = await store.adminResend(props.ticket.number, m.id)
    m.delivery_status = res.delivery_status
    m.delivery_detail = res.delivery_detail
  } catch (e) {
    actionError.value = e.message || 'Could not resend. Please try again.'
  } finally {
    resendingId.value = null
  }
}

function syncDrafts(t) {
  if (!t) return
  statusDraft.value = t.status
  jiraDraft.value = ''
  ccDraft.value = [...(t.cc_emails || [])]
  replyBody.value = ''
  replyInternal.value = false
  replyError.value = ''
}
watch(() => props.ticket?.number, () => syncDrafts(props.ticket), { immediate: true })

// On mobile, selecting a ticket slides in this pane; move focus to the subject
// heading so keyboard/AT users land in the opened conversation. Desktop keeps
// focus on the list (the two-pane layout keeps both visible).
const subjectHeadingEl = ref(null)
watch(() => props.ticket?.number, (n, old) => {
  if (n && n !== old && window.matchMedia('(max-width: 860px)').matches) {
    nextTick(() => subjectHeadingEl.value?.focus())
  }
})

async function onStatusChange() {
  if (!props.ticket) return
  actionError.value = ''
  try {
    await store.adminSetStatus(props.ticket.number, statusDraft.value)
    emit('updated', { status: statusDraft.value })
  } catch (e) {
    actionError.value = e.message || 'Could not update status.'
    statusDraft.value = props.ticket.status // revert the dropdown to server truth
  }
}

async function onJira(action, key) {
  key = (key || '').trim()
  if (!props.ticket || (action === 'add' && !key)) return
  jiraSaving.value = true
  actionError.value = ''
  try {
    const res = await store.adminJiraLink(props.ticket.number, action, key)
    if (action === 'add') jiraDraft.value = ''
    emit('updated', { jira_links: res.jira_links })
  } catch (e) {
    actionError.value = e.message || 'Could not update Jira links.'
  } finally {
    jiraSaving.value = false
  }
}

async function onSaveCc() {
  if (!props.ticket) return
  ccSaving.value = true
  actionError.value = ''
  try {
    const res = await store.adminSetCc(props.ticket.number, ccDraft.value)
    ccDraft.value = res.cc_emails
    emit('updated', { cc_emails: res.cc_emails })
  } catch (e) {
    actionError.value = e.message || 'Could not save CC recipients.'
  } finally {
    ccSaving.value = false
  }
}

async function onSendReply() {
  const text = replyBody.value.trim()
  if (!text || !props.ticket) return
  if (sending.value) return
  sending.value = true
  replyError.value = ''
  const temp = { id: `temp-${Date.now()}`, body: text, is_staff: true, is_internal: replyInternal.value, origin: 'staff', author_name: 'You', created_at: new Date().toISOString(), pending: true }
  pending.value = [temp]
  nextTick(() => threadRef.value?.scrollToBottom(true))
  try {
    const res = await store.adminReply(props.ticket.number, text, replyInternal.value)
    replyBody.value = ''
    replyInternal.value = false
    pending.value = []
    emit('updated', { message: res.message, status: res.status })
    statusDraft.value = res.status
    nextTick(() => threadRef.value?.scrollToBottom(true))
  } catch (e) {
    pending.value = []
    replyError.value = e.message || 'Failed to send. Please try again.'
  } finally {
    sending.value = false
  }
}

function onComposerKeydown(e) {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); onSendReply() }
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
.atd-back:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
.atd-head-top { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.atd-number { font-family: var(--font-ui); font-size: 0.78rem; font-weight: 700; color: var(--muted-foreground); margin: 0; }
.atd-subject-h { font-family: var(--font-ui); font-size: 1.3rem; font-weight: 650; letter-spacing: -0.01em; color: var(--foreground); margin: 4px 0 0; }
.atd-status { flex-shrink: 0; display: inline-flex; align-items: center; gap: 6px; font-size: 0.76rem; font-weight: 650; white-space: nowrap; padding: 4px 11px; border-radius: 999px; }
.atd-status .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.status--success { color: var(--success); background: color-mix(in srgb, var(--success) 13%, transparent); }
.status--warning { color: var(--warning); background: color-mix(in srgb, var(--warning) 15%, transparent); }
.status--info { color: var(--info); background: color-mix(in srgb, var(--info) 13%, transparent); }
.status--muted { color: var(--muted-foreground); background: color-mix(in srgb, var(--muted-foreground) 13%, transparent); }

.atd-action-error { display: flex; align-items: center; gap: 10px; margin: 0; padding: 10px 28px; font-size: 0.82rem; color: var(--destructive); background: color-mix(in srgb, var(--destructive) 8%, var(--card)); border-bottom: 1px solid color-mix(in srgb, var(--destructive) 25%, var(--border)); flex-shrink: 0; }
.atd-action-error-x { margin-left: auto; flex-shrink: 0; border: none; background: none; color: var(--destructive); font-size: 1.1rem; line-height: 1; cursor: pointer; padding: 0 4px; }

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
.ctrl-hint { margin: 6px 0 0; font-size: 11.5px; line-height: 1.45; color: var(--muted-foreground); }
.ctrl-input { width: 100%; height: 38px; padding: 0 11px; border-radius: var(--radius-md); border: 1px solid var(--input); background: var(--background); color: var(--foreground); font: inherit; font-size: 13.5px; }
.ctrl-input:focus-visible { outline: 2px solid var(--ring); outline-offset: -1px; }
.ctrl-inline { display: flex; gap: 8px; align-items: flex-start; }
.ctrl-inline .ctrl-input { flex: 1 1 auto; min-width: 0; }
.ctrl-inline-grow { flex: 1 1 auto; min-width: 0; }
.jira-list { list-style: none; margin: 0 0 8px; padding: 0; display: grid; gap: 6px; }
.jira-item { display: flex; align-items: center; gap: 8px; min-width: 0; }
.jira-key { flex-shrink: 0; font-family: var(--font-ui); font-size: 12.5px; font-weight: 600; color: var(--brand-accent, var(--primary)); text-decoration: none; }
.jira-key:hover { text-decoration: underline; }
.jira-status { font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 999px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.jira-status--new { color: var(--muted-foreground); background: color-mix(in srgb, var(--muted-foreground) 14%, transparent); }
.jira-status--indeterminate { color: var(--info); background: color-mix(in srgb, var(--info) 14%, transparent); }
.jira-status--done { color: var(--success); background: color-mix(in srgb, var(--success) 15%, transparent); }
.jira-status--muted { color: var(--muted-foreground); background: none; font-weight: 400; font-style: italic; }
.jira-remove { margin-left: auto; flex-shrink: 0; display: inline-grid; place-items: center; width: 22px; height: 22px; border: none; background: none; color: var(--muted-foreground); border-radius: var(--radius-sm); cursor: pointer; }
.jira-remove svg { width: 12px; height: 12px; }
.jira-remove:hover { background: color-mix(in srgb, var(--destructive) 12%, transparent); color: var(--destructive); }
.jira-remove:focus-visible { outline: 2px solid var(--ring); outline-offset: 1px; }
.jira-remove:disabled { opacity: 0.5; cursor: default; }

.btn-outline { display: inline-flex; align-items: center; gap: 6px; background: var(--card); color: var(--foreground); border: 1px solid var(--border); font-family: var(--font-ui); font-size: 13.5px; font-weight: 550; padding: 8px 14px; border-radius: var(--radius-md); cursor: pointer; transition: border-color 0.15s, color 0.15s, background 0.15s; flex-shrink: 0; }
.btn-outline:hover { border-color: var(--primary); color: var(--primary); background: var(--accent); }
.btn-outline:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
.btn-outline.sm { padding: 0 12px; height: 38px; }
.btn-outline:disabled { opacity: 0.6; cursor: default; }

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
.composer-send { display: flex; align-items: center; gap: 10px; }
.composer-hint { font-size: 0.72rem; color: var(--muted-foreground); }
.btn-primary { display: inline-flex; align-items: center; gap: 6px; background: var(--primary); color: var(--primary-foreground); font-family: var(--font-ui); font-size: 13.5px; font-weight: 600; padding: 9px 16px; border-radius: var(--radius-md); cursor: pointer; border: 1px solid var(--primary); transition: filter 0.15s, background 0.15s, border-color 0.15s; }
.btn-primary:hover { filter: brightness(0.94); }
.btn-primary:disabled { opacity: 0.6; }
/* --background flips opposite to --warning across themes: light theme = light
   text on dark-gold, dark theme = dark text on light-gold. Fixes the ~1.97:1
   white-on-gold in dark mode. */
.btn-primary--internal { background: var(--warning); border-color: var(--warning); color: var(--background); }

@media (max-width: 860px) {
  .atd-back { display: inline-flex; }
}
</style>
