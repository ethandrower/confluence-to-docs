<template>
  <div class="app-shell">
    <AppShell>
      <template #sidebar>
        <nav class="ticket-nav">
          <RouterLink :to="{ name: 'ticket-list' }" class="nav-link">My Tickets</RouterLink>
          <RouterLink :to="{ name: 'ticket-new' }" class="nav-link">Submit Ticket</RouterLink>
        </nav>
      </template>
      <template #content>
        <RouterView />
      </template>
    </AppShell>
  </div>
</template>

<script setup>
import AppShell from '@/components/layout/AppShell.vue'
</script>

<style scoped>
.ticket-nav {
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.nav-link {
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  color: var(--text-primary);
  text-decoration: none;
  font-size: 0.9rem;
}
.nav-link:hover { background: var(--surface-2); }
.nav-link.router-link-active { background: var(--accent-light); color: var(--accent); font-weight: 500; }
</style>
