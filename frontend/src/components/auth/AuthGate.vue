<template>
  <slot v-if="auth.user" />
  <div v-else class="auth-gate">
    <p>Please <RouterLink to="/login">log in</RouterLink> to access this page.</p>
  </div>
</template>

<script setup>
import { useAuthStore } from '@/stores/auth.js'
const auth = useAuthStore()
</script>

<style scoped>
.auth-gate { padding: 2rem; text-align: center; color: var(--text-secondary); }
.auth-gate a { color: var(--accent); }
</style>
