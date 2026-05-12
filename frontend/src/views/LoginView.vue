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
    <p class="login-footnote">
      Trouble signing in? Email
      <a href="mailto:support@citemed.com">support@citemed.com</a>
    </p>
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
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--background);
  padding: 24px;
  gap: 20px;
}

.login-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 40px 36px 32px;
  width: 100%;
  max-width: 420px;
  box-shadow:
    0 1px 2px oklch(0 0 0 / 0.04),
    0 8px 32px oklch(0.52 0.20 260 / 0.06);
}

.login-logo {
  margin-bottom: 28px;
  text-align: left;
}

.login-logo h1 {
  font-size: 1.625rem;
  font-weight: 700;
  color: var(--primary);
  margin: 0;
  letter-spacing: -0.02em;
  line-height: 1.1;
}

.login-logo p {
  color: var(--muted-foreground);
  font-size: 0.875rem;
  margin: 4px 0 0;
  font-weight: 450;
}

.login-footnote {
  font-size: 0.75rem;
  color: var(--muted-foreground);
  margin: 0;
  text-align: center;
}

.login-footnote a {
  color: var(--primary);
  text-decoration: none;
  font-weight: 500;
}

.login-footnote a:hover {
  text-decoration: underline;
}
</style>
