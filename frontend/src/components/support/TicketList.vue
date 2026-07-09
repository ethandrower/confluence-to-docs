<template>
  <div class="tl">
    <ul v-if="tickets.length" class="tl-rows" role="list">
      <li v-for="t in tickets" :key="t.number" class="tl-row" :class="{ 'tl-row--unread': t.unread }">
        <RouterLink :to="{ name: 'support-ticket', params: { number: t.number } }" class="tl-link">
          <span class="tl-number">
            <span v-if="t.unread" class="unread-dot" aria-hidden="true"></span>
            {{ t.display_number }}
          </span>
          <span class="tl-subject">{{ t.subject }}</span>
          <span v-if="t.unread" class="sr-only">Unread new reply</span>
          <span class="tl-status" :class="`status--${statusTone(t.status)}`">
            <span class="dot" aria-hidden="true" /> {{ statusLabel(t.status) }}
          </span>
          <span class="tl-updated">{{ relDate(t.updated_at) }}</span>
          <span class="tl-count">{{ t.message_count }} message{{ t.message_count === 1 ? '' : 's' }}</span>
        </RouterLink>
      </li>
    </ul>
    <div v-else class="tl-empty">
      <p v-if="isFirstRun">You haven't opened a support ticket yet. Use <strong>New ticket</strong> above to ask a question, report a bug, or request something from the CiteMed team.</p>
      <p v-else>No tickets match right now.</p>
    </div>
  </div>
</template>

<script setup>
defineProps({
  tickets: { type: Array, required: true },
  isFirstRun: { type: Boolean, default: false },
})

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

function relDate(d) {
  const days = Math.floor((Date.now() - new Date(d).getTime()) / 86400000)
  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 7) return `${days} days ago`
  return new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}
</script>

<style scoped>
.tl-rows { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.4rem; }
.tl-row { border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--card); transition: border-color 0.15s ease; }
.tl-row:hover { border-color: color-mix(in srgb, var(--brand-accent) 35%, var(--border)); }

.tl-link {
  display: grid;
  grid-template-columns: 64px 1fr auto auto auto;
  align-items: center;
  gap: 0.85rem;
  padding: 0.7rem 0.9rem;
  color: inherit;
  text-decoration: none;
}
.tl-link:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; border-radius: var(--radius-md); }

.tl-number { display: inline-flex; align-items: center; gap: 0.35rem; font-family: var(--font-ui); font-size: 0.78rem; font-weight: 700; color: var(--muted-foreground); }
.tl-subject { min-width: 0; font-size: 0.9rem; font-weight: 550; color: var(--foreground); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.unread-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--brand-accent, var(--info)); flex-shrink: 0; }
.tl-row--unread { border-color: color-mix(in srgb, var(--brand-accent) 25%, var(--border)); }
.tl-row--unread .tl-subject { font-weight: 700; }

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.tl-status { display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.72rem; font-weight: 600; color: var(--muted-foreground); white-space: nowrap; }
.tl-status .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.status--success { color: var(--success); }
.status--warning { color: var(--warning); }
.status--info { color: var(--info); }
.status--muted { color: var(--muted-foreground); }

.tl-updated { font-size: 0.78rem; color: var(--muted-foreground); white-space: nowrap; }
.tl-count { font-size: 0.78rem; color: var(--muted-foreground); white-space: nowrap; }

.tl-empty { padding: 2rem; text-align: center; color: var(--muted-foreground); font-size: 0.9rem; border: 1px dashed var(--border); border-radius: var(--radius-md); }

@media (max-width: 700px) {
  .tl-link { grid-template-columns: 1fr auto; grid-template-areas: "number status" "subject subject" "updated count"; row-gap: 0.3rem; }
  .tl-number { grid-area: number; }
  .tl-status { grid-area: status; justify-self: end; }
  .tl-subject { grid-area: subject; white-space: normal; }
  .tl-updated { grid-area: updated; }
  .tl-count { grid-area: count; justify-self: end; }
}
</style>
