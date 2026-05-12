<template>
  <div class="magic-link-sent">
    <div class="icon-wrap">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
        <polyline points="22,6 12,13 2,6" />
      </svg>
    </div>
    <h2>Check your email</h2>
    <p>We sent a sign-in link. Click the link in the message to securely log in.</p>
    <p class="hint">The link is valid for 60 minutes and can only be used once. Check your spam folder if it doesn't arrive.</p>
  </div>
</template>

<style scoped>
.magic-link-sent {
  text-align: center;
  padding: 8px 0 4px;
}

.icon-wrap {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  border-radius: 14px;
  background: oklch(0.52 0.20 260 / 0.10);
  color: var(--primary);
  margin: 0 auto 18px;
}

h2 {
  font-size: 1.125rem;
  font-weight: 600;
  margin: 0 0 8px;
  color: var(--foreground);
  letter-spacing: -0.01em;
}

p {
  color: var(--muted-foreground);
  font-size: 0.9375rem;
  line-height: 1.5;
  margin: 0 0 10px;
}

.hint {
  font-size: 0.75rem;
  color: var(--muted-foreground);
  opacity: 0.85;
  line-height: 1.5;
  margin-top: 12px;
}
</style>
