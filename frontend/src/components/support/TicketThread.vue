<template>
  <div class="tt">
    <header class="tt-head">
      <div>
        <p class="tt-number">{{ ticket.display_number }}</p>
        <h1>{{ ticket.subject }}</h1>
      </div>
      <span class="tt-status" :class="`status--${statusTone(ticket.status, 'customer')}`">
        <span class="dot" aria-hidden="true" /> {{ statusLabel(ticket.status, 'customer') }}
      </span>
    </header>

    <MessageThread
      ref="threadRef"
      :messages="renderMessages"
      perspective="customer"
      :last-read-at="lastReadAt"
    />

    <p v-if="isClosed" class="tt-reopen-note">
      This ticket is {{ statusLabel(ticket.status, 'customer').toLowerCase() }} — replying will reopen it.
    </p>

    <form class="tt-reply" @submit.prevent="submit">
      <label for="tt-reply-body">Reply to {{ ticket.display_number }}</label>
      <textarea
        id="tt-reply-body"
        v-model="body"
        class="tt-textarea"
        rows="4"
        placeholder="Write your reply…"
        @focus="textareaFocused = true"
        @blur="textareaFocused = false"
        @keydown="onKeydown"
      />
      <p v-if="serverError" class="tt-error" role="alert">{{ serverError }}</p>
      <div class="tt-reply-actions">
        <span class="tt-hint">⌘↵ to send</span>
        <button type="submit" class="btn-primary" :disabled="sending || !body.trim()">
          {{ sending ? 'Sending…' : 'Send' }}
        </button>
      </div>
    </form>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useTicketsStore } from '@/stores/tickets'
import { usePolling } from '@/lib/usePolling'
import { useTicketChannel } from '@/lib/useTicketChannel'
import { statusLabel, statusTone } from '@/lib/ticketStatus'
import MessageThread from '@/components/support/MessageThread.vue'

const props = defineProps({
  ticket: { type: Object, required: true },
})

const store = useTicketsStore()
const body = ref('')
const sending = ref(false)
const serverError = ref('')

const threadRef = ref(null)
const pending = ref([])   // optimistic messages not yet confirmed
const renderMessages = computed(() => [...props.ticket.messages, ...pending.value])

const lastReadAt = ref(null)   // frozen prior read-time for the currently open ticket

const textareaFocused = ref(false)
const isTyping = computed(() => textareaFocused.value || body.value.trim() !== '')

// Jump to newest when navigating to a different ticket in the same component.
// Also capture prev_read_at once per ticket open — every GET /api/tickets/:n/
// advances the backend's last_read_at, so the reactive prop value keeps
// creeping toward "now" on later silent refetches (realtime nudges, polling
// fallback). Freezing it here keeps the "New" divider anchored to the read
// time as of open, not the most recent refetch.
watch(() => props.ticket.number, () => {
  pending.value = []
  lastReadAt.value = props.ticket.prev_read_at || null
  nextTick(() => threadRef.value?.resetToBottom())
}, { immediate: true })

const { connected } = useTicketChannel(
  () => `/ws/tickets/${props.ticket.number}/`,
  () => { if (!isTyping.value) store.fetchTicket(props.ticket.number, { silent: true }) },
)
usePolling(() => store.fetchTicket(props.ticket.number, { silent: true }), {
  intervalMs: 30000,  // fallback cadence; only runs while the socket is down
  enabled: () => !connected.value && !isTyping.value,
})

const isClosed = computed(() => props.ticket.status === 'resolved' || props.ticket.status === 'closed')

function onKeydown(e) {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); submit() }
}

async function submit() {
  const text = body.value.trim()
  if (!text) return
  if (sending.value) return
  sending.value = true
  serverError.value = ''
  const temp = { id: `temp-${Date.now()}`, body: text, is_staff: false, is_internal: false, origin: 'portal', author_name: 'You', created_at: new Date().toISOString(), pending: true }
  pending.value = [temp]
  nextTick(() => threadRef.value?.scrollToBottom(true))
  try {
    await store.reply(props.ticket.number, text)
    body.value = ''
    pending.value = []            // real message now in ticket.messages
    nextTick(() => threadRef.value?.scrollToBottom(true))
  } catch (e) {
    pending.value = []            // remove the optimistic bubble
    serverError.value = e.message || 'Failed to send reply. Please try again.'
  } finally {
    sending.value = false
  }
}
</script>

<script>
export default { name: 'TicketThread' }
</script>

<style scoped>
/* Fill the SupportView thread column so the message list scrolls internally
   while the header stays put and the reply form docks at the bottom. */
.tt { display: flex; flex-direction: column; flex: 1 1 auto; min-height: 0; }

.tt-head { flex-shrink: 0; display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; padding-bottom: 1rem; border-bottom: 1px solid var(--border); }
.tt-number { font-family: var(--font-ui); font-size: 0.78rem; font-weight: 700; color: var(--muted-foreground); margin: 0 0 0.15rem; }
.tt-head h1 { font-family: var(--font-ui); font-size: 1.4rem; font-weight: 700; letter-spacing: -0.01em; color: var(--foreground); margin: 0; }

.tt-status { flex-shrink: 0; display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.76rem; font-weight: 600; color: var(--muted-foreground); white-space: nowrap; margin-top: 0.3rem; }
.tt-status .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.status--success { color: var(--success); }
.status--warning { color: var(--warning); }
.status--info { color: var(--info); }
.status--muted { color: var(--muted-foreground); }

.tt-reopen-note {
  flex-shrink: 0;
  font-size: 0.85rem; color: var(--warning); margin: 0;
  padding: 0.6rem 0.85rem;
  border: 1px solid color-mix(in srgb, var(--warning) 35%, var(--border));
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--warning) 10%, transparent);
}

.tt-reply { flex-shrink: 0; display: flex; flex-direction: column; gap: 0.5rem; border-top: 1px solid var(--border); padding-top: 1.1rem; margin-top: 0.5rem; }
.tt-reply label { font-size: 0.8125rem; font-weight: 550; color: var(--foreground); }
.tt-textarea {
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 0.9rem;
  font-family: inherit;
  color: var(--foreground);
  background: var(--background);
  resize: vertical;
  min-height: 96px;
  line-height: 1.5;
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.tt-textarea:focus-visible { border-color: var(--brand-accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--brand-accent) 15%, transparent); }
.tt-error { font-size: 0.82rem; color: var(--destructive); margin: 0; }
.tt-reply-actions { display: flex; justify-content: space-between; align-items: center; }
.tt-hint { font-size: 0.72rem; color: var(--muted-foreground); }
.btn-primary { background: var(--primary); color: var(--primary-foreground); border: none; border-radius: var(--radius-sm); padding: 0.5rem 1.1rem; cursor: pointer; font: inherit; font-size: 0.85rem; font-weight: 600; transition: opacity 0.15s; }
.btn-primary:hover:not(:disabled) { opacity: 0.9; }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
