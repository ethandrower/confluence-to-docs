<template>
  <AppShell hide-sidebar>
    <template #content>
      <div class="admin">
        <RouterLink to="/docs" class="back-link">
          <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" /></svg>
          Back to docs
        </RouterLink>

        <header class="admin-head">
          <div>
            <h1>Manage access</h1>
            <p>Add companies and people, and control who can sign in to the support portal.</p>
          </div>
          <button class="btn-sync" :disabled="syncing" @click="runSync">
            <svg class="w-4 h-4" :class="syncing && 'spin'" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
            </svg>
            {{ syncing ? 'Syncing…' : 'Sync from Confluence' }}
          </button>
        </header>
        <p v-if="syncMsg" class="sync-msg">{{ syncMsg }}</p>

        <div class="tabs" role="tablist">
          <button role="tab" :aria-selected="tab==='users'" class="tab" :class="tab==='users' && 'tab--active'" @click="tab='users'">
            Users <span class="tab-count">{{ store.users.length }}</span>
          </button>
          <button role="tab" :aria-selected="tab==='companies'" class="tab" :class="tab==='companies' && 'tab--active'" @click="tab='companies'">
            Companies <span class="tab-count">{{ store.companies.length }}</span>
          </button>
        </div>

        <p v-if="store.error" class="admin-error">{{ store.error }}</p>

        <!-- USERS -->
        <section v-show="tab==='users'" class="panel">
          <div class="panel-bar">
            <span class="panel-hint">Only people listed here (and enabled) can sign in.</span>
            <button class="btn-primary" @click="openUser()">+ Add user</button>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr><th>Email</th><th>Name</th><th>Role</th><th>Company</th><th class="ta-c">Access</th><th></th></tr>
              </thead>
              <tbody>
                <tr v-for="u in store.users" :key="u.id">
                  <td class="mono">{{ u.email }}</td>
                  <td>{{ u.name || '—' }}</td>
                  <td><span class="role" :class="u.role==='admin' ? 'role--admin' : 'role--customer'">{{ u.role }}</span></td>
                  <td>{{ u.company_name || '—' }}</td>
                  <td class="ta-c">
                    <button class="switch" :class="u.access_enabled && 'switch--on'" :aria-pressed="u.access_enabled" @click="toggleAccess(u)" :title="u.access_enabled ? 'Enabled' : 'Disabled'"><span class="switch-knob" /></button>
                  </td>
                  <td class="ta-r">
                    <button class="icon-btn" @click="openUser(u)" aria-label="Edit user">✎</button>
                    <button class="icon-btn icon-btn--danger" @click="remove('user', u)" aria-label="Remove user">✕</button>
                  </td>
                </tr>
                <tr v-if="!store.users.length"><td colspan="6" class="empty">No users yet.</td></tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- COMPANIES -->
        <section v-show="tab==='companies'" class="panel">
          <div class="panel-bar">
            <span class="panel-hint">Companies group your users; set the contract end date here.</span>
            <button class="btn-primary" @click="openCompany()">+ Add company</button>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr><th>Company</th><th>Contract end date</th><th class="ta-c">Users</th><th></th></tr>
              </thead>
              <tbody>
                <tr v-for="c in store.companies" :key="c.id">
                  <td>{{ c.name }}</td>
                  <td>{{ c.contract_end_date ? formatDate(c.contract_end_date) : '—' }}</td>
                  <td class="ta-c tabular">{{ c.user_count }}</td>
                  <td class="ta-r">
                    <button class="icon-btn" @click="openCompany(c)" aria-label="Edit company">✎</button>
                    <button class="icon-btn icon-btn--danger" @click="remove('company', c)" aria-label="Remove company">✕</button>
                  </td>
                </tr>
                <tr v-if="!store.companies.length"><td colspan="4" class="empty">No companies yet.</td></tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <!-- Modal -->
      <Transition name="modal">
        <div v-if="modal" class="modal-overlay" @click.self="modal=null">
          <div class="modal" role="dialog" aria-modal="true">
            <h2 class="modal-title">{{ modalTitle }}</h2>
            <p v-if="formError" class="form-error">{{ formError }}</p>

            <template v-if="modal==='user'">
              <label class="field"><span>Email</span>
                <input v-model="form.email" type="email" :disabled="!!editing" placeholder="person@company.com" />
              </label>
              <label class="field"><span>Name</span>
                <input v-model="form.name" type="text" placeholder="Full name (optional)" />
              </label>
              <label class="field"><span>Role</span>
                <select v-model="form.role">
                  <option value="customer">Customer</option>
                  <option value="admin">Admin</option>
                </select>
              </label>
              <label class="field"><span>Company</span>
                <select v-model="form.company_id">
                  <option :value="null">— None —</option>
                  <option v-for="c in store.companies" :key="c.id" :value="c.id">{{ c.name }}</option>
                </select>
              </label>
              <label class="check"><input type="checkbox" v-model="form.access_enabled" /> <span>Access enabled (can sign in)</span></label>
            </template>

            <template v-else>
              <label class="field"><span>Company name</span>
                <input v-model="form.name" type="text" placeholder="e.g. Abiomed" />
              </label>
              <label class="field"><span>Contract end date</span>
                <input v-model="form.contract_end_date" type="date" />
              </label>
            </template>

            <div class="modal-actions">
              <button class="btn-ghost" @click="modal=null">Cancel</button>
              <button class="btn-primary" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save' }}</button>
            </div>
          </div>
        </div>
      </Transition>
    </template>
  </AppShell>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import AppShell from '@/components/layout/AppShell.vue'
import { useAdminStore } from '@/stores/admin.js'

const store = useAdminStore()
const tab = ref('users')
const modal = ref(null)      // 'user' | 'company' | null
const editing = ref(null)    // record being edited, or null for create
const saving = ref(false)
const formError = ref('')
const form = ref({})
const syncing = ref(false)
const syncMsg = ref('')

async function runSync() {
  syncing.value = true
  syncMsg.value = ''
  try {
    syncMsg.value = await store.syncDocs()
  } catch (e) {
    syncMsg.value = e.response?.data?.error || 'Could not start sync'
  } finally {
    setTimeout(() => { syncing.value = false }, 1200)
  }
}

const modalTitle = computed(() => {
  const noun = modal.value === 'user' ? 'user' : 'company'
  return `${editing.value ? 'Edit' : 'Add'} ${noun}`
})

function openUser(u = null) {
  editing.value = u
  formError.value = ''
  form.value = u
    ? { email: u.email, name: u.name, role: u.role, company_id: u.company_id, access_enabled: u.access_enabled }
    : { email: '', name: '', role: 'customer', company_id: null, access_enabled: true }
  modal.value = 'user'
}
function openCompany(c = null) {
  editing.value = c
  formError.value = ''
  form.value = c
    ? { name: c.name, contract_end_date: c.contract_end_date || '' }
    : { name: '', contract_end_date: '' }
  modal.value = 'company'
}

async function save() {
  saving.value = true
  formError.value = ''
  try {
    if (modal.value === 'user') {
      const payload = { name: form.value.name, role: form.value.role, company_id: form.value.company_id, access_enabled: form.value.access_enabled }
      if (editing.value) await store.updateUser(editing.value.id, payload)
      else await store.createUser({ ...payload, email: form.value.email })
    } else {
      const payload = { name: form.value.name, contract_end_date: form.value.contract_end_date || null }
      if (editing.value) await store.updateCompany(editing.value.id, payload)
      else await store.createCompany(payload)
    }
    modal.value = null
  } catch (e) {
    formError.value = e.response?.data?.error || 'Something went wrong'
  } finally {
    saving.value = false
  }
}

async function toggleAccess(u) {
  try {
    await store.updateUser(u.id, { access_enabled: !u.access_enabled })
  } catch (e) {
    store.error = e.response?.data?.error || 'Could not update access'
  }
}

async function remove(type, item) {
  const label = type === 'user' ? item.email : item.name
  if (!confirm(`Remove ${label}? This can't be undone.`)) return
  try {
    if (type === 'user') await store.deleteUser(item.id)
    else await store.deleteCompany(item.id)
  } catch (e) {
    store.error = e.response?.data?.error || 'Could not delete'
  }
}

function formatDate(iso) {
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

onMounted(() => store.fetchAll())
</script>

<style scoped>
.admin { max-width: 1400px; margin: 0 auto; padding: 24px clamp(1.5rem, 4vw, 3rem) 64px; }
.back-link {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 13px; font-weight: 500; color: var(--muted-foreground);
  padding: 6px 10px 6px 6px; border-radius: 8px; margin-bottom: 14px;
  transition: color 0.15s, background 0.15s;
}
.back-link:hover { color: var(--foreground); background: var(--muted); }

.admin-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.admin-head h1 { font-family: var(--font-ui); font-size: 1.7rem; font-weight: 600; letter-spacing: -0.02em; color: var(--foreground); margin: 0; }
.admin-head p { color: var(--muted-foreground); font-size: 0.95rem; margin: 6px 0 0; }
.btn-sync {
  flex-shrink: 0; display: inline-flex; align-items: center; gap: 7px;
  font-family: var(--font-ui); font-size: 13px; font-weight: 500;
  color: var(--foreground); border: 1px solid var(--border); background: var(--card);
  padding: 8px 13px; border-radius: 9px; transition: background 0.15s, border-color 0.15s;
}
.btn-sync:hover { background: var(--muted); border-color: var(--accent-hover); }
.btn-sync:disabled { opacity: 0.7; }
.btn-sync .spin { animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.sync-msg { margin: 10px 0 0; font-size: 13px; color: var(--brand-accent); }

.tabs { display: flex; gap: 4px; margin: 22px 0 18px; border-bottom: 1px solid var(--border); }
.tab {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 9px 14px; font-family: var(--font-ui); font-size: 14px; font-weight: 550;
  color: var(--muted-foreground); border-bottom: 2px solid transparent; margin-bottom: -1px;
  transition: color 0.15s, border-color 0.15s;
}
.tab:hover { color: var(--foreground); }
.tab--active { color: var(--primary); border-bottom-color: var(--primary); }
.dark .tab--active { color: var(--foreground); border-bottom-color: var(--brand-accent); }
.tab-count { font-size: 11px; font-weight: 600; color: var(--muted-foreground); background: var(--muted); padding: 1px 7px; border-radius: 10px; }

.admin-error { color: var(--destructive); font-size: 0.9rem; margin: 8px 0; }

.panel-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.panel-hint { font-size: 12.5px; color: var(--muted-foreground); }

.table-wrap { border: 1px solid var(--border); border-radius: 12px; overflow: hidden; background: var(--card); }
table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13.5px; }
th { text-align: left; font-family: var(--font-ui); font-size: 11px; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; color: var(--muted-foreground); padding: 11px 14px; background: var(--muted); border-bottom: 1px solid var(--border); }
td { padding: 11px 14px; border-bottom: 1px solid var(--border-subtle); color: var(--foreground); vertical-align: middle; }
tbody tr:last-child td { border-bottom: none; }
tbody tr:hover td { background: var(--accent); }
.mono { font-family: 'Menlo','Monaco',ui-monospace,monospace; font-size: 12.5px; }
.tabular { font-variant-numeric: tabular-nums; }
.ta-c { text-align: center; } .ta-r { text-align: right; white-space: nowrap; }
.empty { text-align: center; color: var(--muted-foreground); padding: 28px; }

.role { font-family: var(--font-ui); font-size: 11px; font-weight: 600; text-transform: capitalize; padding: 2px 9px; border-radius: 6px; }
.role--admin { color: var(--primary); background: var(--accent); }
.dark .role--admin { color: var(--accent-foreground); }
.role--customer { color: var(--muted-foreground); background: var(--muted); }

.switch { width: 36px; height: 20px; border-radius: 999px; background: var(--input); position: relative; transition: background 0.18s; }
.switch--on { background: var(--primary); }
.switch-knob { position: absolute; top: 2px; left: 2px; width: 16px; height: 16px; border-radius: 50%; background: #fff; transition: transform 0.18s; box-shadow: 0 1px 2px oklch(0 0 0 / 0.2); }
.switch--on .switch-knob { transform: translateX(16px); }

.icon-btn { width: 28px; height: 28px; border-radius: 6px; color: var(--muted-foreground); font-size: 13px; transition: color 0.15s, background 0.15s; }
.icon-btn:hover { color: var(--foreground); background: var(--muted); }
.icon-btn--danger:hover { color: var(--destructive); background: color-mix(in srgb, var(--destructive) 12%, transparent); }

.btn-primary { background: var(--primary); color: var(--primary-foreground); font-family: var(--font-ui); font-size: 13.5px; font-weight: 550; padding: 8px 14px; border-radius: 8px; transition: filter 0.15s; }
.btn-primary:hover { filter: brightness(0.94); }
.btn-primary:disabled { opacity: 0.6; }
.btn-ghost { color: var(--muted-foreground); font-family: var(--font-ui); font-size: 13.5px; font-weight: 500; padding: 8px 14px; border-radius: 8px; }
.btn-ghost:hover { background: var(--muted); color: var(--foreground); }

/* Modal */
.modal-overlay { position: fixed; inset: 0; z-index: 60; background: oklch(0 0 0 / 0.45); display: flex; align-items: center; justify-content: center; padding: 20px; }
.modal { width: 100%; max-width: 440px; background: var(--popover); border: 1px solid var(--border); border-radius: 14px; padding: 22px; box-shadow: 0 20px 50px oklch(0 0 0 / 0.25); }
.modal-title { font-family: var(--font-ui); font-size: 1.15rem; font-weight: 600; color: var(--foreground); margin: 0 0 14px; }
.form-error { color: var(--destructive); font-size: 0.85rem; margin: 0 0 10px; }
.field { display: block; margin-bottom: 13px; }
.field > span { display: block; font-family: var(--font-ui); font-size: 12px; font-weight: 600; color: var(--muted-foreground); margin-bottom: 5px; }
.field input, .field select { width: 100%; height: 38px; padding: 0 11px; border-radius: 8px; border: 1px solid var(--input); background: var(--background); color: var(--foreground); font-size: 14px; }
.field input:focus, .field select:focus { outline: 2px solid var(--ring); outline-offset: -1px; border-color: var(--ring); }
.field input:disabled { opacity: 0.6; }
.check { display: flex; align-items: center; gap: 8px; font-size: 13.5px; color: var(--foreground); margin: 4px 0 2px; }
.check input { accent-color: var(--primary); width: 16px; height: 16px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 18px; }

.modal-enter-active, .modal-leave-active { transition: opacity 0.18s; }
.modal-enter-from, .modal-leave-to { opacity: 0; }
</style>
