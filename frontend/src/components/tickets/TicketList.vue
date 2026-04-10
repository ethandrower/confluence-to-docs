<template>
  <AuthGate>
    <div class="ticket-list-page">
      <div class="list-header">
        <h1>My Tickets</h1>
        <RouterLink :to="{ name: 'ticket-new' }" class="btn-primary">New Ticket</RouterLink>
      </div>
      <div v-if="store.loading" class="loading-state">Loading...</div>
      <div v-else-if="store.error" class="error-state">{{ store.error }}</div>
      <div v-else-if="!store.tickets.length" class="empty-state">
        <p>You haven't submitted any tickets yet.</p>
        <RouterLink v-if="auth.canSubmitTickets" :to="{ name: 'ticket-new' }">Submit your first ticket</RouterLink>
      </div>
      <div v-else class="tickets">
        <RouterLink
          v-for="ticket in store.tickets"
          :key="ticket.issueKey || ticket.id"
          :to="{ name: 'ticket-detail', params: { id: ticket.issueKey || ticket.id } }"
          class="ticket-row"
        >
          <div class="ticket-main">
            <span class="ticket-key">{{ ticket.issueKey }}</span>
            <span class="ticket-summary">{{ ticket.requestFieldValues?.summary || ticket.summary }}</span>
          </div>
          <span class="ticket-status" :class="`status-${(ticket.currentStatus?.status || '').toLowerCase().replace(/\s+/g, '-')}`">
            {{ ticket.currentStatus?.status || 'Open' }}
          </span>
        </RouterLink>
      </div>
    </div>
  </AuthGate>
</template>

<script setup>
import { onMounted } from 'vue'
import { useTicketsStore } from '@/stores/tickets.js'
import { useAuthStore } from '@/stores/auth.js'
import AuthGate from '@/components/auth/AuthGate.vue'

const store = useTicketsStore()
const auth = useAuthStore()
onMounted(() => store.fetchTickets())
</script>

<style scoped>
.ticket-list-page { max-width: 800px; }
.list-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.5rem; }
h1 { font-size: 1.75rem; font-weight: 700; margin: 0; }
.btn-primary {
  padding: 8px 16px;
  background: var(--accent);
  color: white;
  border-radius: 6px;
  text-decoration: none;
  font-size: 0.875rem;
  font-weight: 500;
}
.loading-state, .error-state, .empty-state { color: var(--text-secondary); padding: 2rem 0; }
.tickets { display: flex; flex-direction: column; gap: 0.5rem; }
.ticket-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border: 1px solid var(--border);
  border-radius: 8px;
  text-decoration: none;
  color: var(--text-primary);
  background: white;
}
.ticket-row:hover { border-color: var(--accent); background: var(--accent-light); }
.ticket-main { display: flex; align-items: center; gap: 0.75rem; }
.ticket-key { font-size: 0.8rem; color: var(--text-secondary); font-family: monospace; }
.ticket-summary { font-size: 0.9rem; }
.ticket-status {
  font-size: 0.75rem;
  font-weight: 500;
  padding: 3px 8px;
  border-radius: 12px;
  background: var(--surface-2);
  color: var(--text-secondary);
  white-space: nowrap;
}
</style>
