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
          <StatusMenu :status="ticket.status" :disabled="statusSaving" @change="onStatusChange" />
        </div>
        <h1 ref="subjectHeadingEl" tabindex="-1" class="atd-subject-h">{{ ticket.subject }}</h1>
      </header>

      <p v-if="actionError" class="atd-action-error" role="alert">
        {{ actionError }}
        <button class="atd-action-error-x" aria-label="Dismiss" @click="actionError = ''">×</button>
      </p>

      <!-- Controls strip (collapsed by default) -->
      <PopoverRoot>
        <PopoverTrigger class="atd-details-trigger" aria-label="Ticket details — Jira and CC">
          <svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg>
          <span>Details</span>
          <span class="atd-details-hint">{{ detailsHint }}</span>
        </PopoverTrigger>
        <PopoverPortal>
          <PopoverContent class="atd-details-pop" align="start" :side-offset="6">
            <div class="atd-controls">
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
          </PopoverContent>
        </PopoverPortal>
      </PopoverRoot>

      <!-- Conversation -->
      <MessageThread
        ref="threadRef"
        :messages="renderMessages"
        perspective="admin"
        :fresh-ids="freshIds"
        :resending-id="resendingId"
        @resend="onResend"
      />

      <!-- Docked composer -->
      <form class="composer" @submit.prevent="onSendReply">
        <div class="composer-labelrow">
          <label for="admin-reply-body">Reply to {{ ticket.display_number }}</label>
          <Sheet>
            <SheetTrigger class="atd-activity-trigger">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 8v4l3 2"/><circle cx="12" cy="12" r="9"/></svg>
              Activity ({{ ticket.activity.length }})
            </SheetTrigger>
            <SheetContent side="right" class="atd-activity-sheet">
              <SheetHeader><SheetTitle>Activity</SheetTitle></SheetHeader>
              <ul class="atd-activity-list">
                <li v-for="(a, i) in ticket.activity" :key="i">
                  <span class="dim">{{ fullDate(a.created_at) }}</span> — {{ activityLabel(a) }}
                  <span v-if="a.actor" class="dim">· {{ a.actor }}</span>
                </li>
              </ul>
            </SheetContent>
          </Sheet>
        </div>
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
import { PopoverRoot, PopoverTrigger, PopoverPortal, PopoverContent } from 'reka-ui'
import { Sheet, SheetTrigger, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { useTicketsStore } from '@/stores/tickets'
import EmailChipsInput from '@/components/support/EmailChipsInput.vue'
import MessageThread from '@/components/support/MessageThread.vue'
import StatusMenu from '@/components/support/StatusMenu.vue'
import { usePolling } from '@/lib/usePolling'
import { useTicketChannel } from '@/lib/useTicketChannel'
import { statusLabel, fullDate } from '@/lib/ticketStatus'

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
// `freshBaseline` holds the message ids known at the moment the current ticket
// was opened; `freshForNumber` records which ticket number that baseline
// belongs to. This single watcher self-detects a ticket switch by comparing
// the ticket number to the number its own baseline belongs to — independent
// of watcher registration order, and correct even when two consecutively
// opened tickets happen to share a message count (a length-based watch would
// miss that switch entirely, since the count never changes).
let freshBaseline = new Set()   // message ids known at the moment this ticket was opened
let freshForNumber = null       // which ticket number freshBaseline belongs to
watch(() => props.ticket?.messages, (msgs) => {
  const num = props.ticket?.number ?? null
  if (num !== freshForNumber) {
    // ticket changed (or first load): re-baseline, mark nothing fresh
    freshForNumber = num
    freshBaseline = new Set((msgs || []).map((m) => m.id))
    freshIds.value = new Set()
    return
  }
  // same ticket still open: any message id not in the baseline is a new arrival
  for (const m of msgs || []) {
    if (!freshBaseline.has(m.id) && !m.is_staff) freshIds.value.add(m.id)
    freshBaseline.add(m.id)
  }
}, { immediate: true })

// Reset scroll to newest (and clear per-ticket state) when a different ticket is opened.
watch(() => props.ticket?.number, () => {
  pending.value = []
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

const statusSaving = ref(false)
async function onStatusChange(key) {
  if (!props.ticket || key === props.ticket.status) return
  const prev = props.ticket.status
  statusSaving.value = true
  actionError.value = ''
  emit('updated', { status: key })        // optimistic: header chip + list row update immediately
  try {
    await store.adminSetStatus(props.ticket.number, key)
  } catch (e) {
    actionError.value = e.message || 'Could not update status.'
    emit('updated', { status: prev })      // revert to server truth
  } finally {
    statusSaving.value = false
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
.atd-head { display: flex; flex-direction: column; gap: 6px; padding: 13px 28px 11px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.atd-back { display: none; align-items: center; gap: 6px; align-self: flex-start; color: var(--muted-foreground); font-size: 13px; font-weight: 550; padding: 4px 8px 4px 4px; border-radius: var(--radius-sm); cursor: pointer; }
.atd-back svg { width: 15px; height: 15px; }
.atd-back:hover { color: var(--foreground); background: var(--muted); }
.atd-back:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
.atd-head-top { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.atd-number { font-family: var(--font-ui); font-size: 0.78rem; font-weight: 700; color: var(--muted-foreground); margin: 0; }
.atd-subject-h { font-family: var(--font-ui); font-size: 1.2rem; font-weight: 650; letter-spacing: -0.01em; color: var(--foreground); margin: 0; }

.atd-action-error { display: flex; align-items: center; gap: 10px; margin: 0; padding: 10px 28px; font-size: 0.82rem; color: var(--destructive); background: color-mix(in srgb, var(--destructive) 8%, var(--card)); border-bottom: 1px solid color-mix(in srgb, var(--destructive) 25%, var(--border)); flex-shrink: 0; }
.atd-action-error-x { margin-left: auto; flex-shrink: 0; border: none; background: none; color: var(--destructive); font-size: 1.1rem; line-height: 1; cursor: pointer; padding: 0 4px; }

/* Details trigger (collapsed by default; opens a floating popover so the
   conversation/composer below never reflows). */
.atd-details-trigger { display: flex; align-items: center; gap: 8px; width: 100%; cursor: pointer; font-family: var(--font-ui); font-size: 12px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--muted-foreground); padding: 9px 28px; border: none; border-bottom: 1px solid var(--border); background: none; flex-shrink: 0; text-align: left; }
.atd-details-trigger:hover { color: var(--foreground); }
.atd-details-trigger:focus-visible { outline: 2px solid var(--ring); outline-offset: -2px; }
.atd-details-trigger .chev { width: 13px; height: 13px; flex-shrink: 0; transition: transform 0.18s ease; }
.atd-details-trigger[data-state="open"] .chev { transform: rotate(90deg); }
.atd-details-trigger .atd-details-hint { margin-left: auto; text-transform: none; letter-spacing: 0; font-weight: 500; font-size: 12px; color: var(--muted-foreground); }

/* Activity bar (footer strip; opens a slide-out drawer so the conversation/
   composer above never reflows). */
.composer-labelrow { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.atd-activity-trigger { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; font-size: 0.82rem; font-weight: 600; color: var(--muted-foreground); background: none; border: none; padding: 0; }
.atd-activity-trigger:hover { color: var(--foreground); }
.atd-activity-trigger:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
.atd-activity-trigger svg { width: 14px; height: 14px; flex-shrink: 0; }

/* Docked composer */
.composer { display: flex; flex-direction: column; gap: 6px; border-top: 1px solid var(--border); padding: 11px 28px 12px; flex-shrink: 0; background: var(--card); }
.composer label[for="admin-reply-body"] { font-size: 0.82rem; font-weight: 550; color: var(--foreground); }
.composer-textarea { padding: 0.6rem 0.8rem; border: 1px solid var(--input); border-radius: var(--radius-md); font-size: 0.9rem; font-family: inherit; color: var(--foreground); background: var(--background); resize: vertical; min-height: 58px; line-height: 1.5; outline: none; transition: border-color 0.15s, box-shadow 0.15s; }
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

<!--
  Not scoped: Reka teleports PopoverContent and the sheet's DialogContent to
  <body>, so the teleported content never carries this component's
  data-v-HASH attribute and scoped styles would never match. A plain,
  non-scoped block reaches the portalled content regardless — every selector
  below is nested under a unique wrapper class (.atd-details-pop /
  .atd-activity-sheet) to avoid leaking globally, mirroring StatusMenu.vue.
-->
<style>
.atd-details-pop { width: 320px; max-width: calc(100vw - 24px); background: var(--card); border: 1px solid var(--border); border-radius: var(--radius-md); box-shadow: 0 10px 30px color-mix(in srgb, var(--foreground) 14%, transparent); padding: 16px; z-index: 50; }
.atd-details-pop .atd-controls { display: grid; gap: 16px; }
.atd-details-pop .ctrl { display: block; }
.atd-details-pop .ctrl > span { display: block; font-family: var(--font-ui); font-size: 11px; font-weight: 700; letter-spacing: 0.03em; text-transform: uppercase; color: var(--muted-foreground); margin-bottom: 6px; }
.atd-details-pop .ctrl-hint { margin: 6px 0 0; font-size: 11.5px; line-height: 1.45; color: var(--muted-foreground); }
.atd-details-pop .ctrl-input { width: 100%; height: 38px; padding: 0 11px; border-radius: var(--radius-md); border: 1px solid var(--input); background: var(--background); color: var(--foreground); font: inherit; font-size: 13.5px; }
.atd-details-pop .ctrl-input:focus-visible { outline: 2px solid var(--ring); outline-offset: -1px; }
.atd-details-pop .ctrl-inline { display: flex; gap: 8px; align-items: flex-start; }
.atd-details-pop .ctrl-inline .ctrl-input { flex: 1 1 auto; min-width: 0; }
.atd-details-pop .ctrl-inline-grow { flex: 1 1 auto; min-width: 0; }
.atd-details-pop .jira-list { list-style: none; margin: 0 0 8px; padding: 0; display: grid; gap: 6px; }
.atd-details-pop .jira-item { display: flex; align-items: center; gap: 8px; min-width: 0; }
.atd-details-pop .jira-key { flex-shrink: 0; font-family: var(--font-ui); font-size: 12.5px; font-weight: 600; color: var(--brand-accent, var(--primary)); text-decoration: none; }
.atd-details-pop .jira-key:hover { text-decoration: underline; }
.atd-details-pop .jira-status { font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 999px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.atd-details-pop .jira-status--new { color: var(--muted-foreground); background: color-mix(in srgb, var(--muted-foreground) 14%, transparent); }
.atd-details-pop .jira-status--indeterminate { color: var(--info); background: color-mix(in srgb, var(--info) 14%, transparent); }
.atd-details-pop .jira-status--done { color: var(--success); background: color-mix(in srgb, var(--success) 15%, transparent); }
.atd-details-pop .jira-status--muted { color: var(--muted-foreground); background: none; font-weight: 400; font-style: italic; }
.atd-details-pop .jira-remove { margin-left: auto; flex-shrink: 0; display: inline-grid; place-items: center; width: 22px; height: 22px; border: none; background: none; color: var(--muted-foreground); border-radius: var(--radius-sm); cursor: pointer; }
.atd-details-pop .jira-remove svg { width: 12px; height: 12px; }
.atd-details-pop .jira-remove:hover { background: color-mix(in srgb, var(--destructive) 12%, transparent); color: var(--destructive); }
.atd-details-pop .jira-remove:focus-visible { outline: 2px solid var(--ring); outline-offset: 1px; }
.atd-details-pop .jira-remove:disabled { opacity: 0.5; cursor: default; }

.atd-details-pop .btn-outline { display: inline-flex; align-items: center; gap: 6px; background: var(--card); color: var(--foreground); border: 1px solid var(--border); font-family: var(--font-ui); font-size: 13.5px; font-weight: 550; padding: 8px 14px; border-radius: var(--radius-md); cursor: pointer; transition: border-color 0.15s, color 0.15s, background 0.15s; flex-shrink: 0; }
.atd-details-pop .btn-outline:hover { border-color: var(--primary); color: var(--primary); background: var(--accent); }
.atd-details-pop .btn-outline:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
.atd-details-pop .btn-outline.sm { padding: 0 12px; height: 38px; }
.atd-details-pop .btn-outline:disabled { opacity: 0.6; cursor: default; }

/* Activity drawer (teleported sheet content) */
.atd-activity-sheet { padding: 20px; gap: 12px; }
.atd-activity-sheet .atd-activity-list { list-style: none; margin: 0; padding: 8px 4px; display: grid; gap: 8px; overflow-y: auto; }
.atd-activity-sheet .atd-activity-list li { font-size: 0.82rem; color: var(--foreground); }
.atd-activity-sheet .dim { color: var(--muted-foreground); }
</style>
