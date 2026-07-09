<template>
  <div class="tt">
    <header class="tt-head">
      <div>
        <p class="tt-number">{{ ticket.display_number }}</p>
        <h1>{{ ticket.subject }}</h1>
      </div>
      <span class="tt-status" :class="`status--${statusTone(ticket.status)}`">
        <span class="dot" aria-hidden="true" /> {{ statusLabel(ticket.status) }}
      </span>
    </header>

    <div class="tt-scroll-wrap">
      <ol ref="containerRef" class="tt-messages" role="list" @scroll="checkAtBottom">
        <li v-for="m in ticket.messages" :key="m.id" class="tt-msg" :class="{ 'tt-msg--staff': m.is_staff, 'tt-msg--mine': !m.is_staff }">
          <div class="tt-msg-head">
            <span v-if="m.is_staff" class="tt-badge">CiteMed</span>
            <span v-if="m.origin === 'email'" class="tt-badge tt-badge--email">via email</span>
            <span class="tt-author">{{ m.author_name }}</span>
            <span class="tt-time">{{ fullDate(m.created_at) }}</span>
          </div>
          <p class="tt-body"><template v-for="(seg, i) in linkify(m.body)" :key="i"><a v-if="seg.type === 'link'" :href="seg.value" target="_blank" rel="noopener nofollow ugc" class="tt-link">{{ seg.value }}</a><template v-else>{{ seg.value }}</template></template></p>
        </li>
      </ol>
      <button v-if="showNewPill" type="button" class="tt-newpill" @click="scrollToBottom(true)">
        New messages ↓
      </button>
      <span class="sr-only" role="status" aria-live="polite">{{ showNewPill ? 'New messages below' : '' }}</span>
    </div>

    <p v-if="isClosed" class="tt-reopen-note">
      This ticket is {{ statusLabel(ticket.status).toLowerCase() }} — replying will reopen it.
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
      />
      <p v-if="serverError" class="tt-error" role="alert">{{ serverError }}</p>
      <div class="tt-reply-actions">
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
import { linkify } from '@/lib/linkify'
import { usePolling } from '@/lib/usePolling'
import { useTicketChannel } from '@/lib/useTicketChannel'
import { useThreadScroll } from '@/lib/useThreadScroll'

const props = defineProps({
  ticket: { type: Object, required: true },
})

const store = useTicketsStore()
const body = ref('')
const sending = ref(false)
const serverError = ref('')

const { containerRef, showNewPill, checkAtBottom, scrollToBottom, resetToBottom } =
  useThreadScroll(() => props.ticket.messages.length)

const textareaFocused = ref(false)
const isTyping = computed(() => textareaFocused.value || body.value.trim() !== '')

// Jump to newest when navigating to a different ticket in the same component.
watch(() => props.ticket.number, () => resetToBottom())

const { connected } = useTicketChannel(
  () => `/ws/tickets/${props.ticket.number}/`,
  () => { if (!isTyping.value) store.fetchTicket(props.ticket.number, { silent: true }) },
)
usePolling(() => store.fetchTicket(props.ticket.number, { silent: true }), {
  intervalMs: 30000,  // fallback cadence; only runs while the socket is down
  enabled: () => !connected.value && !isTyping.value,
})

const isClosed = computed(() => props.ticket.status === 'resolved' || props.ticket.status === 'closed')

const STATUS_LABELS = {
  waiting_on_support: 'Awaiting reply',
  waiting_on_customer: 'Action needed',
  resolved: 'Resolved',
  closed: 'Closed',
  open: 'Open',
}
const STATUS_TONES = {
  waiting_on_support: 'info',
  waiting_on_customer: 'warning',
  resolved: 'success',
  closed: 'muted',
  open: 'info',
}
function statusLabel(s) { return STATUS_LABELS[s] || s }
function statusTone(s) { return STATUS_TONES[s] || 'muted' }

function fullDate(d) {
  return new Date(d).toLocaleString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
  })
}

async function submit() {
  const text = body.value.trim()
  if (!text) return
  sending.value = true
  serverError.value = ''
  try {
    await store.reply(props.ticket.number, text)
    body.value = ''
    nextTick(() => scrollToBottom(true))
  } catch (e) {
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

.tt-scroll-wrap { position: relative; flex: 1 1 auto; min-height: 0; display: flex; }
.tt-messages { list-style: none; margin: 0; padding: 1rem 0; display: grid; gap: 0.75rem; flex: 1 1 auto; min-height: 0; overflow-y: auto; align-content: start; }
.tt-newpill {
  position: absolute; left: 50%; bottom: 12px; transform: translateX(-50%);
  display: inline-flex; align-items: center; gap: 6px;
  font: inherit; font-size: 0.78rem; font-weight: 600;
  color: var(--primary-foreground); background: var(--primary);
  border: none; border-radius: 999px; padding: 6px 14px; cursor: pointer;
  box-shadow: 0 2px 8px color-mix(in srgb, var(--foreground) 18%, transparent);
}
.tt-newpill:hover { filter: brightness(0.95); }
.tt-newpill:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
.tt-msg {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--card);
  padding: 0.85rem 1rem;
  max-width: min(85%, 560px);
}
/* Chat alignment from the customer's POV: their own messages right, CiteMed
   staff left (mirror of the admin pane, which is customer-left / staff-right). */
.tt-msg--mine { justify-self: end; }
.tt-msg--staff {
  justify-self: start;
  background: color-mix(in srgb, var(--info) 7%, var(--card));
  border-color: color-mix(in srgb, var(--info) 25%, var(--border));
}
.tt-msg-head { display: flex; align-items: baseline; gap: 0.5rem; margin-bottom: 0.4rem; flex-wrap: wrap; }
.tt-badge {
  font-size: 0.66rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em;
  padding: 0.1rem 0.45rem; border-radius: 999px;
  color: var(--info); background: color-mix(in srgb, var(--info) 16%, transparent);
}
.tt-badge--email { color: var(--muted-foreground); background: color-mix(in srgb, var(--muted-foreground) 14%, transparent); }
.tt-author { font-size: 0.85rem; font-weight: 600; color: var(--foreground); }
.tt-time { font-size: 0.76rem; color: var(--muted-foreground); margin-left: auto; }
.tt-body { font-size: 0.9rem; line-height: 1.6; color: var(--foreground); margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.tt-link { color: var(--brand-accent); text-decoration: underline; }
.tt-link:hover { text-decoration: none; }

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
.tt-reply-actions { display: flex; justify-content: flex-end; }
.btn-primary { background: var(--primary); color: var(--primary-foreground); border: none; border-radius: var(--radius-sm); padding: 0.5rem 1.1rem; cursor: pointer; font: inherit; font-size: 0.85rem; font-weight: 600; transition: opacity 0.15s; }
.btn-primary:hover:not(:disabled) { opacity: 0.9; }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
