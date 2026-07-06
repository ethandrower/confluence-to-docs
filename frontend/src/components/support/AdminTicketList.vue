<template>
  <div class="atl">
    <div class="atl-head">
      <div class="atl-modes" role="tablist" aria-label="Ticket views">
        <button role="tab" :aria-selected="mode === 'inbox'" class="seg" :class="mode === 'inbox' && 'seg--active'" @click="$emit('open-inbox')">
          Inbox <span v-if="inboxTotal" class="seg-badge">{{ inboxTotal }}</span>
        </button>
        <button role="tab" :aria-selected="mode === 'all'" class="seg" :class="mode === 'all' && 'seg--active'" @click="$emit('open-all')">
          All
        </button>
      </div>
      <button class="refresh-btn" :class="refreshing && 'is-spinning'" :disabled="refreshing" title="Refresh" aria-label="Refresh ticket list" @click="$emit('refresh')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v5h-5"/></svg>
      </button>
    </div>

    <p class="atl-hint">
      {{ mode === 'inbox' ? 'Waiting on a CiteMed reply, oldest first.' : 'Every ticket, most recently updated first.' }}
    </p>

    <div v-if="mode === 'all'" class="atl-filters">
      <select :value="filterCompany" class="atl-select" aria-label="Filter by company" @change="$emit('update:filterCompany', $event.target.value)">
        <option value="">All clients</option>
        <option v-for="c in companies" :key="c.id" :value="c.id">{{ c.name }}</option>
      </select>
      <select :value="filterStatus" class="atl-select" aria-label="Filter by status" @change="$emit('update:filterStatus', $event.target.value)">
        <option value="">All statuses</option>
        <option v-for="s in STATUS_KEYS" :key="s" :value="s">{{ STATUS_LABELS[s] }}</option>
      </select>
    </div>

    <ul class="atl-rows" role="list">
      <template v-if="loading">
        <li v-for="n in 5" :key="'sk' + n" class="atl-row atl-row--skeleton"><span class="sk-bar" /></li>
      </template>
      <template v-else>
        <li v-for="t in tickets" :key="t.number">
          <button
            class="atl-row"
            :class="{ 'atl-row--active': selectedNumber === t.number }"
            :aria-current="selectedNumber === t.number ? 'true' : undefined"
            @click="$emit('select', t.number)"
          >
            <span class="atl-row-line">
              <span class="atl-ref">{{ t.display_number }} · {{ t.company.name }}</span>
              <span class="atl-status" :class="`status--${statusTone(t.status)}`">
                <span class="dot" aria-hidden="true" /> {{ statusLabel(t.status) }}
              </span>
            </span>
            <span class="atl-row-line">
              <span class="atl-subject">{{ t.subject }}</span>
              <span class="atl-updated">{{ relDate(t.updated_at) }}</span>
            </span>
          </button>
        </li>
        <li v-if="!tickets.length" class="atl-empty">
          {{ mode === 'inbox' ? 'Nothing waiting on support — all caught up.' : 'No tickets match.' }}
        </li>
      </template>
    </ul>
  </div>
</template>

<script setup>
defineProps({
  mode: { type: String, required: true },
  tickets: { type: Array, required: true },
  loading: { type: Boolean, default: false },
  refreshing: { type: Boolean, default: false },
  inboxTotal: { type: Number, default: 0 },
  selectedNumber: { type: [String, Number], default: null },
  companies: { type: Array, default: () => [] },
  filterCompany: { type: [String, Number], default: '' },
  filterStatus: { type: String, default: '' },
})
defineEmits(['open-inbox', 'open-all', 'refresh', 'select', 'update:filterCompany', 'update:filterStatus'])

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

function relDate(d) {
  const days = Math.floor((Date.now() - new Date(d).getTime()) / 86400000)
  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 7) return `${days}d ago`
  return new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
</script>

<style scoped>
.atl { display: flex; flex-direction: column; height: 100%; min-height: 0; padding: 20px 16px 16px; }

.atl-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 4px; }
.atl-modes { display: flex; align-items: center; gap: 6px; }
.seg { display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--card); color: var(--muted-foreground); font: inherit; font-size: 13.5px; font-weight: 550; cursor: pointer; transition: color 0.15s, border-color 0.15s, background 0.15s; }
.seg:hover { color: var(--foreground); }
.seg--active { border-color: var(--primary); background: color-mix(in srgb, var(--primary) 8%, var(--card)); color: var(--primary); }
.seg-badge { font-size: 11px; font-weight: 700; background: var(--primary); color: var(--primary-foreground); border-radius: 999px; padding: 1px 7px; }

.refresh-btn { display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--card); color: var(--muted-foreground); cursor: pointer; transition: color 0.15s, border-color 0.15s; flex-shrink: 0; }
.refresh-btn svg { width: 15px; height: 15px; }
.refresh-btn:hover { color: var(--primary); border-color: var(--primary); }
.refresh-btn:disabled { opacity: 0.6; cursor: default; }
.refresh-btn.is-spinning svg { animation: rspin 0.7s linear infinite; }
@keyframes rspin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .refresh-btn.is-spinning svg { animation: none; } }

.atl-hint { font-size: 12.5px; color: var(--muted-foreground); margin: 10px 0 12px; line-height: 1.4; }

.atl-filters { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; }
.atl-select { flex: 1 1 auto; min-width: 0; height: 34px; padding: 0 10px; border-radius: var(--radius-md); border: 1px solid var(--input); background: var(--background); color: var(--foreground); font: inherit; font-size: 13px; }
.atl-select:focus-visible { outline: 2px solid var(--ring); outline-offset: -1px; }

.atl-rows { list-style: none; margin: 0 -16px; padding: 0; flex: 1 1 auto; min-height: 0; overflow-y: auto; display: flex; flex-direction: column; }
.atl-rows > li { display: block; }

.atl-row {
  display: flex; flex-direction: column; gap: 5px; width: 100%; text-align: left;
  padding: 11px 16px; border: none; border-bottom: 1px solid var(--border);
  background: transparent; cursor: pointer; transition: background 0.12s;
}
.atl-row:hover { background: var(--accent); }
.atl-row--active { background: color-mix(in srgb, var(--primary) 10%, var(--card)); box-shadow: inset 3px 0 0 var(--primary); }
.atl-row-line { display: flex; align-items: center; justify-content: space-between; gap: 10px; min-width: 0; }
.atl-ref { font-family: var(--font-ui); font-weight: 650; font-size: 13px; color: var(--foreground); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.atl-updated { font-size: 11.5px; color: var(--muted-foreground); flex-shrink: 0; white-space: nowrap; }
.atl-subject { font-size: 12.5px; color: var(--muted-foreground); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }

.atl-status { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 600; flex-shrink: 0; white-space: nowrap; }
.atl-status .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
.status--success { color: var(--success); }
.status--warning { color: var(--warning); }
.status--info { color: var(--info); }
.status--muted { color: var(--muted-foreground); }

.atl-empty { text-align: center; color: var(--muted-foreground); font-size: 13px; padding: 32px 12px; }

.atl-row--skeleton { height: 62px; display: flex; align-items: center; padding: 10px 12px; }
.sk-bar { display: block; width: 100%; height: 16px; border-radius: 6px; background: linear-gradient(90deg, var(--muted) 25%, var(--secondary) 37%, var(--muted) 63%); background-size: 400% 100%; animation: sk-shimmer 1.4s ease infinite; }
@keyframes sk-shimmer { 0% { background-position: 100% 0; } 100% { background-position: 0 0; } }
@media (prefers-reduced-motion: reduce) { .sk-bar { animation: none; } }
</style>
