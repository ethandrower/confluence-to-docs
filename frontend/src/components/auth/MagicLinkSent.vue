<template>
  <div class="magic-link-sent">
    <div class="icon">✉</div>
    <h2>Check your email</h2>
    <p>We sent a login link to your email address. Click the link to sign in.</p>
    <p class="hint">The link expires in 15 minutes. Check your spam folder if you don't see it.</p>
  </div>
</template>

<style scoped>
.magic-link-sent { text-align: center; padding: 1rem 0; }
.icon { font-size: 2.5rem; margin-bottom: 1rem; }
h2 { font-size: 1.25rem; font-weight: 600; margin-bottom: 0.5rem; }
p { color: var(--text-secondary); font-size: 0.9rem; margin-bottom: 0.5rem; }
.hint { font-size: 0.8rem; color: var(--text-secondary); }
</style>
