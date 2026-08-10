<script setup>
/**
 * Agent-only helper for opening the portal as a sandbox customer, so staff can
 * check what a customer actually sees without keeping a second set of
 * credentials around.
 *
 * It hands over a URL to copy rather than navigating, on purpose: the session
 * cookie belongs to the browser, not the tab, so following the link here would
 * sign the agent out of their own session. A private window keeps both
 * perspectives open at once, which is the point.
 */
import { ref } from 'vue'
import axios from 'axios'

const open = ref(false)
const accounts = ref([])
const loading = ref(false)
const error = ref('')
const copied = ref('')

async function toggle() {
  open.value = !open.value
  if (!open.value || accounts.value.length) return
  loading.value = true
  error.value = ''
  try {
    const res = await axios.get('/api/admin/demo-accounts/')
    accounts.value = res.data.accounts || []
  } catch {
    error.value = 'Could not load sandbox accounts.'
  } finally {
    loading.value = false
  }
}

async function copy(account) {
  try {
    await navigator.clipboard.writeText(account.login_url)
    copied.value = account.email
    setTimeout(() => { if (copied.value === account.email) copied.value = '' }, 2000)
  } catch {
    error.value = 'Copy failed — select the link and copy it manually.'
  }
}
</script>

<template>
  <div class="vac">
    <button type="button" class="topbar-btn-ghost hidden sm:inline-flex"
            :aria-expanded="open" aria-haspopup="dialog"
            title="Open the portal as a sandbox customer"
            @click="toggle">
      View as customer
    </button>

    <div v-if="open" class="vac-panel" role="dialog" aria-label="View as customer">
      <p class="vac-note">
        Open one of these in a <strong>private window</strong> — signing in here
        would replace your own agent session.
      </p>

      <p v-if="loading" class="vac-muted">Loading…</p>
      <p v-else-if="error" class="vac-error">{{ error }}</p>
      <p v-else-if="!accounts.length" class="vac-muted">
        No sandbox accounts yet. Mark a customer <code>is_demo</code> to add one.
      </p>

      <ul v-else class="vac-list">
        <li v-for="a in accounts" :key="a.email">
          <div class="vac-who">
            <span class="vac-name">{{ a.name || a.email }}</span>
            <span v-if="a.company" class="vac-co">{{ a.company }}</span>
          </div>
          <button type="button" class="vac-copy" @click="copy(a)">
            {{ copied === a.email ? 'Copied' : 'Copy link' }}
          </button>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.vac { position: relative; }

.vac-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 300;
  width: 320px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--popover, var(--background));
  color: var(--foreground);
  box-shadow: 0 10px 30px rgb(0 0 0 / 18%);
}

.vac-note { margin: 0 0 10px; font-size: 12px; line-height: 1.45; color: var(--muted-foreground); }
.vac-muted { margin: 0; font-size: 13px; color: var(--muted-foreground); }
.vac-error { margin: 0; font-size: 13px; color: var(--destructive, #b91c1c); }

.vac-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.vac-list li { display: flex; align-items: center; justify-content: space-between; gap: 10px; }

.vac-who { display: flex; flex-direction: column; min-width: 0; }
.vac-name { font-size: 13px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.vac-co { font-size: 11px; color: var(--muted-foreground); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.vac-copy {
  flex: none;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: transparent;
  color: var(--foreground);
  font-size: 12px;
  cursor: pointer;
}
.vac-copy:hover { background: var(--muted); }
</style>
