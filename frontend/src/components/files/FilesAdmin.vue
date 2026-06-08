<template>
  <div class="files-admin-root">
    <div class="files-modes" role="tablist">
      <button role="tab" :aria-selected="filesMode==='inbox'" class="seg" :class="filesMode==='inbox' && 'seg--active'" @click="openInbox">
        Inbox <span v-if="inboxUnprocessed" class="seg-badge">{{ inboxUnprocessed }}</span>
      </button>
      <button role="tab" :aria-selected="filesMode==='company'" class="seg" :class="filesMode==='company' && 'seg--active'" @click="filesMode='company'">
        By company
      </button>
      <button role="tab" :aria-selected="filesMode==='activity'" class="seg" :class="filesMode==='activity' && 'seg--active'" @click="openActivity">
        Activity
      </button>
      <button class="refresh-btn" :class="refreshing && 'is-spinning'" :disabled="refreshing" title="Refresh" aria-label="Refresh" @click="refresh">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v5h-5"/></svg>
        {{ refreshing ? 'Refreshing…' : 'Refresh' }}
      </button>
    </div>

    <!-- ACTIVITY: append-only audit trail -->
    <div v-show="filesMode==='activity'" class="activity">
      <span class="panel-hint">Every upload, download, review, and status change — newest first.</span>
      <div class="table-wrap" style="margin-top:12px">
        <table>
          <thead><tr><th>When</th><th>Who</th><th>Action</th><th>File</th><th>Client</th></tr></thead>
          <tbody>
            <tr v-for="a in activityItems" :key="a.id">
              <td class="dim">{{ fmtWhen(a.created_at) }}</td>
              <td>{{ a.actor }}</td>
              <td><span class="act-tag" :class="`act-tag--${a.action}`">{{ actionLabel(a.action) }}</span></td>
              <td>{{ a.file || '—' }}</td>
              <td>{{ a.company || '—' }}</td>
            </tr>
            <tr v-if="!activityItems.length"><td colspan="5" class="empty">No activity yet.</td></tr>
          </tbody>
        </table>
      </div>
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
            <tbody v-if="inboxLoading">
              <tr v-for="n in 4" :key="'sk'+n" class="sk-row"><td :colspan="preview ? 3 : 6"><span class="sk-bar" /></td></tr>
            </tbody>
            <tbody v-else>
              <tr v-for="i in inboxItems" :key="i.id" :class="[i.processed && 'is-processed', preview && preview.id===i.id && 'row-active']">
                <td>{{ i.original_name }} <span class="dim">· {{ fmtSize(i.size_bytes) }}</span></td>
                <td><button class="link" @click="selectCompany(i.company.id); filesMode='company'">{{ i.company.name }}</button></td>
                <template v-if="!preview">
                  <td>{{ i.bucket.kind==='request' ? i.bucket.title : '—' }}</td>
                  <td>{{ fmtFileDate(i.uploaded_at) }}</td>
                  <td>{{ i.uploaded_by_name || '—' }}</td>
                </template>
                <td class="ta-r">
                  <span class="row-acts">
                    <button v-if="previewable(i.original_name)" class="act" :class="preview && preview.id===i.id && 'act--on'" :title="preview && preview.id===i.id ? 'Close preview' : 'Preview'" aria-label="Preview" @click="openPreview(i.id, i.original_name)">
                      <svg v-if="preview && preview.id===i.id" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 18 18 6M6 6l12 12"/></svg>
                      <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8Z"/><circle cx="12" cy="12" r="3"/></svg>
                    </button>
                    <a class="act" :href="`/api/admin/files/${i.id}/download`" title="Download" aria-label="Download">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                    </a>
                    <button v-if="!preview" class="done-btn" :class="i.processed && 'is-on'" @click="toggleProcessed(i)" :aria-pressed="i.processed" :aria-label="i.processed ? `Mark ${i.original_name} not processed` : `Mark ${i.original_name} processed`" :title="i.processed ? 'Processed — click to undo' : 'Mark as processed'">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                      {{ i.processed ? 'Done' : 'Mark done' }}
                    </button>
                  </span>
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
              <button class="refresh-btn" :class="refreshing && 'is-spinning'" :disabled="refreshing" title="Refresh this company" aria-label="Refresh" @click="refresh">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v5h-5"/></svg>
                {{ refreshing ? 'Refreshing…' : 'Refresh' }}
              </button>
              <a v-if="companyFileCount" class="btn-outline" :href="`/api/admin/files/companies/${selectedCompanyId}/download-all`">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                Download all
              </a>
              <button class="btn-primary" @click="openRequest()">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>
                New request
              </button>
            </div>
          </div>
          <div v-for="b in orderedBuckets" :key="b.id" class="fd-bucket">
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

            <!-- Required-documents checklist (requests only, optional) -->
            <template v-if="b.kind==='request'">
              <div v-if="b.checklist.length || showAdd[b.id]" class="checklist">
                <template v-if="b.checklist.length">
                  <div class="checklist-head">
                    <span class="checklist-label">Required documents</span>
                    <span class="checklist-progress">{{ b.checklist.filter(c=>c.linked_file).length }} / {{ b.checklist.length }} received</span>
                  </div>
                  <div class="progress-bar"><div :style="{ width: checklistPct(b) + '%' }" /></div>
                  <div v-for="c in b.checklist" :key="c.id" class="check-row">
                    <span class="check-dot" :class="c.linked_file && 'check-dot--on'" />
                    <span class="check-text">{{ c.text }}</span>
                    <select class="check-link" :value="c.linked_file || ''" :aria-label="`Link a file to: ${c.text}`" @change="linkChecklist(c, $event.target.value)">
                      <option value="">— link a file —</option>
                      <option v-for="f in b.files" :key="f.id" :value="f.id">{{ f.original_name }}</option>
                    </select>
                    <button class="ico-sm" title="Remove" @click="removeChecklist(c)" aria-label="Remove checklist item">×</button>
                  </div>
                </template>
                <div class="check-add">
                  <input v-model="checklistDraft[b.id]" placeholder="Add a required document…" @keydown.enter="addChecklist(b)" />
                  <button class="btn-ghost" @click="addChecklist(b)">Add</button>
                </div>
              </div>
              <button v-else class="checklist-add-link" @click="showAdd[b.id]=true">+ Add a required-documents checklist (optional)</button>
            </template>

            <ul v-if="b.files.length" class="fd-rows">
              <li v-for="f in b.files" :key="f.id" class="fd-row" :class="preview && preview.id===f.id && 'row-active'">
                <span class="fd-file">
                  <span class="fd-name">{{ f.original_name }}</span>
                  <span class="fd-sub">{{ fmtSize(f.size_bytes) }} · {{ fmtFileDate(f.uploaded_at) }} · {{ f.uploaded_by_name || '—' }}</span>
                  <span v-if="f.review_notes" class="fd-note">Note: {{ f.review_notes }}</span>
                </span>
                <select class="review-select" :class="`rv--${f.review_status}`" :value="f.review_status" :aria-label="`Review status for ${f.original_name}`" @change="setReview(f, $event.target.value)">
                  <option value="pending">Pending</option>
                  <option value="review">In review</option>
                  <option value="approved">Approved</option>
                  <option value="revision">Needs revision</option>
                </select>
                <button class="ico-sm" title="Add / edit note" @click="editNote(f)" aria-label="Edit note">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 1 1 3 3L7 19l-4 1 1-4Z"/></svg>
                </button>
                <span class="row-acts">
                  <button v-if="previewable(f.original_name)" class="act" :class="preview && preview.id===f.id && 'act--on'" :title="preview && preview.id===f.id ? 'Close preview' : 'Preview'" aria-label="Preview" @click="openPreview(f.id, f.original_name)">
                    <svg v-if="preview && preview.id===f.id" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 18 18 6M6 6l12 12"/></svg>
                    <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8Z"/><circle cx="12" cy="12" r="3"/></svg>
                  </button>
                  <a class="act" :href="`/api/admin/files/${f.id}/download`" title="Download" aria-label="Download">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                  </a>
                </span>
              </li>
            </ul>
            <p v-else class="bucket-empty">No files uploaded yet.</p>
          </div>
        </template>
        <p v-else class="fd-placeholder">Select a company to view its files.</p>
      </div>
      <Transition name="pane"><FilePreviewPane v-if="preview" :src="preview.src" :name="preview.name" @close="closePreview" /></Transition>
    </div>

    <!-- Request modal -->
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
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import FilePreviewPane from '@/components/files/FilePreviewPane.vue'

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
// Active requests first, the freeform "General uploads" bucket last.
const orderedBuckets = computed(() => {
  const reqs = companyBuckets.value.filter((b) => b.kind === 'request')
  const gen = companyBuckets.value.filter((b) => b.kind !== 'request')
  return [...reqs, ...gen]
})

const filesMode = ref('inbox')
const inboxItems = ref([])
const inboxStatus = ref('unprocessed')
const inboxCompany = ref('')
const inboxUnprocessed = ref(0)
const inboxLoading = ref(false)

async function loadFileCompanies(force = false) {
  if (!force && fileCompanies.value.length) return
  const r = await fetch('/api/admin/files/companies/', { credentials: 'include' })
  if (r.ok) fileCompanies.value = (await r.json()).companies
}

const refreshing = ref(false)
async function refresh() {
  refreshing.value = true
  try {
    if (filesMode.value === 'inbox') {
      await loadInbox()
    } else if (filesMode.value === 'company') {
      await loadFileCompanies(true)
      if (selectedCompanyId.value) await selectCompany(selectedCompanyId.value)
    } else if (filesMode.value === 'activity') {
      await loadActivity()
    }
  } finally {
    refreshing.value = false
  }
}
async function loadInbox() {
  inboxLoading.value = true
  try {
    const params = new URLSearchParams({ status: inboxStatus.value })
    if (inboxCompany.value) params.set('company', inboxCompany.value)
    const r = await fetch(`/api/admin/files/inbox/?${params}`, { credentials: 'include' })
    if (r.ok) {
      const data = await r.json()
      inboxItems.value = data.items
      inboxUnprocessed.value = data.unprocessed_total
    }
  } finally {
    inboxLoading.value = false
  }
}
function openInbox() {
  preview.value = null
  filesMode.value = 'inbox'
  loadInbox()
}

// Activity (audit trail)
const activityItems = ref([])
async function loadActivity() {
  const r = await fetch('/api/admin/files/activity/?limit=200', { credentials: 'include' })
  if (r.ok) activityItems.value = (await r.json()).items
}
function openActivity() {
  preview.value = null
  filesMode.value = 'activity'
  loadActivity()
}
const ACTION_LABELS = {
  upload: 'Uploaded', download: 'Downloaded', rename: 'Renamed', delete: 'Deleted',
  status_change: 'Review changed', note: 'Note', request_created: 'Request created',
  request_deleted: 'Request deleted', processed: 'Marked processed', unprocessed: 'Unmarked',
}
function actionLabel(a) { return ACTION_LABELS[a] || a }
function fmtWhen(d) {
  return new Date(d).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
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
const showAdd = ref({})  // per-bucket: reveal the (optional) checklist editor
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

onMounted(() => {
  loadFileCompanies()
  loadInbox()
})
</script>

<style scoped>
/* ── Shared primitives (this component is self-contained) ── */
.panel-hint { font-size: 12.5px; color: var(--muted-foreground); }
.table-wrap { border: 1px solid var(--border); border-radius: 12px; overflow: hidden; background: var(--card); }
table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13.5px; }
th { text-align: left; font-family: var(--font-ui); font-size: 11px; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; color: var(--muted-foreground); padding: 11px 14px; background: var(--muted); border-bottom: 1px solid var(--border); }
td { padding: 11px 14px; border-bottom: 1px solid var(--border-subtle); color: var(--foreground); vertical-align: middle; }
tbody tr:last-child td { border-bottom: none; }
tbody tr:hover td { background: var(--accent); }
.ta-r { text-align: right; white-space: nowrap; }
.empty { text-align: center; color: var(--muted-foreground); padding: 28px; }
.btn-primary { display: inline-flex; align-items: center; gap: 6px; background: var(--primary); color: var(--primary-foreground); font-family: var(--font-ui); font-size: 13.5px; font-weight: 600; padding: 8px 14px; border-radius: 8px; cursor: pointer; border: 1px solid var(--primary); transition: filter 0.15s; }
.btn-primary:hover { filter: brightness(0.94); }
.btn-primary:disabled { opacity: 0.6; }
.btn-primary svg { width: 15px; height: 15px; }
.btn-outline { display: inline-flex; align-items: center; gap: 6px; background: var(--card); color: var(--foreground); border: 1px solid var(--border); font-family: var(--font-ui); font-size: 13.5px; font-weight: 550; padding: 8px 14px; border-radius: 8px; cursor: pointer; transition: border-color 0.15s, color 0.15s, background 0.15s; }
.btn-outline:hover { border-color: var(--primary); color: var(--primary); background: var(--accent); }
.btn-outline svg { width: 15px; height: 15px; }
.btn-ghost { color: var(--muted-foreground); font-family: var(--font-ui); font-size: 13.5px; font-weight: 500; padding: 8px 14px; border-radius: 8px; cursor: pointer; }
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
.field textarea { width: 100%; padding: 8px 11px; border-radius: 8px; border: 1px solid var(--input); background: var(--background); color: var(--foreground); font: inherit; font-size: 14px; resize: vertical; }
.field textarea:focus { outline: 2px solid var(--ring); outline-offset: -1px; border-color: var(--ring); }
.field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 18px; }
.modal-enter-active, .modal-leave-active { transition: opacity 0.18s; }
.modal-enter-from, .modal-leave-to { opacity: 0; }

/* ── Files: segmented modes + inbox ── */
.files-modes { display: flex; align-items: center; gap: 6px; margin-bottom: 16px; }
.refresh-btn { display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--card); color: var(--muted-foreground); font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; transition: color 0.15s, border-color 0.15s; }
.refresh-btn svg { width: 15px; height: 15px; }
.refresh-btn:hover { color: var(--primary); border-color: var(--primary); }
.refresh-btn:disabled { opacity: 0.6; cursor: default; }
.files-modes .refresh-btn { margin-left: auto; }
.refresh-btn.is-spinning svg { animation: rspin 0.7s linear infinite; }
@keyframes rspin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .refresh-btn.is-spinning svg { animation: none; } }
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
.is-processed td { color: var(--muted-foreground); }
.row-active > td { background: color-mix(in srgb, var(--primary) 8%, var(--card)); }

/* Row action group */
.row-acts { display: inline-flex; align-items: center; gap: 6px; justify-content: flex-end; }
.act { display: inline-grid; place-items: center; width: 30px; height: 30px; border: 1px solid transparent; border-radius: 8px; background: none; color: var(--muted-foreground); cursor: pointer; transition: background-color 0.13s ease, color 0.13s ease, border-color 0.13s ease; }
.act svg { width: 16px; height: 16px; }
.act:hover { background: var(--secondary); color: var(--foreground); }
.act--on { background: color-mix(in srgb, var(--primary) 12%, var(--card)); color: var(--primary); border-color: color-mix(in srgb, var(--primary) 35%, transparent); }
.done-btn { display: inline-flex; align-items: center; gap: 5px; height: 30px; padding: 0 11px; border: 1px solid var(--border); border-radius: 999px; background: var(--card); color: var(--muted-foreground); font: inherit; font-size: 12.5px; font-weight: 550; cursor: pointer; transition: all 0.13s ease; }
.done-btn svg { width: 14px; height: 14px; }
.done-btn:hover { border-color: color-mix(in srgb, var(--primary) 45%, var(--border)); color: var(--foreground); }
.done-btn.is-on { background: color-mix(in srgb, var(--success) 14%, var(--card)); border-color: color-mix(in srgb, var(--success) 40%, transparent); color: var(--success); }

/* Activity audit trail */
.act-tag { font-size: 0.68rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.02em; padding: 2px 8px; border-radius: 999px; color: var(--muted-foreground); background: var(--muted); }
.act-tag--upload { color: var(--info); background: color-mix(in srgb, var(--info) 12%, transparent); }
.act-tag--processed { color: var(--success); background: color-mix(in srgb, var(--success) 12%, transparent); }
.act-tag--delete, .act-tag--request_deleted { color: var(--destructive); background: color-mix(in srgb, var(--destructive) 12%, transparent); }
.act-tag--status_change, .act-tag--request_created { color: var(--info); background: color-mix(in srgb, var(--info) 10%, transparent); }

/* Inbox loading skeleton */
.sk-row td { padding: 10px; }
.sk-bar { display: block; height: 16px; border-radius: 6px; background: linear-gradient(90deg, var(--muted) 25%, var(--secondary) 37%, var(--muted) 63%); background-size: 400% 100%; animation: sk-shimmer 1.4s ease infinite; }
@keyframes sk-shimmer { 0% { background-position: 100% 0; } 100% { background-position: 0 0; } }

/* ── By-company switcher + detail ── */
.files-admin { display: flex; gap: 20px; align-items: flex-start; }
.files-admin .company-switcher { flex: 0 0 280px; }
.files-admin .files-detail { flex: 1 1 auto; min-width: 0; }
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
.fd-head-actions { display: flex; align-items: center; gap: 8px; }
.fd-bucket { margin-bottom: 22px; }
.bucket-empty { font-size: 0.82rem; color: var(--muted-foreground); padding: 4px 2px 2px; margin: 0; }
.checklist-add-link { display: inline-flex; align-items: center; background: none; border: none; color: var(--brand-accent); cursor: pointer; font: inherit; font-size: 0.8rem; font-weight: 550; padding: 2px 0; margin: 0 0 10px; }
.checklist-add-link:hover { text-decoration: underline; }
.fd-bucket h4 { font-size: 0.95rem; font-weight: 600; color: var(--foreground); margin: 0; }
.fd-bucket-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
.fd-bucket-title { display: flex; align-items: center; gap: 10px; min-width: 0; }
.kind-tag { font-size: 0.62rem; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; color: var(--info); border: 1px solid color-mix(in srgb, var(--info) 35%, var(--border)); background: color-mix(in srgb, var(--info) 10%, transparent); border-radius: 999px; padding: 1px 8px; }
.fd-desc { font-size: 0.85rem; color: var(--muted-foreground); margin: -2px 0 10px; max-width: 70ch; }
.fd-placeholder { color: var(--muted-foreground); font-size: 0.95rem; padding: 24px 0; }
.fd-edit { background: none; border: none; color: var(--muted-foreground); cursor: pointer; padding: 2px; border-radius: 6px; display: inline-grid; place-items: center; }
.fd-edit:hover { background: var(--muted); color: var(--foreground); }
.due { font-size: 0.72rem; font-weight: 550; color: var(--muted-foreground); }
.due--soon { color: var(--warning); font-weight: 650; }
.due--over { color: var(--destructive); font-weight: 650; }

/* Checklist */
.checklist { border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; margin: 0 0 14px; background: var(--card); }
.checklist-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.checklist-label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; color: var(--muted-foreground); }
.checklist-progress { font-size: 0.78rem; color: var(--muted-foreground); }
.progress-bar { height: 5px; border-radius: 999px; background: var(--secondary); overflow: hidden; margin-bottom: 10px; }
.progress-bar div { height: 100%; background: var(--success); transition: width 0.3s ease; }
.check-row { display: grid; grid-template-columns: 14px 1fr 200px 24px; align-items: center; gap: 8px; padding: 4px 0; }
.check-dot { width: 9px; height: 9px; border-radius: 50%; border: 1.5px solid var(--input); }
.check-dot--on { background: var(--success); border-color: var(--success); }
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
.review-select { height: 30px; border: 1px solid var(--input); border-radius: 7px; background: var(--background); color: var(--foreground); font: inherit; font-size: 12.5px; font-weight: 600; padding: 0 6px; }
.rv--pending { color: var(--muted-foreground); }
.rv--review { color: var(--info); border-color: color-mix(in srgb, var(--info) 45%, var(--input)); }
.rv--approved { color: var(--success); border-color: color-mix(in srgb, var(--success) 45%, var(--input)); }
.rv--revision { color: var(--destructive); border-color: color-mix(in srgb, var(--destructive) 45%, var(--input)); }

/* Split preview — flex so the table shrinks smoothly */
.split { display: flex; gap: 16px; align-items: flex-start; }
.split > .table-wrap { flex: 1 1 auto; min-width: 0; }
.split :deep(.pvp), .files-admin :deep(.pvp) { flex: 0 0 clamp(360px, 46%, 640px); }
.pane-enter-active, .pane-leave-active { transition: max-width 0.34s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.3s ease, transform 0.34s cubic-bezier(0.4, 0, 0.2, 1); overflow: hidden; }
.pane-enter-from, .pane-leave-to { max-width: 0; opacity: 0; transform: translateX(18px); }
.pane-enter-to, .pane-leave-from { max-width: 680px; }
.files-detail.compact .review-select,
.files-detail.compact .fd-row .ico-sm,
.files-detail.compact .fd-sub,
.files-detail.compact .fd-note,
.files-detail.compact .checklist { display: none; }
.files-detail.compact .fd-row { grid-template-columns: 1fr auto; }
.fd-row.row-active { box-shadow: inset 3px 0 0 var(--primary); border-color: color-mix(in srgb, var(--primary) 40%, var(--border)); }
@media (max-width: 720px) { .files-admin { flex-direction: column; } }
@media (prefers-reduced-motion: reduce) {
  .sk-bar { animation: none; }
  .pane-enter-active, .pane-leave-active { transition: none; }
  .pane-enter-from, .pane-leave-to { max-width: 680px; transform: none; }
}
</style>
