<template>
  <AuthGate>
    <div class="ticket-detail-page">
      <RouterLink :to="{ name: 'ticket-list' }" class="back-link">← Back to tickets</RouterLink>
      <div v-if="loading" class="loading-state">Loading ticket...</div>
      <div v-else-if="error" class="error-state">{{ error }}</div>
      <div v-else-if="ticket" class="ticket-card">
        <div class="ticket-header">
          <span class="ticket-key">{{ ticket.issueKey }}</span>
          <span class="ticket-status">{{ ticket.currentStatus?.status || 'Open' }}</span>
        </div>
        <h1 class="ticket-summary">{{ ticket.requestFieldValues?.summary || ticket.summary }}</h1>
        <div class="ticket-meta">
          <span>Created: {{ formatDate(ticket.createdDate?.jira || ticket.created) }}</span>
        </div>
        <div class="ticket-description">
          <h3>Description</h3>
          <p>{{ ticket.requestFieldValues?.description || ticket.description }}</p>
        </div>
      </div>
    </div>
  </AuthGate>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useTicketsStore } from '@/stores/tickets.js'
import AuthGate from '@/components/auth/AuthGate.vue'

const props = defineProps({ id: String })
const store = useTicketsStore()
const ticket = ref(null)
const loading = ref(true)
const error = ref('')

function formatDate(dateStr) {
  if (!dateStr) return ''
  try {
    return new Date(dateStr).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
  } catch {
    return dateStr
  }
}

onMounted(async () => {
  try {
    ticket.value = await store.fetchTicket(props.id)
  } catch (e) {
    error.value = 'Failed to load ticket'
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.ticket-detail-page { max-width: 720px; }
.back-link { color: var(--accent); text-decoration: none; font-size: 0.875rem; display: block; margin-bottom: 1.5rem; }
.loading-state, .error-state { color: var(--text-secondary); padding: 2rem 0; }
.ticket-card { background: white; border: 1px solid var(--border); border-radius: 8px; padding: 1.5rem; }
.ticket-header { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.75rem; }
.ticket-key { font-family: monospace; font-size: 0.8rem; color: var(--text-secondary); }
.ticket-status { font-size: 0.75rem; font-weight: 500; padding: 3px 8px; border-radius: 12px; background: var(--surface-2); color: var(--text-secondary); }
.ticket-summary { font-size: 1.5rem; font-weight: 600; margin: 0 0 0.75rem; }
.ticket-meta { font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 1.5rem; }
.ticket-description h3 { font-size: 0.9rem; font-weight: 600; margin-bottom: 0.5rem; }
.ticket-description p { color: var(--text-secondary); white-space: pre-wrap; }
</style>
