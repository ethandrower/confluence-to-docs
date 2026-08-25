<template>
  <div class="verify-page">
    <div class="verify-card">
      <div v-if="state === 'ready'" class="state-ready">
        <h2>Sign in to CiteMed Support</h2>
        <p>Click the button below to finish signing in. This link works once.</p>
        <button ref="signInBtn" class="btn-primary" @click="signIn">Sign in</button>
      </div>
      <div v-else-if="state === 'loading'" class="state-loading">
        <p>Verifying your login link...</p>
      </div>
      <div v-else-if="state === 'error'" class="state-error">
        <h2>Link expired or invalid</h2>
        <p>{{ error }}</p>
        <RouterLink to="/login" class="btn-link">Request a new link</RouterLink>
      </div>
      <div v-else class="state-success">
        <h2>Logged in!</h2>
        <p>Redirecting you now...</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth.js'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
// ready → loading → success | error. Starts at 'loading' only long enough for
// onMounted to read the token; a present token lands on 'ready'.
const state = ref('loading')
const error = ref('')
const signInBtn = ref(null)

// The token never touches reactive template state — held in module scope and
// sent once from the click handler.
let token = ''

onMounted(async () => {
  token = route.query.token || ''
  if (!token) {
    error.value = 'No token provided.'
    state.value = 'error'
    return
  }
  // Drop the token from the address bar as soon as it's been read. Sending it
  // to the API in a POST body keeps it out of server logs, but the SPA's own
  // URL would still carry it into browser history and into the Referer of any
  // request this page makes. replaceState (not push) so Back doesn't restore
  // it either. Query params other than the token are preserved.
  try {
    const url = new URL(window.location.href)
    if (url.searchParams.has('token')) {
      url.searchParams.delete('token')
      window.history.replaceState({}, '', url.pathname + url.search + url.hash)
    }
  } catch { /* non-browser env */ }
  // Deliberately do NOT verify here. Corporate email scanners (Defender Safe
  // Links, Proofpoint, …) open emailed URLs in a JS-executing sandbox before
  // the recipient ever sees the message; auto-verifying on load let that
  // sandbox burn the single-use token, so the human always got "already
  // used". Requiring one real click keeps scanners out: they render pages,
  // they don't press buttons.
  state.value = 'ready'
  await nextTick()
  signInBtn.value?.focus()
})

async function signIn() {
  state.value = 'loading'
  try {
    await auth.verifyToken(token)
    state.value = 'success'
    // Reject anything but a strictly internal path (must start with "/"
    // and not "//", which browsers treat as protocol-relative external).
    // Prevents using the verify URL as an open-redirect to attacker pages.
    const isInternal = (p) => typeof p === 'string' && p.startsWith('/') && !p.startsWith('//')
    // Prefer an explicit ?redirect; otherwise fall back to the path stashed at
    // the auth gate (the magic-link email doesn't carry ?redirect), so a
    // deep link like /support/:n survives the login round-trip. The stash is
    // consumed once and only if fresh (<30 min), so an abandoned attempt can't
    // hijack a later, unrelated login on the same browser.
    let stashed = null
    try {
      const raw = localStorage.getItem('pendingRedirect')
      localStorage.removeItem('pendingRedirect')
      if (raw) {
        const o = JSON.parse(raw)
        if (o && isInternal(o.p) && Date.now() - (o.t || 0) < 30 * 60 * 1000) stashed = o.p
      }
    } catch { /* private mode / bad JSON */ }
    const raw = route.query.redirect
    const target = isInternal(raw) ? raw : (stashed || '/docs')
    router.push(target)
  } catch (e) {
    error.value = e.response?.data?.error || 'This link has expired or already been used.'
    state.value = 'error'
  }
}
</script>

<style scoped>
.verify-page { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: var(--surface-1); }
.verify-card { background: white; border-radius: var(--radius-lg); padding: 2.5rem 2rem; width: 100%; max-width: 400px; text-align: center; box-shadow: 0 4px 24px rgba(0,0,0,0.08); }
.state-ready h2 { margin-bottom: 0.5rem; }
.state-ready p { color: var(--text-secondary); margin-bottom: 1.25rem; }
.btn-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 11px 24px;
  background: var(--primary);
  color: var(--primary-foreground);
  border: none;
  border-radius: var(--radius-sm);
  font-size: 0.9375rem;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  letter-spacing: -0.005em;
  transition: background 0.15s, transform 0.04s;
}
.btn-primary:hover { background: oklch(0.46 0.20 260); }
.btn-primary:active { transform: translateY(0.5px); }
.state-error h2 { color: #ef4444; margin-bottom: 0.5rem; }
.state-error p { color: var(--text-secondary); margin-bottom: 1rem; }
.btn-link { color: var(--accent); text-decoration: underline; }
.state-success h2 { color: #22c55e; }
.state-loading p { color: var(--text-secondary); }
</style>
