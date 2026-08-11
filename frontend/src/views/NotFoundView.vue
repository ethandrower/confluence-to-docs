<template>
  <div class="nf-page">
    <div class="nf-card">
      <p class="nf-code">404</p>
      <h1 class="nf-title">This page doesn’t exist</h1>
      <p class="nf-body">
        The link may be out of date, or the page may have moved. Nothing has gone
        wrong with your account.
      </p>
      <div class="nf-actions">
        <RouterLink class="nf-btn nf-btn--primary" :to="{ name: 'docs-home' }">
          Go to documentation
        </RouterLink>
        <RouterLink class="nf-btn" :to="{ name: 'contact' }">Contact support</RouterLink>
      </div>
    </div>
    <p class="nf-footnote">
      Still stuck? Email <a href="mailto:support@citemed.com">support@citemed.com</a>
    </p>
  </div>
</template>

<script setup>
// Deliberately standalone rather than wrapped in AppShell: this renders for
// signed-out visitors too (the catch-all route has no requiresAuth), and
// AppShell's nav assumes a resolved user. A 404 that itself errors because it
// couldn't find a user would be a poor way to report that something is missing.
import { RouterLink } from 'vue-router'
</script>

<style scoped>
.nf-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--background);
  padding: 24px;
  gap: 20px;
}

.nf-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 40px;
  width: 100%;
  max-width: 460px;
  text-align: center;
}

.nf-code {
  font-family: var(--font-ui);
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.14em;
  color: var(--muted-foreground);
  margin: 0 0 10px;
}

.nf-title {
  font-family: var(--font-ui);
  font-size: 1.4rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--foreground);
  margin: 0 0 10px;
}

.nf-body {
  font-size: 0.9rem;
  line-height: 1.55;
  color: var(--muted-foreground);
  margin: 0 0 24px;
}

.nf-actions {
  display: flex;
  gap: 10px;
  justify-content: center;
  flex-wrap: wrap;
}

.nf-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 38px;
  padding: 0 18px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--card);
  color: var(--foreground);
  font-family: var(--font-ui);
  font-size: 0.87rem;
  font-weight: 600;
  text-decoration: none;
}

.nf-btn:hover { background: var(--accent); }

.nf-btn--primary {
  background: var(--primary);
  border-color: var(--primary);
  color: var(--primary-foreground);
}

.nf-btn--primary:hover { opacity: 0.92; }

.nf-footnote {
  font-size: 0.83rem;
  color: var(--muted-foreground);
}

.nf-footnote a { color: var(--brand-accent, var(--primary)); }
</style>
