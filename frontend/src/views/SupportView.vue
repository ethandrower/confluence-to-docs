<template>
  <AppShell hide-sidebar>
    <template #content>
      <div class="sv" :class="{ 'sv--thread': number }">
        <template v-if="number">
          <div class="sv-thread-top">
            <RouterLink :to="{ name: 'support' }" class="sv-back">
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" />
              </svg>
              All tickets
            </RouterLink>
            <button class="refresh-btn" :class="store.loading && 'is-spinning'" :disabled="store.loading" title="Refresh conversation" aria-label="Refresh conversation" @click="store.fetchTicket(number)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v5h-5"/></svg>
              {{ store.loading ? 'Refreshing…' : 'Refresh' }}
            </button>
          </div>

          <template v-if="store.loading && !store.current">
            <div class="skeleton-head" />
            <div class="skeleton-row" v-for="n in 3" :key="n" />
          </template>
          <p v-else-if="store.error" class="sv-error">{{ store.error }}</p>
          <TicketThread v-else-if="store.current" :ticket="store.current" />
        </template>

        <template v-else>
          <header class="sv-head">
            <h1>Support tickets</h1>
            <div class="sv-head-actions">
              <button class="refresh-btn" :class="store.loading && 'is-spinning'" :disabled="store.loading" title="Refresh" aria-label="Refresh tickets" @click="store.fetchTickets()">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v5h-5"/></svg>
                {{ store.loading ? 'Refreshing…' : 'Refresh' }}
              </button>
              <button class="btn-primary" @click="showForm = !showForm">
                {{ showForm ? 'Cancel' : 'New ticket' }}
              </button>
            </div>
          </header>

          <NewTicketForm v-if="showForm" @created="onCreated" @cancel="showForm = false" />

          <template v-if="store.loading && !store.tickets.length">
            <div class="skeleton-row" v-for="n in 3" :key="n" />
          </template>
          <p v-else-if="store.error" class="sv-error">{{ store.error }}</p>
          <TicketList v-else :tickets="store.tickets" :is-first-run="isFirstRun" />
        </template>
      </div>
    </template>
  </AppShell>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AppShell from '@/components/layout/AppShell.vue'
import TicketList from '@/components/support/TicketList.vue'
import TicketThread from '@/components/support/TicketThread.vue'
import NewTicketForm from '@/components/support/NewTicketForm.vue'
import { useTicketsStore } from '@/stores/tickets'
import { usePolling } from '@/lib/usePolling'

const props = defineProps({
  number: { type: [String, Number], default: null },
})

const router = useRouter()
const store = useTicketsStore()
const showForm = ref(false)

const isFirstRun = computed(() => !store.tickets.length)

function load() {
  if (props.number) {
    store.fetchTicket(props.number)
  } else {
    store.fetchTickets()
  }
}

usePolling(() => store.fetchTickets({ silent: true }), {
  intervalMs: 15000,
  enabled: () => !props.number,
})

function onCreated(ticket) {
  showForm.value = false
  router.push({ name: 'support-ticket', params: { number: ticket.number } })
}

onMounted(load)
watch(() => props.number, load)
</script>

<style scoped>
.sv {
  max-width: 860px;
  margin: 0 auto;
  padding: clamp(1.25rem, 3vw, 2rem);
}
/* Thread view: fill the height so the conversation scrolls inside its own
   region (fixed header + docked reply), instead of the whole page scrolling. */
.sv--thread {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding-bottom: clamp(1rem, 2vw, 1.5rem);
}
.sv--thread .sv-thread-top { flex-shrink: 0; }

.sv-thread-top { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: 18px; }
.sv-back {
  display: inline-flex; align-items: center; gap: 6px;
  font-family: var(--font-ui); font-size: 13px; font-weight: 500;
  color: var(--muted-foreground);
  padding: 6px 10px 6px 6px; border-radius: 8px;
  transition: color 0.15s, background 0.15s;
}
.sv-back:hover { color: var(--foreground); background: var(--muted); }
.sv-back:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }

.sv-head { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: 1.25rem; }
.sv-head h1 { font-family: var(--font-ui); font-size: 1.5rem; font-weight: 700; letter-spacing: -0.01em; color: var(--foreground); margin: 0; min-width: 0; }
.sv-head-actions { display: flex; align-items: center; gap: 0.6rem; flex-shrink: 0; }

.refresh-btn { flex-shrink: 0; display: inline-flex; align-items: center; gap: 6px; height: 34px; padding: 0 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--card); color: var(--muted-foreground); font: inherit; font-size: 0.82rem; font-weight: 600; cursor: pointer; transition: color 0.15s, border-color 0.15s, background 0.15s; }
.refresh-btn svg { width: 15px; height: 15px; }
.refresh-btn:hover { color: var(--brand-accent); border-color: var(--brand-accent); }
.refresh-btn:disabled { opacity: 0.6; cursor: default; }
.refresh-btn.is-spinning svg { animation: rspin 0.7s linear infinite; }
@keyframes rspin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .refresh-btn.is-spinning svg { animation: none; } }

.btn-primary { background: var(--primary); color: var(--primary-foreground); border: none; border-radius: 8px; height: 34px; padding: 0 14px; cursor: pointer; font: inherit; font-size: 0.82rem; font-weight: 600; white-space: nowrap; flex-shrink: 0; transition: opacity 0.15s; }
.btn-primary:hover { opacity: 0.9; }

.sv-error { color: var(--destructive); font-size: 0.9rem; padding: 1rem; border: 1px solid color-mix(in srgb, var(--destructive) 30%, var(--border)); border-radius: var(--radius-md); background: color-mix(in srgb, var(--destructive) 6%, transparent); }

.skeleton-head, .skeleton-row {
  border-radius: var(--radius-md);
  background: linear-gradient(90deg, var(--muted) 25%, var(--secondary) 37%, var(--muted) 63%);
  background-size: 400% 100%;
  animation: shimmer 1.4s ease infinite;
}
.skeleton-head { height: 28px; width: 40%; margin-bottom: 1.25rem; }
.skeleton-row { height: 54px; margin-bottom: 0.4rem; }
@keyframes shimmer { 0% { background-position: 100% 0; } 100% { background-position: 0 0; } }
@media (prefers-reduced-motion: reduce) { .skeleton-head, .skeleton-row { animation: none; } }
</style>
