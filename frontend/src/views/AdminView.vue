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
            <div class="split" :class="{ 'has-preview': preview }">
              <div class="table-wrap">
                <table>
                  <thead>
                    <tr v-if="preview"><th>File</th><th>Client</th><th></th></tr>
                    <tr v-else><th>File</th><th>Client</th><th>Request</th><th>Uploaded</th><th>By</th><th></th></tr>
                  </thead>
                  <tbody>
                    <tr v-for="i in inboxItems" :key="i.id" :class="[i.processed && 'is-processed', preview && preview.id===i.id && 'row-active']">
                      <td>{{ i.original_name }} <span class="dim">· {{ fmtSize(i.size_bytes) }}</span></td>
                      <td><button class="link" @click="selectCompany(i.company.id); filesMode='company'">{{ i.company.name }}</button></td>
                      <template v-if="!preview">
                        <td>{{ i.bucket.kind==='request' ? i.bucket.title : '—' }}</td>
                        <td>{{ fmtFileDate(i.uploaded_at) }}</td>
                        <td>{{ i.uploaded_by_name || '—' }}</td>
                      </template>
                      <td class="ta-r inbox-actions">
                        <button v-if="previewable(i.original_name)" class="link" @click="openPreview(i.id, i.original_name)">{{ preview && preview.id===i.id ? 'Close' : 'Preview' }}</button>
                        <a :href="`/api/admin/files/${i.id}/download`">Download</a>
                        <button v-if="!preview" class="link" @click="toggleProcessed(i)">{{ i.processed ? 'Undo' : 'Mark processed' }}</button>
                      </td>
                    </tr>
                    <tr v-if="!inboxItems.length"><td :colspan="preview ? 3 : 6" class="empty">{{ inboxStatus==='unprocessed' ? 'Nothing waiting — all caught up.' : 'No files yet.' }}</td></tr>
                  </tbody>
                </table>
              </div>
              <Transition name="pane"><FilePreviewPane v-if="preview" :src="preview.src" :name="preview.name" @close="closePreview" /></Transition>
            </div>
          </div>

          <!-- BY COMPANY: drill-down switcher -->
          <div v-show="filesMode==='company'" class="files-admin" :class="{ 'has-preview': preview }">
            <aside class="company-switcher" v-show="!preview">
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

            <div class="files-detail" :class="{ compact: preview }">
              <template v-if="selectedCompany">
                <div class="fd-head">
                  <h3>{{ selectedCompany.name }}</h3>
                  <div class="fd-head-actions">
                    <button class="btn-ghost" @click="openRequest()">+ New request</button>
                    <a v-if="companyFileCount" class="btn-primary" :href="`/api/admin/files/companies/${selectedCompanyId}/download-all`">Download all</a>
                  </div>
                </div>
                <div v-for="b in companyBuckets" :key="b.id" class="fd-bucket">
                  <div class="fd-bucket-head">
                    <div class="fd-bucket-title">
                      <h4>{{ b.title }}</h4>
                      <span v-if="b.kind==='request'" class="kind-tag">Request</span>
                      <span v-if="b.due_at" class="due" :class="`due--${dueTone(b)}`">{{ dueLabel(b) }}</span>
                    </div>
                    <button v-if="b.kind==='request'" class="fd-edit" title="Edit request" @click="openRequest(b)" aria-label="Edit request">
                      <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.7"><path stroke-linecap="round" stroke-linejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125" /></svg>
                    </button>
                  </div>
                  <p v-if="b.description" class="fd-desc">{{ b.description }}</p>

                  <!-- Required-documents checklist (requests only) -->
                  <div v-if="b.kind==='request'" class="checklist">
                    <div class="checklist-head">
                      <span class="checklist-label">Required documents</span>
                      <span class="checklist-progress">{{ b.checklist.filter(c=>c.linked_file).length }} / {{ b.checklist.length }} received</span>
                    </div>
                    <div class="progress-bar"><div :style="{ width: checklistPct(b) + '%' }" /></div>
                    <div v-for="c in b.checklist" :key="c.id" class="check-row">
                      <span class="check-dot" :class="c.linked_file && 'check-dot--on'" />
                      <span class="check-text">{{ c.text }}</span>
                      <select class="check-link" :value="c.linked_file || ''" @change="linkChecklist(c, $event.target.value)">
                        <option value="">— link a file —</option>
                        <option v-for="f in b.files" :key="f.id" :value="f.id">{{ f.original_name }}</option>
                      </select>
                      <button class="ico-sm" title="Remove" @click="removeChecklist(c)" aria-label="Remove checklist item">×</button>
                    </div>
                    <div class="check-add">
                      <input v-model="checklistDraft[b.id]" placeholder="Add a required document…" @keydown.enter="addChecklist(b)" />
                      <button class="btn-ghost" @click="addChecklist(b)">Add</button>
                    </div>
                  </div>

                  <ul v-if="b.files.length" class="fd-rows">
                    <li v-for="f in b.files" :key="f.id" class="fd-row" :class="preview && preview.id===f.id && 'row-active'">
                      <span class="fd-file">
                        <span class="fd-name">{{ f.original_name }}</span>
                        <span class="fd-sub">{{ fmtSize(f.size_bytes) }} · {{ fmtFileDate(f.uploaded_at) }} · {{ f.uploaded_by_name || '—' }}</span>
                        <span v-if="f.review_notes" class="fd-note">Note: {{ f.review_notes }}</span>
                      </span>
                      <select class="review-select" :class="`rv--${f.review_status}`" :value="f.review_status" @change="setReview(f, $event.target.value)">
                        <option value="pending">Pending</option>
                        <option value="review">In review</option>
                        <option value="approved">Approved</option>
                        <option value="revision">Needs revision</option>
                      </select>
                      <button class="ico-sm" title="Add / edit note" @click="editNote(f)" aria-label="Edit note">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 1 1 3 3L7 19l-4 1 1-4Z"/></svg>
                      </button>
                      <span class="fd-actions">
                        <button v-if="previewable(f.original_name)" class="link" @click="openPreview(f.id, f.original_name)">{{ preview && preview.id===f.id ? 'Close' : 'Preview' }}</button>
                        <a :href="`/api/admin/files/${f.id}/download`">Download</a>
                      </span>
                    </li>
                  </ul>
                  <p v-else class="empty">No files in this bucket.</p>
                </div>
              </template>
              <p v-else class="fd-placeholder">Select a company to view its files.</p>
            </div>
            <Transition name="pane"><FilePreviewPane v-if="preview" :src="preview.src" :name="preview.name" @close="closePreview" /></Transition>
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
import FilePreviewPane from '@/components/files/FilePreviewPane.vue'
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
  preview.value = null
  filesMode.value = 'inbox'
  loadInbox()
}
const preview = ref(null)  // { id, src, name }
function previewable(name) { return /\.(pdf|png|jpe?g|gif|webp)$/i.test(name) }
function openPreview(id, name) {
  if (preview.value?.id === id) { preview.value = null; return }  // toggle
  preview.value = { id, src: `/api/admin/files/${id}/view`, name }
}
function closePreview() { preview.value = null }

// Review + checklist
const checklistDraft = ref({})
async function setReview(f, status) {
  const r = await fetch(`/api/admin/files/${f.id}/review`, {
    method: 'PATCH', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ review_status: status }),
  })
  if (r.ok) await selectCompany(selectedCompanyId.value)
}
async function editNote(f) {
  const notes = prompt('Reviewer note (shown to the customer when status is In review / Needs revision):', f.review_notes || '')
  if (notes === null) return
  const r = await fetch(`/api/admin/files/${f.id}/review`, {
    method: 'PATCH', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ notes }),
  })
  if (r.ok) await selectCompany(selectedCompanyId.value)
}
async function addChecklist(b) {
  const text = (checklistDraft.value[b.id] || '').trim()
  if (!text) return
  const r = await fetch('/api/admin/files/checklist/', {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bucket_id: b.id, text }),
  })
  if (r.ok) { checklistDraft.value[b.id] = ''; await selectCompany(selectedCompanyId.value) }
}
async function linkChecklist(item, fileId) {
  const r = await fetch(`/api/admin/files/checklist/${item.id}/`, {
    method: 'PATCH', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ linked_file_id: fileId ? Number(fileId) : null }),
  })
  if (r.ok) await selectCompany(selectedCompanyId.value)
}
async function removeChecklist(item) {
  const r = await fetch(`/api/admin/files/checklist/${item.id}/`, { method: 'DELETE', credentials: 'include' })
  if (r.ok) await selectCompany(selectedCompanyId.value)
}
function checklistPct(b) {
  if (!b.checklist.length) return 0
  return Math.round(b.checklist.filter((c) => c.linked_file).length / b.checklist.length * 100)
}
function dueTone(b) {
  const days = Math.ceil((new Date(b.due_at) - Date.now()) / 86400000)
  return days < 0 ? 'over' : days <= 3 ? 'soon' : 'ok'
}
function dueLabel(b) {
  const days = Math.ceil((new Date(b.due_at) - Date.now()) / 86400000)
  if (days < 0) return 'Overdue'
  if (days === 0) return 'Due today'
  return `Due ${days}d`
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
  preview.value = null
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
.files-admin { display: flex; gap: 20px; align-items: flex-start; }
.files-admin .company-switcher { flex: 0 0 280px; }
.files-admin .files-detail { flex: 1 1 auto; min-width: 0; }
@media (max-width: 720px) { .files-admin { grid-template-columns: 1fr; } }
.company-switcher { border: 1px solid var(--border); border-radius: 12px; padding: 10px; background: var(--card); }
.cs-search { width: 100%; height: 36px; padding: 0 11px; border-radius: 8px; border: 1px solid var(--input); background: var(--background); color: var(--foreground); font-size: 13.5px; margin-bottom: 8px; }
.cs-search:focus { outline: 2px solid var(--ring); outline-offset: -1px; }
.cs-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; max-height: 60vh; overflow-y: auto; }
.cs-item { width: 100%; text-align: left; display: flex; flex-direction: column; gap: 2px; padding: 9px 11px; border-radius: 8px; cursor: pointer; background: none; border: 1px solid transparent; transition: background-color 0.12s ease, border-color 0.12s ease; }
.cs-item:hover { background: var(--secondary); }
.cs-item--active { background: color-mix(in srgb, var(--primary) 14%, var(--card)); border-color: color-mix(in srgb, var(--primary) 45%, transparent); }
.cs-item--active:hover { background: color-mix(in srgb, var(--primary) 18%, var(--card)); }
.cs-name { font-size: 14px; font-weight: 600; color: var(--foreground); }
.cs-item--active .cs-name { color: var(--primary); }
.cs-counts { font-size: 12px; color: var(--muted-foreground); }
.cs-empty { padding: 10px; font-size: 13px; color: var(--muted-foreground); }
.files-detail { min-width: 0; }
.fd-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.fd-head h3 { font-family: var(--font-ui); font-size: 1.2rem; font-weight: 600; color: var(--foreground); margin: 0; }
.fd-bucket { margin-bottom: 22px; }
.fd-bucket h4 { font-size: 0.95rem; font-weight: 600; color: var(--foreground); margin: 0; }
.fd-bucket-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
.fd-bucket-title { display: flex; align-items: center; gap: 10px; min-width: 0; }
.kind-tag { font-size: 0.62rem; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; color: var(--muted-foreground); border: 1px solid var(--border); border-radius: 999px; padding: 1px 8px; }
.fd-desc { font-size: 0.85rem; color: var(--muted-foreground); margin: -2px 0 10px; max-width: 70ch; }
.fd-placeholder { color: var(--muted-foreground); font-size: 0.95rem; padding: 24px 0; }
.due { font-size: 0.72rem; font-weight: 550; color: var(--muted-foreground); }
.due--soon { font-weight: 650; }
.due--over { color: var(--destructive); font-weight: 650; }

/* Checklist */
.checklist { border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; margin: 0 0 14px; background: var(--card); }
.checklist-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.checklist-label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; color: var(--muted-foreground); }
.checklist-progress { font-size: 0.78rem; color: var(--muted-foreground); }
.progress-bar { height: 5px; border-radius: 999px; background: var(--secondary); overflow: hidden; margin-bottom: 10px; }
.progress-bar div { height: 100%; background: var(--primary); transition: width 0.3s ease; }
.check-row { display: grid; grid-template-columns: 14px 1fr 200px 24px; align-items: center; gap: 8px; padding: 4px 0; }
.check-dot { width: 9px; height: 9px; border-radius: 50%; border: 1.5px solid var(--input); }
.check-dot--on { background: var(--primary); border-color: var(--primary); }
.check-text { font-size: 0.85rem; color: var(--foreground); }
.check-link { height: 30px; border: 1px solid var(--input); border-radius: 7px; background: var(--background); color: var(--foreground); font: inherit; font-size: 12.5px; padding: 0 8px; max-width: 200px; }
.check-add { display: flex; gap: 8px; margin-top: 8px; }
.check-add input { flex: 1; height: 32px; border: 1px solid var(--input); border-radius: 7px; background: var(--background); color: var(--foreground); font: inherit; font-size: 13px; padding: 0 10px; }
.ico-sm { width: 24px; height: 24px; display: inline-grid; place-items: center; border: none; background: none; color: var(--muted-foreground); border-radius: 6px; cursor: pointer; font-size: 16px; }
.ico-sm svg { width: 13px; height: 13px; }
.ico-sm:hover { background: var(--secondary); color: var(--foreground); }

/* File rows (company view) */
.fd-rows { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
.fd-row { display: grid; grid-template-columns: 1fr 140px 28px auto; align-items: center; gap: 12px; padding: 8px 10px; border: 1px solid var(--border); border-radius: 9px; }
.fd-file { min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.fd-name { font-size: 0.88rem; font-weight: 550; color: var(--foreground); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fd-sub { font-size: 0.74rem; color: var(--muted-foreground); }
.fd-note { font-size: 0.74rem; color: var(--destructive); margin-top: 2px; }
.review-select { height: 30px; border: 1px solid var(--input); border-radius: 7px; background: var(--background); color: var(--foreground); font: inherit; font-size: 12.5px; padding: 0 6px; }
.rv--approved { color: var(--primary); }
.rv--revision { color: var(--destructive); }
.fd-actions { display: flex; gap: 12px; justify-content: flex-end; white-space: nowrap; }
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
.row-active > td { background: color-mix(in srgb, var(--primary) 8%, var(--card)); }

/* Split preview (inbox + company) — flex so the table shrinks smoothly */
.split { display: flex; gap: 16px; align-items: flex-start; }
.split > .table-wrap { flex: 1 1 auto; min-width: 0; }
.split :deep(.pvp), .files-admin :deep(.pvp) { flex: 0 0 clamp(360px, 46%, 640px); }
.review-select, .cs-item, .seg, .b-card { transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease; }

/* Pane reveal: width + fade together, eased out */
.pane-enter-active, .pane-leave-active { transition: max-width 0.34s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.3s ease, transform 0.34s cubic-bezier(0.4, 0, 0.2, 1); overflow: hidden; }
.pane-enter-from, .pane-leave-to { max-width: 0; opacity: 0; transform: translateX(18px); }
.pane-enter-to, .pane-leave-from { max-width: 680px; }
@media (prefers-reduced-motion: reduce) {
  .pane-enter-active, .pane-leave-active { transition: none; }
  .pane-enter-from, .pane-leave-to { max-width: 680px; transform: none; }
}
.files-detail.compact .review-select,
.files-detail.compact .fd-row .ico-sm,
.files-detail.compact .fd-sub,
.files-detail.compact .fd-note,
.files-detail.compact .checklist { display: none; }
.files-detail.compact .fd-row { grid-template-columns: 1fr auto; }
.fd-row.row-active { box-shadow: inset 3px 0 0 var(--primary); border-color: color-mix(in srgb, var(--primary) 40%, var(--border)); }
@media (max-width: 900px) {
  .split.has-preview, .files-admin.has-preview { grid-template-columns: 1fr; }
}
.field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.field textarea { width: 100%; padding: 8px 11px; border-radius: 8px; border: 1px solid var(--input); background: var(--background); color: var(--foreground); font: inherit; font-size: 14px; resize: vertical; }
.field textarea:focus { outline: 2px solid var(--ring); outline-offset: -1px; border-color: var(--ring); }
</style>
