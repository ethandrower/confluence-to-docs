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
          <div class="head-actions">
            <button class="btn-sync" @click="openAddPage">
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v6m3-3H9m12 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
              </svg>
              Add a page
            </button>
            <button class="btn-sync" :disabled="syncing" @click="runSync">
              <svg class="w-4 h-4" :class="syncing && 'spin'" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
              </svg>
              {{ syncing ? 'Syncing…' : 'Sync from Confluence' }}
            </button>
          </div>
        </header>
        <p v-if="syncMsg" class="sync-msg">{{ syncMsg }}</p>

        <div class="tabs" role="tablist">
          <button role="tab" :aria-selected="tab==='users'" class="tab" :class="tab==='users' && 'tab--active'" @click="tab='users'">
            Users <span class="tab-count">{{ store.users.length }}</span>
          </button>
          <button role="tab" :aria-selected="tab==='companies'" class="tab" :class="tab==='companies' && 'tab--active'" @click="tab='companies'">
            Companies <span class="tab-count">{{ store.companies.length }}</span>
          </button>
          <button role="tab" :aria-selected="tab==='files'" class="tab" :class="tab==='files' && 'tab--active'" @click="openFiles">
            Files
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
                  <td><span class="role" :class="`role--${u.role}`">{{ u.role }}</span></td>
                  <td>{{ u.company_name || '—' }}</td>
                  <td class="ta-c">
                    <button class="switch" :class="u.access_enabled && 'switch--on'" :aria-pressed="u.access_enabled" :disabled="!canManage(u)" @click="toggleAccess(u)" :title="!canManage(u) ? 'Owner — only an owner can change this' : (u.access_enabled ? 'Enabled' : 'Disabled')"><span class="switch-knob" /></button>
                  </td>
                  <td class="ta-r">
                    <div class="row-actions">
                      <button v-if="!canManage(u)" class="owner-lock" title="Owner account — only an owner can manage it" aria-label="Owner-protected">
                        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.7"><path stroke-linecap="round" stroke-linejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" /></svg>
                      </button>
                      <template v-else>
                      <button class="icon-btn" @click="openUser(u)" aria-label="Edit user" title="Edit">
                        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.7"><path stroke-linecap="round" stroke-linejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125" /></svg>
                      </button>
                      <button class="icon-btn icon-btn--danger" @click="remove('user', u)" aria-label="Remove user" title="Remove">
                        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.7"><path stroke-linecap="round" stroke-linejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" /></svg>
                      </button>
                      </template>
                    </div>
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
                    <div class="row-actions">
                      <button class="icon-btn" @click="openCompany(c)" aria-label="Edit company" title="Edit">
                        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.7"><path stroke-linecap="round" stroke-linejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125" /></svg>
                      </button>
                      <button class="icon-btn icon-btn--danger" @click="remove('company', c)" aria-label="Remove company" title="Remove">
                        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.7"><path stroke-linecap="round" stroke-linejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" /></svg>
                      </button>
                    </div>
                  </td>
                </tr>
                <tr v-if="!store.companies.length"><td colspan="4" class="empty">No companies yet.</td></tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- FILES -->
        <section v-show="tab==='files'" class="panel">
          <div class="files-modes" role="tablist">
            <button role="tab" :aria-selected="filesMode==='inbox'" class="seg" :class="filesMode==='inbox' && 'seg--active'" @click="openInbox">
              Inbox <span v-if="inboxUnprocessed" class="seg-badge">{{ inboxUnprocessed }}</span>
            </button>
            <button role="tab" :aria-selected="filesMode==='company'" class="seg" :class="filesMode==='company' && 'seg--active'" @click="filesMode='company'">
              By company
            </button>
          </div>

          <!-- INBOX: recent uploads across all clients -->
          <div v-show="filesMode==='inbox'" class="inbox">
            <div class="inbox-bar">
              <span class="panel-hint">New uploads across all clients — mark items processed once integrated.</span>
              <div class="inbox-filters">
                <select v-model="inboxCompany" class="inbox-select" @change="loadInbox" aria-label="Filter by company">
                  <option :value="''">All clients</option>
                  <option v-for="c in fileCompanies" :key="c.id" :value="c.id">{{ c.name }}</option>
                </select>
                <div class="seg sm-seg">
                  <button :class="inboxStatus==='unprocessed' && 'on'" @click="inboxStatus='unprocessed'; loadInbox()">Unprocessed</button>
                  <button :class="inboxStatus==='all' && 'on'" @click="inboxStatus='all'; loadInbox()">All</button>
                </div>
              </div>
            </div>
            <div class="table-wrap">
              <table>
                <thead><tr><th>File</th><th>Client</th><th>Request</th><th>Uploaded</th><th>By</th><th></th></tr></thead>
                <tbody>
                  <tr v-for="i in inboxItems" :key="i.id" :class="i.processed && 'is-processed'">
                    <td>{{ i.original_name }} <span class="dim">· {{ fmtSize(i.size_bytes) }}</span></td>
                    <td><button class="link" @click="selectCompany(i.company.id); filesMode='company'">{{ i.company.name }}</button></td>
                    <td>{{ i.bucket.kind==='request' ? i.bucket.title : '—' }}</td>
                    <td>{{ fmtFileDate(i.uploaded_at) }}</td>
                    <td>{{ i.uploaded_by_name || '—' }}</td>
                    <td class="ta-r inbox-actions">
                      <a :href="`/api/admin/files/${i.id}/download`">Download</a>
                      <button class="link" @click="toggleProcessed(i)">{{ i.processed ? 'Undo' : 'Mark processed' }}</button>
                    </td>
                  </tr>
                  <tr v-if="!inboxItems.length"><td colspan="6" class="empty">{{ inboxStatus==='unprocessed' ? 'Nothing waiting — all caught up.' : 'No files yet.' }}</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- BY COMPANY: drill-down switcher -->
          <div v-show="filesMode==='company'" class="files-admin">
            <aside class="company-switcher">
              <input v-model="fileCompanyQuery" class="cs-search" type="search" placeholder="Search companies…" aria-label="Search companies" />
              <ul class="cs-list">
                <li v-for="c in filteredFileCompanies" :key="c.id">
                  <button class="cs-item" :class="c.id===selectedCompanyId && 'cs-item--active'" @click="selectCompany(c.id)">
                    <span class="cs-name">{{ c.name }}</span>
                    <span class="cs-counts">{{ c.file_count }} file{{ c.file_count===1?'':'s' }}<span v-if="c.open_request_count"> · {{ c.open_request_count }} open</span></span>
                  </button>
                </li>
                <li v-if="!fileCompanies.length" class="cs-empty">No companies.</li>
              </ul>
            </aside>

            <div class="files-detail">
              <template v-if="selectedCompany">
                <div class="fd-head">
                  <h3>{{ selectedCompany.name }}</h3>
                  <div class="fd-head-actions">
                    <button class="btn-ghost" @click="openRequest()">+ New request</button>
                    <a v-if="companyFileCount" class="btn-primary" :href="`/api/admin/files/companies/${selectedCompanyId}/download-all`">Download all</a>
                  </div>
                </div>
                <div v-for="b in companyBuckets" :key="b.id" class="fd-bucket">
                  <h4>
                    {{ b.title }}
                    <span v-if="b.kind==='request'" class="role role--admin">request</span>
                    <button v-if="b.kind==='request'" class="fd-edit" title="Edit request" @click="openRequest(b)" aria-label="Edit request">
                      <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.7"><path stroke-linecap="round" stroke-linejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125" /></svg>
                    </button>
                  </h4>
                  <p v-if="b.description" class="fd-desc">{{ b.description }}</p>
                  <table v-if="b.files.length">
                    <thead><tr><th>Name</th><th>Size</th><th>Uploaded</th><th>By</th><th></th></tr></thead>
                    <tbody>
                      <tr v-for="f in b.files" :key="f.id">
                        <td>{{ f.original_name }}</td>
                        <td class="tabular">{{ fmtSize(f.size_bytes) }}</td>
                        <td>{{ fmtFileDate(f.uploaded_at) }}</td>
                        <td>{{ f.uploaded_by_name || '—' }}</td>
                        <td class="ta-r"><a :href="`/api/admin/files/${f.id}/download`">Download</a></td>
                      </tr>
                    </tbody>
                  </table>
                  <p v-else class="empty">No files in this bucket.</p>
                </div>
              </template>
              <p v-else class="fd-placeholder">Select a company to view its files.</p>
            </div>
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
                <input v-model="form.email" type="email" placeholder="person@company.com" />
              </label>
              <label class="field"><span>Name</span>
                <input v-model="form.name" type="text" placeholder="Full name (optional)" />
              </label>
              <label class="field"><span>Role</span>
                <select v-model="form.role">
                  <option value="customer">Customer</option>
                  <option value="admin">Admin</option>
                  <option v-if="isOwner" value="owner">Owner</option>
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

            <template v-else-if="modal==='company'">
              <label class="field"><span>Company name</span>
                <input v-model="form.name" type="text" placeholder="e.g. Abiomed" />
              </label>
              <label class="field"><span>Contract end date</span>
                <input v-model="form.contract_end_date" type="date" />
              </label>
            </template>

            <template v-else-if="modal==='addpage'">
              <label class="field"><span>Confluence page URL</span>
                <input v-model="form.url" type="url" placeholder="https://citemed.atlassian.net/wiki/spaces/ECD/pages/…" />
              </label>
              <p class="addpage-hint">Paste a link to an Evidence Cloud (ECD) page. We'll fetch the page and its images and add it to the docs.</p>
            </template>

            <div class="modal-actions">
              <button class="btn-ghost" @click="modal=null">Cancel</button>
              <button class="btn-primary" :disabled="saving" @click="save">{{ saving ? (modal==='addpage' ? 'Adding…' : 'Saving…') : (modal==='addpage' ? 'Add page' : 'Save') }}</button>
            </div>
          </div>
        </div>
      </Transition>

      <!-- Request modal (file sharing) -->
      <Transition name="modal">
        <div v-if="reqModal" class="modal-overlay" @click.self="reqModal=false">
          <div class="modal" role="dialog" aria-modal="true">
            <h2 class="modal-title">{{ reqEditing ? 'Edit request' : 'New request' }}</h2>
            <p v-if="reqError" class="form-error">{{ reqError }}</p>
            <label class="field"><span>Title</span>
              <input v-model="reqForm.title" type="text" placeholder="e.g. Q3 PMS report submission" />
            </label>
            <label class="field"><span>Description for customer</span>
              <textarea v-model="reqForm.description" rows="3" placeholder="Tell the customer what to upload…"></textarea>
            </label>
            <div class="field-row">
              <label class="field"><span>Due date</span>
                <input v-model="reqForm.due_at" type="date" />
              </label>
              <label class="field"><span>Status</span>
                <select v-model="reqForm.status">
                  <option value="open">Open</option>
                  <option value="partial">Partial</option>
                  <option value="complete">Complete</option>
                </select>
              </label>
            </div>
            <div class="modal-actions">
              <button class="btn-ghost" @click="reqModal=false">Cancel</button>
              <button class="btn-primary" :disabled="reqSaving" @click="saveRequest">{{ reqSaving ? 'Saving…' : (reqEditing ? 'Save' : 'Create request') }}</button>
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
import { useAuthStore } from '@/stores/auth.js'

const store = useAdminStore()
const auth = useAuthStore()
const isOwner = computed(() => !!auth.user?.is_owner)
// A non-owner admin cannot modify owner accounts.
function canManage(u) {
  return isOwner.value || !u.is_owner
}
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
  if (modal.value === 'addpage') return 'Add a Confluence page'
  const noun = modal.value === 'user' ? 'user' : 'company'
  return `${editing.value ? 'Edit' : 'Add'} ${noun}`
})

function openAddPage() {
  editing.value = null
  formError.value = ''
  form.value = { url: '' }
  modal.value = 'addpage'
}

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
    if (modal.value === 'addpage') {
      syncMsg.value = await store.addPage(form.value.url)
      modal.value = null
      return
    }
    if (modal.value === 'user') {
      const payload = { email: form.value.email, name: form.value.name, role: form.value.role, company_id: form.value.company_id, access_enabled: form.value.access_enabled }
      if (editing.value) await store.updateUser(editing.value.id, payload)
      else await store.createUser(payload)
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

// ── Files tab (read-only company switcher) ──────────────────────────
const fileCompanies = ref([])
const fileCompanyQuery = ref('')
const selectedCompanyId = ref(null)
const companyBuckets = ref([])
const selectedCompany = ref(null)

const filteredFileCompanies = computed(() => {
  const q = fileCompanyQuery.value.toLowerCase().trim()
  return q ? fileCompanies.value.filter((c) => c.name.toLowerCase().includes(q)) : fileCompanies.value
})
const companyFileCount = computed(() => companyBuckets.value.reduce((n, b) => n + b.files.length, 0))

const filesMode = ref('inbox')
const inboxItems = ref([])
const inboxStatus = ref('unprocessed')
const inboxCompany = ref('')
const inboxUnprocessed = ref(0)

async function loadFileCompanies() {
  if (fileCompanies.value.length) return
  const r = await fetch('/api/admin/files/companies/', { credentials: 'include' })
  if (r.ok) fileCompanies.value = (await r.json()).companies
}
async function loadInbox() {
  const params = new URLSearchParams({ status: inboxStatus.value })
  if (inboxCompany.value) params.set('company', inboxCompany.value)
  const r = await fetch(`/api/admin/files/inbox/?${params}`, { credentials: 'include' })
  if (r.ok) {
    const data = await r.json()
    inboxItems.value = data.items
    inboxUnprocessed.value = data.unprocessed_total
  }
}
async function openFiles() {
  tab.value = 'files'
  loadFileCompanies()
  if (filesMode.value === 'inbox') loadInbox()
}
function openInbox() {
  filesMode.value = 'inbox'
  loadInbox()
}
async function toggleProcessed(item) {
  const next = !item.processed
  const r = await fetch(`/api/admin/files/${item.id}/processed`, {
    method: 'PATCH', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ processed: next }),
  })
  if (r.ok) await loadInbox()
}
async function selectCompany(id) {
  selectedCompanyId.value = id
  const r = await fetch(`/api/admin/files/companies/${id}/`, { credentials: 'include' })
  if (r.ok) {
    const data = await r.json()
    selectedCompany.value = data.company
    companyBuckets.value = data.buckets
  }
}
function fmtSize(b) {
  if (!b) return '—'
  const u = ['B', 'KB', 'MB', 'GB']
  let i = 0
  while (b >= 1024 && i < 3) { b /= 1024; i++ }
  return `${b.toFixed(i ? 1 : 0)} ${u[i]}`
}
function fmtFileDate(d) {
  return new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

// Request authoring
const reqModal = ref(false)
const reqEditing = ref(null)
const reqSaving = ref(false)
const reqError = ref('')
const reqForm = ref({ title: '', description: '', due_at: '', status: 'open' })

function openRequest(b = null) {
  reqEditing.value = b
  reqError.value = ''
  reqForm.value = b
    ? { title: b.title, description: b.description || '', due_at: b.due_at ? b.due_at.slice(0, 10) : '', status: b.status === 'general' ? 'open' : b.status }
    : { title: '', description: '', due_at: '', status: 'open' }
  reqModal.value = true
}
async function saveRequest() {
  reqSaving.value = true
  reqError.value = ''
  try {
    const payload = { ...reqForm.value, due_at: reqForm.value.due_at || null, company_id: selectedCompanyId.value }
    const url = reqEditing.value
      ? `/api/admin/files/requests/${reqEditing.value.id}/`
      : '/api/admin/files/requests/'
    const r = await fetch(url, {
      method: reqEditing.value ? 'PATCH' : 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || 'Could not save request')
    reqModal.value = false
    await selectCompany(selectedCompanyId.value)
  } catch (e) {
    reqError.value = e.message
  } finally {
    reqSaving.value = false
  }
}

onMounted(() => store.fetchAll())
</script>

<style scoped>
/* Full-width admin module — aligns with the top-bar padding (px-4 / lg:px-6) */
.admin { max-width: none; margin: 0; padding: 26px clamp(1rem, 2vw, 1.5rem) 64px; }
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
.head-actions { display: flex; gap: 8px; flex-shrink: 0; }
.addpage-hint { font-size: 12px; color: var(--muted-foreground); line-height: 1.45; margin: 2px 0 0; }

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
.role--owner { color: #fff; background: var(--primary); }
.dark .role--owner { color: var(--background); background: var(--brand-accent); }
.role--admin { color: var(--primary); background: var(--accent); }
.dark .role--admin { color: var(--accent-foreground); }
.role--customer { color: var(--muted-foreground); background: var(--muted); }

/* Owner-protected row: no actions for non-owners */
.owner-lock {
  display: inline-flex; align-items: center; justify-content: center;
  width: 32px; height: 32px; border-radius: 7px;
  color: var(--muted-foreground); cursor: default;
}
.switch:disabled { opacity: 0.5; cursor: not-allowed; }
.icon-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.switch { width: 36px; height: 20px; border-radius: 999px; background: var(--input); position: relative; transition: background 0.18s; }
.switch--on { background: var(--primary); }
.switch-knob { position: absolute; top: 2px; left: 2px; width: 16px; height: 16px; border-radius: 50%; background: #fff; transition: transform 0.18s; box-shadow: 0 1px 2px oklch(0 0 0 / 0.2); }
.switch--on .switch-knob { transform: translateX(16px); }

.row-actions { display: inline-flex; gap: 6px; }
.icon-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 32px; height: 32px; border-radius: 7px;
  color: var(--foreground);
  border: 1px solid var(--border);
  background: var(--card);
  transition: color 0.15s, background 0.15s, border-color 0.15s;
}
.icon-btn:hover { color: var(--primary); border-color: var(--primary); background: var(--accent); }
.dark .icon-btn:hover { color: var(--accent-foreground); }
.icon-btn--danger:hover { color: var(--destructive); border-color: var(--destructive); background: color-mix(in srgb, var(--destructive) 12%, transparent); }

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

/* Files tab */
.files-admin { display: grid; grid-template-columns: 280px 1fr; gap: 20px; align-items: start; }
@media (max-width: 720px) { .files-admin { grid-template-columns: 1fr; } }
.company-switcher { border: 1px solid var(--border); border-radius: 12px; padding: 10px; background: var(--card); }
.cs-search { width: 100%; height: 36px; padding: 0 11px; border-radius: 8px; border: 1px solid var(--input); background: var(--background); color: var(--foreground); font-size: 13.5px; margin-bottom: 8px; }
.cs-search:focus { outline: 2px solid var(--ring); outline-offset: -1px; }
.cs-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; max-height: 60vh; overflow-y: auto; }
.cs-item { width: 100%; text-align: left; display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; border-radius: 8px; cursor: pointer; background: none; border: none; }
.cs-item:hover { background: var(--muted); }
.cs-item--active { background: color-mix(in srgb, var(--primary) 12%, transparent); }
.cs-name { font-size: 14px; font-weight: 550; color: var(--foreground); }
.cs-counts { font-size: 12px; color: var(--muted-foreground); }
.cs-empty { padding: 10px; font-size: 13px; color: var(--muted-foreground); }
.files-detail { min-width: 0; }
.fd-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.fd-head h3 { font-family: var(--font-ui); font-size: 1.2rem; font-weight: 600; color: var(--foreground); margin: 0; }
.fd-bucket { margin-bottom: 22px; }
.fd-bucket h4 { font-size: 0.95rem; font-weight: 600; color: var(--foreground); margin: 0 0 8px; display: flex; align-items: center; gap: 8px; }
.fd-desc { font-size: 0.85rem; color: var(--muted-foreground); margin: -2px 0 10px; max-width: 70ch; }
.fd-placeholder { color: var(--muted-foreground); font-size: 0.95rem; padding: 24px 0; }
.fd-head-actions { display: flex; align-items: center; gap: 8px; }
.fd-edit { background: none; border: none; color: var(--muted-foreground); cursor: pointer; padding: 2px; border-radius: 6px; display: inline-grid; place-items: center; }
.fd-edit:hover { background: var(--muted); color: var(--foreground); }
/* Files: segmented modes + inbox */
.files-modes { display: flex; gap: 6px; margin-bottom: 16px; }
.seg { display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; border: 1px solid var(--border); border-radius: 8px; background: var(--card); color: var(--muted-foreground); font: inherit; font-size: 13.5px; font-weight: 550; cursor: pointer; }
.seg:hover { color: var(--foreground); }
.seg--active { border-color: var(--primary); background: color-mix(in srgb, var(--primary) 8%, var(--card)); color: var(--primary); }
.seg-badge { font-size: 11px; font-weight: 700; background: var(--primary); color: var(--primary-foreground); border-radius: 999px; padding: 1px 7px; }
.inbox-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.inbox-filters { display: flex; align-items: center; gap: 10px; }
.inbox-select { height: 34px; padding: 0 10px; border-radius: 8px; border: 1px solid var(--input); background: var(--background); color: var(--foreground); font: inherit; font-size: 13px; }
.sm-seg { display: inline-flex; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
.sm-seg button { border: none; background: var(--card); color: var(--muted-foreground); font: inherit; font-size: 12.5px; font-weight: 550; padding: 6px 12px; cursor: pointer; }
.sm-seg button.on { background: color-mix(in srgb, var(--primary) 10%, var(--card)); color: var(--primary); }
.link { background: none; border: none; color: var(--brand-accent); cursor: pointer; font: inherit; padding: 0; }
.link:hover { text-decoration: underline; }
.dim { color: var(--muted-foreground); font-size: 12px; }
.inbox-actions { display: flex; gap: 14px; justify-content: flex-end; }
.is-processed td { color: var(--muted-foreground); }
.field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.field textarea { width: 100%; padding: 8px 11px; border-radius: 8px; border: 1px solid var(--input); background: var(--background); color: var(--foreground); font: inherit; font-size: 14px; resize: vertical; }
.field textarea:focus { outline: 2px solid var(--ring); outline-offset: -1px; border-color: var(--ring); }
</style>
