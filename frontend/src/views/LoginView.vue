<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-logo">
        <h1>CiteMed</h1>
        <p>Support Portal</p>
      </div>
      <LoginPage v-if="!linkSent" @sent="linkSent = true" />
      <MagicLinkSent v-else />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import LoginPage from '@/components/auth/LoginPage.vue'
import MagicLinkSent from '@/components/auth/MagicLinkSent.vue'

const linkSent = ref(false)
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--surface-1);
}
.login-card {
  background: white;
  border-radius: 12px;
  padding: 2.5rem 2rem;
  width: 100%;
  max-width: 400px;
  box-shadow: 0 4px 24px rgba(0,0,0,0.08);
}
.login-logo h1 {
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--accent);
  margin: 0;
}
.login-logo p {
  color: var(--text-secondary);
  margin: 0.25rem 0 2rem;
}
</style>
