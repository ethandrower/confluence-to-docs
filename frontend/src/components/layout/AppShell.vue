<template>
  <div class="shell" :class="{ 'sidebar-open': sidebarOpen }">
    <header class="topbar">
      <button class="menu-btn" @click="sidebarOpen = !sidebarOpen" aria-label="Toggle menu">
        <span class="hamburger" />
      </button>
      <RouterLink to="/" class="brand">CiteMed Support</RouterLink>
      <SearchBar class="topbar-search" />
      <nav class="topbar-nav">
        <RouterLink to="/docs">Docs</RouterLink>
        <RouterLink to="/tickets">Tickets</RouterLink>
        <span v-if="auth.user" class="user-badge">{{ auth.user.email }}</span>
        <RouterLink v-else to="/login" class="login-link">Log in</RouterLink>
      </nav>
    </header>
    <div class="shell-body">
      <aside class="sidebar" :class="{ open: sidebarOpen }">
        <div class="sidebar-overlay" @click="sidebarOpen = false" />
        <div class="sidebar-inner">
          <slot name="sidebar" />
        </div>
      </aside>
      <main class="main-content">
        <slot name="content" />
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth.js'
import SearchBar from './SearchBar.vue'

const auth = useAuthStore()
const sidebarOpen = ref(false)
</script>

<style scoped>
.shell { display: flex; flex-direction: column; min-height: 100vh; }
.topbar {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0 1.5rem;
  height: 56px;
  border-bottom: 1px solid var(--border);
  background: white;
  position: sticky;
  top: 0;
  z-index: 100;
}
.brand { font-weight: 700; font-size: 1rem; color: var(--accent); text-decoration: none; white-space: nowrap; }
.topbar-search { flex: 1; max-width: 360px; }
.topbar-nav { display: flex; align-items: center; gap: 1rem; margin-left: auto; font-size: 0.9rem; }
.topbar-nav a { color: var(--text-secondary); text-decoration: none; }
.topbar-nav a:hover, .topbar-nav a.router-link-active { color: var(--accent); }
.user-badge { font-size: 0.8rem; color: var(--text-secondary); max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.shell-body { display: flex; flex: 1; }
.sidebar {
  width: 260px;
  min-width: 260px;
  border-right: 1px solid var(--border);
  background: var(--surface-1);
  overflow-y: auto;
  height: calc(100vh - 56px);
  position: sticky;
  top: 56px;
}
.sidebar-inner { padding: 1rem 0; }
.sidebar-overlay { display: none; }
.main-content { flex: 1; padding: 2rem; max-width: 900px; overflow-x: hidden; }
.menu-btn { display: none; background: none; border: none; cursor: pointer; padding: 4px; }
.hamburger { display: block; width: 20px; height: 2px; background: var(--text-primary); position: relative; }
.hamburger::before, .hamburger::after {
  content: '';
  display: block;
  width: 20px;
  height: 2px;
  background: var(--text-primary);
  position: absolute;
}
.hamburger::before { top: -6px; }
.hamburger::after { top: 6px; }

@media (max-width: 768px) {
  .menu-btn { display: block; }
  .topbar-search { display: none; }
  .sidebar {
    position: fixed;
    left: -260px;
    top: 56px;
    height: calc(100vh - 56px);
    z-index: 200;
    transition: left 0.25s ease;
  }
  .sidebar.open { left: 0; }
  .sidebar-overlay {
    display: block;
    position: fixed;
    inset: 56px 0 0 0;
    background: rgba(0,0,0,0.3);
    z-index: 199;
  }
  .sidebar:not(.open) .sidebar-overlay { display: none; }
  .main-content { padding: 1rem; }
}
</style>
