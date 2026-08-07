<template>
  <div class="files-admin-root">
    <div class="files-modes" role="tablist">
      <!-- One view per client, not a cross-client queue. The client list
           carries the "who sent something new" signal the inbox used to. -->
      <button role="tab" :aria-selected="filesMode==='company'" class="seg" :class="filesMode==='company' && 'seg--active'" @click="openCompanyTab">
        Clients <span v-if="totalUnseen" class="seg-badge">{{ totalUnseen }}</span>
      </button>
      <button role="tab" :aria-selected="filesMode==='activity'" class="seg" :class="filesMode==='activity' && 'seg--active'" @click="openActivity">
        Activity
      </button>
      <button class="btn-primary fm-new" @click="openRequest()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>
        New request
      </button>
      <button class="refresh-btn" :class="refreshing && 'is-spinning'" :disabled="refreshing" title="Refresh" aria-label="Refresh" @click="refresh">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v5h-5"/></svg>
        {{ refreshing ? 'Refreshing…' : 'Refresh' }}
      </button>
    </div>

    <!-- ACTIVITY: append-only audit trail -->
    <div v-show="filesMode==='activity'" class="activity">
      <div class="inbox-bar">
        <span class="panel-hint">Every upload, download, review, and status change — newest first.</span>
        <select v-model="activityCompany" class="inbox-select" @change="loadActivity" aria-label="Filter activity by company">
          <option :value="''">All clients</option>
          <option v-for="c in fileCompanies" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
      </div>
      <div v-for="g in activityGroups" :key="g.company" class="act-group">
        <h3 class="act-company">{{ g.company }} <span class="act-count">{{ g.items.length }}</span></h3>
        <div class="table-wrap">
          <table>
            <thead><tr><th>When</th><th>Who</th><th>Action</th><th>File</th></tr></thead>
            <tbody>
              <tr v-for="a in g.items" :key="a.id">
                <td class="dim">{{ fmtWhen(a.created_at) }}</td>
                <td>{{ a.actor }}</td>
                <td><span class="act-tag" :class="`act-tag--${a.action}`">{{ actionLabel(a.action) }}</span></td>
                <td>{{ a.file || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <p v-if="!activityItems.length" class="empty">No activity yet.</p>
    </div>

    <!-- BY COMPANY: drill-down switcher -->
    <div v-show="filesMode==='company'" class="files-admin" :class="{ 'has-preview': preview }">
      <aside class="company-switcher" v-show="!preview">
        <input v-model="fileCompanyQuery" class="cs-search" type="search" placeholder="Search companies…" aria-label="Search companies" />
        <ul class="cs-list">
          <li v-for="c in filteredFileCompanies" :key="c.id">
            <button class="cs-item" :class="c.id===selectedCompanyId && 'cs-item--active'" @click="selectCompany(c.id)">
              <span class="cs-name">
                {{ c.name }}
                <!-- The whole reason this list replaces the inbox. -->
                <span v-if="c.unseen_count" class="cs-new">{{ c.unseen_count }} new</span>
              </span>
              <span class="cs-counts">
                {{ c.file_count }} file{{ c.file_count===1?'':'s' }}<span v-if="c.open_request_count"> · {{ c.open_request_count }} open</span><span v-if="c.required_open_count" class="cs-req"> · {{ c.required_open_count }} required</span>
              </span>
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
          <!-- 1. WHAT THIS CLIENT STILL OWES US.
               Pinned above the files because it's the only thing on this
               screen with a deadline. Required requests first. -->
          <section v-if="requestBuckets.length" class="fd-needed">
            <h4 class="fd-section-title">Needed from this client</h4>
            <div v-for="b in requestBuckets" :key="b.id" class="fd-req" :class="b.required && 'fd-req--required'">
              <div class="fd-bucket-head">
                <div class="fd-bucket-title">
                  <h4>{{ b.title }}</h4>
                  <span v-if="b.required" class="kind-tag kind-tag--required">Required</span>
                  <span v-if="b.status === 'complete'" class="kind-tag kind-tag--done">Complete</span>
                  <span v-if="b.due_at" class="due" :class="`due--${dueTone(b)}`">{{ dueLabel(b) }}</span>
                </div>
                <button class="fd-edit" title="Edit request" @click="openRequest(b)" aria-label="Edit request">
                  <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.7"><path stroke-linecap="round" stroke-linejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125" /></svg>
                </button>
              </div>
              <p v-if="b.description" class="fd-desc">{{ b.description }}</p>

              <!-- The checklist IS the completion signal now that nothing gets
                   approved. Ticking an item links the file that satisfies it. -->
              <div v-if="b.checklist.length || showAdd[b.id]" class="checklist">
                <template v-if="b.checklist.length">
                  <div class="checklist-head">
                    <span class="checklist-label">Required documents</span>
                    <span class="checklist-progress">{{ b.checklist.filter(c=>c.linked_file).length }} / {{ b.checklist.length }} received</span>
                  </div>
                  <div class="progress-bar"><div :style="{ width: checklistPct(b) + '%' }" /></div>
                  <div v-for="c in b.checklist" :key="c.id" class="check-row">
                    <span class="check-dot" :class="c.linked_file && 'check-dot--on'" />
                    <span class="check-text" :class="c.linked_file && 'check-text--done'">{{ c.text }}</span>
                    <!-- Any of the client's files, wherever they filed it —
                         they won't have known which request it answered. -->
                    <select class="check-link" :value="c.linked_file || ''" :aria-label="`Link a file to: ${c.text}`" @change="linkChecklist(c, $event.target.value)">
                      <option value="">— link a file —</option>
                      <option v-for="f in allCompanyFiles" :key="f.id" :value="f.id">{{ f.original_name }}</option>
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

              <ul v-if="b.files.length" class="fd-rows">
                <li v-for="f in b.files" :key="f.id" class="fd-row" :class="preview && preview.id===f.id && 'row-active'">
                  <FileRow :file="f" :preview-id="preview && preview.id" @preview="openPreview" @comments="openComments" @seen="setSeen" />
                </li>
              </ul>
            </div>
          </section>

          <!-- 2. THE CLIENT'S OWN FILING, exactly as they see it. -->
          <section class="fd-files">
            <h4 class="fd-section-title">Files</h4>
            <div class="fd-browser">
              <div class="fd-tree">
                <button
                  v-if="generalBucket"
                  class="fd-tree-general"
                  :class="{ 'is-active': generalBucket.id === adminBucketId }"
                  @click="adminBucketId = generalBucket.id"
                >
                  <span class="fd-tree-general-title">{{ generalBucket.title }}</span>
                  <span v-if="unseenIn(generalBucket)" class="fn-newcount">{{ unseenIn(generalBucket) }} new</span>
                  <span v-if="generalBucket.files.length" class="fn-count">{{ generalBucket.files.length }}</span>
                </button>

                <ul v-if="adminTree.length" class="fs-tree">
                  <!-- read-only: an agent reorganising the client's folders
                       would move documents out from under them. -->
                  <FolderNode
                    v-for="node in adminTree"
                    :key="node.id"
                    :node="node"
                    :active-id="adminBucketId"
                    :read-only="true"
                    @select="adminBucketId = $event"
                  />
                </ul>
                <p v-else class="fd-tree-empty">This client hasn’t made any folders.</p>
              </div>

              <div class="fd-folder">
                <template v-if="adminBucket">
                  <div class="fd-folder-head">
                    <span v-if="adminCrumb" class="fd-path">{{ adminCrumb }}</span>
                    <h5>{{ adminBucket.title }}</h5>
                    <button v-if="unseenIn(adminBucket)" class="btn-ghost sm" @click="markFolderSeen(adminBucket)">
                      Mark {{ unseenIn(adminBucket) }} as seen
                    </button>
                  </div>
                  <ul v-if="adminBucket.files.length" class="fd-rows">
                    <li v-for="f in adminBucket.files" :key="f.id" class="fd-row" :class="preview && preview.id===f.id && 'row-active'">
                      <FileRow :file="f" :preview-id="preview && preview.id" @preview="openPreview" @comments="openComments" @seen="setSeen" />
                    </li>
                  </ul>
                  <p v-else class="bucket-empty">Nothing in this folder.</p>
                </template>
                <p v-else class="bucket-empty">Pick a folder to see what’s in it.</p>
              </div>
            </div>
          </section>
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
          <label v-if="!reqEditing" class="field"><span>Client</span>
            <select v-model="reqForm.company_id">
              <option value="">Select a client…</option>
              <option v-for="c in fileCompanies" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
          </label>
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
          <label class="field-check">
            <input v-model="reqForm.required" type="checkbox" />
            <span>
              <strong>Required</strong> — show this at the top of the customer’s
              file page as something they must send.
              <em>Leave off for nice-to-haves: a long list of equally-urgent
              demands gets read as noise and none of it gets done.</em>
            </span>
          </label>
          <div class="modal-actions">
            <button class="btn-ghost" @click="reqModal=false">Cancel</button>
            <button class="btn-primary" :disabled="reqSaving" @click="saveRequest">{{ reqSaving ? 'Saving…' : (reqEditing ? 'Save' : 'Create request') }}</button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- Internal comments modal -->
    <Transition name="modal">
      <div v-if="commentsFile" class="modal-overlay" @click.self="commentsFile=null">
        <div class="modal comments-modal" role="dialog" aria-modal="true">
          <h2 class="modal-title">Comments</h2>
          <p class="comments-file">{{ commentsFile.name }}</p>
          <p class="comments-internal">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z"/></svg>
            Internal — only the CiteMed team can see this.
          </p>
          <div class="comments-thread">
            <div v-for="c in comments" :key="c.id" class="comment">
              <div class="comment-head"><span class="comment-author">{{ c.author }}</span><span class="comment-time">{{ fmtWhen(c.created_at) }}</span></div>
              <p class="comment-body">{{ c.body }}</p>
            </div>
            <p v-if="!comments.length" class="comments-empty">No comments yet — start the discussion below.</p>
          </div>
          <textarea v-model="commentDraft" class="comment-input" rows="3" placeholder="Write a comment for the team…"></textarea>
          <div class="modal-actions">
            <button class="btn-ghost" @click="commentsFile=null">Close</button>
            <button class="btn-primary" :disabled="commentsAdding || !commentDraft.trim()" @click="addComment">{{ commentsAdding ? 'Posting…' : 'Add comment' }}</button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import FilePreviewPane from '@/components/files/FilePreviewPane.vue'
import FolderNode from '@/components/files/FolderNode.vue'
import FileRow from '@/components/files/FileRow.vue'
import { apiFetch } from '../../lib/http.js'
import { buildFolderTree, folderPath, unseenIn } from '../../lib/folders.js'

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
const totalUnseen = computed(() =>
  fileCompanies.value.reduce((n, c) => n + (c.unseen_count || 0), 0)
)

// Requests are what the client still owes us, so required and still-open ones
// come first; complete ones sink but stay visible as a record.
const requestBuckets = computed(() => {
  const rank = (b) => (b.status === 'complete' ? 2 : b.required ? 0 : 1)
  return companyBuckets.value
    .filter((b) => b.kind === 'request')
    .slice()
    .sort((a, b) => rank(a) - rank(b) || a.title.localeCompare(b.title))
})

const generalBucket = computed(() =>
  companyBuckets.value.find((b) => b.kind === 'general') || null
)

// Built with the SAME helper the customer page uses, so "the structure your
// client sees" is a fact rather than a claim.
const adminTree = computed(() => buildFolderTree(companyBuckets.value))

const adminBucketId = ref(null)
const adminBucket = computed(() =>
  companyBuckets.value.find((b) => b.id === adminBucketId.value) || null
)
const adminCrumb = computed(() => {
  const path = folderPath(companyBuckets.value, adminBucketId.value)
  return path.slice(0, -1).map((p) => p.title).join(' / ')
})

/** Every file this client has, wherever it sits — the checklist links against
 *  this, because the client had no way of knowing which request a document
 *  was meant to answer when they filed it. */
const allCompanyFiles = computed(() =>
  companyBuckets.value
    .flatMap((b) => b.files || [])
    .slice()
    .sort((a, b) => a.original_name.localeCompare(b.original_name))
)

// 'company' is the only file view now; 'activity' is the audit trail.
const filesMode = ref('company')

async function loadFileCompanies(force = false) {
  if (!force && fileCompanies.value.length) return
  const r = await apiFetch('/api/admin/files/companies/', { credentials: 'include' })
  if (r.ok) fileCompanies.value = (await r.json()).companies
}

const refreshing = ref(false)
async function refresh() {
  refreshing.value = true
  try {
    if (filesMode.value === 'activity') {
      await loadActivity()
    } else {
      // Always reload the client list: its unseen counts are the only signal
      // that another client uploaded while you were looking at this one.
      await loadFileCompanies(true)
      if (selectedCompanyId.value) await selectCompany(selectedCompanyId.value)
    }
  } finally {
    refreshing.value = false
  }
}

async function openCompanyTab() {
  preview.value = null
  filesMode.value = 'company'
  await loadFileCompanies()
  // Never show a blank pane: auto-open the first company if none is selected.
  if (!selectedCompanyId.value && fileCompanies.value.length) {
    await selectCompany(fileCompanies.value[0].id)
  }
}

// Internal comments
const commentsFile = ref(null)   // { id, name }
const comments = ref([])
const commentDraft = ref('')
const commentsAdding = ref(false)
async function openComments(id, name) {
  commentsFile.value = { id, name }
  comments.value = []
  commentDraft.value = ''
  const r = await apiFetch(`/api/admin/files/${id}/comments`, { credentials: 'include' })
  if (r.ok) comments.value = (await r.json()).comments
}
function bumpCommentCount(id) {
  for (const b of companyBuckets.value) {
    const f = b.files.find((x) => x.id === id)
    if (f) f.comment_count = (f.comment_count || 0) + 1
  }
}
async function addComment() {
  const body = commentDraft.value.trim()
  if (!body || !commentsFile.value) return
  commentsAdding.value = true
  try {
    const r = await apiFetch(`/api/admin/files/${commentsFile.value.id}/comments`, {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ body }),
    })
    if (r.ok) {
      comments.value.push(await r.json())
      commentDraft.value = ''
      bumpCommentCount(commentsFile.value.id)
    }
  } finally {
    commentsAdding.value = false
  }
}

// Activity (audit trail)
const activityItems = ref([])
const activityCompany = ref('')
// Group the (newest-first) feed by company; group order follows recency.
const activityGroups = computed(() => {
  const map = new Map()
  for (const a of activityItems.value) {
    const key = a.company || '—'
    if (!map.has(key)) map.set(key, [])
    map.get(key).push(a)
  }
  return Array.from(map, ([company, items]) => ({ company, items }))
})
async function loadActivity() {
  const params = new URLSearchParams({ limit: '200' })
  if (activityCompany.value) params.set('company', activityCompany.value)
  const r = await apiFetch(`/api/admin/files/activity/?${params}`, { credentials: 'include' })
  if (r.ok) activityItems.value = (await r.json()).items
}
function openActivity() {
  preview.value = null
  filesMode.value = 'activity'
  loadActivity()
}
const ACTION_LABELS = {
  upload: 'Uploaded', download: 'Downloaded', rename: 'Renamed', delete: 'Deleted',
  status_change: 'Review changed', note: 'Note', comment: 'Commented', request_created: 'Request created',
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
/** The only per-file state left: has anyone here looked at it.
 *  Optimistic — the dot must clear the instant you click, or you lose your
 *  place scanning a long folder waiting for a round trip. */
async function setSeen(f, seen) {
  const before = f.seen
  f.seen = seen
  const r = await apiFetch(`/api/admin/files/${f.id}/processed`, {
    method: 'PATCH', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ processed: seen }),
  })
  if (!r.ok) {
    f.seen = before
    return
  }
  bumpCompanyUnseen(seen ? -1 : 1)
}

/** Clear a whole folder at once — the realistic action after you've opened a
 *  client and worked through what they sent. */
async function markFolderSeen(bucket) {
  const pending = (bucket.files || []).filter((f) => f.seen === false)
  for (const f of pending) await setSeen(f, true)
}

/** Keep the client list's badge honest without refetching it. */
function bumpCompanyUnseen(delta) {
  const c = fileCompanies.value.find((x) => x.id === selectedCompanyId.value)
  if (c) c.unseen_count = Math.max(0, (c.unseen_count || 0) + delta)
}

async function addChecklist(b) {
  const text = (checklistDraft.value[b.id] || '').trim()
  if (!text) return
  const r = await apiFetch('/api/admin/files/checklist/', {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bucket_id: b.id, text }),
  })
  if (r.ok) { checklistDraft.value[b.id] = ''; await selectCompany(selectedCompanyId.value) }
}
async function linkChecklist(item, fileId) {
  const r = await apiFetch(`/api/admin/files/checklist/${item.id}/`, {
    method: 'PATCH', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ linked_file_id: fileId ? Number(fileId) : null }),
  })
  if (r.ok) await selectCompany(selectedCompanyId.value)
}
async function removeChecklist(item) {
  const r = await apiFetch(`/api/admin/files/checklist/${item.id}/`, { method: 'DELETE', credentials: 'include' })
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
async function selectCompany(id) {
  preview.value = null
  selectedCompanyId.value = id
  const r = await apiFetch(`/api/admin/files/companies/${id}/`, { credentials: 'include' })
  if (r.ok) {
    const data = await r.json()
    selectedCompany.value = data.company
    companyBuckets.value = data.buckets
    // Land wherever the new files are, otherwise General uploads. Opening on
    // an empty folder when the client just sent three documents is the exact
    // failure the unseen counts exist to prevent.
    const withNew = data.buckets
      .filter((b) => unseenIn(b) > 0)
      .sort((a, b) => unseenIn(b) - unseenIn(a))[0]
    const general = data.buckets.find((b) => b.kind === 'general')
    adminBucketId.value = (withNew || general || data.buckets[0] || {}).id ?? null
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
const reqForm = ref({ title: '', description: '', due_at: '', status: 'open', required: false, company_id: '' })

function openRequest(b = null) {
  reqEditing.value = b
  reqError.value = ''
  reqForm.value = b
    ? { title: b.title, description: b.description || '', due_at: b.due_at ? b.due_at.slice(0, 10) : '', status: b.status === 'general' ? 'open' : b.status, required: !!b.required, company_id: selectedCompanyId.value || '' }
    : { title: '', description: '', due_at: '', status: 'open', required: false, company_id: selectedCompanyId.value || '' }
  reqModal.value = true
}
async function saveRequest() {
  // Company comes from the picker (top-level) or the open company (drill-down).
  const companyId = reqForm.value.company_id || selectedCompanyId.value
  if (!reqEditing.value && !companyId) {
    reqError.value = 'Please select a client.'
    return
  }
  reqSaving.value = true
  reqError.value = ''
  try {
    const payload = { ...reqForm.value, due_at: reqForm.value.due_at || null, company_id: companyId }
    const url = reqEditing.value
      ? `/api/admin/files/requests/${reqEditing.value.id}/`
      : '/api/admin/files/requests/'
    const r = await apiFetch(url, {
      method: reqEditing.value ? 'PATCH' : 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || 'Could not save request')
    reqModal.value = false
    // Land on the request we just created/edited so the admin sees it.
    filesMode.value = 'company'
    await loadFileCompanies(true)
    await selectCompany(Number(companyId))
  } catch (e) {
    reqError.value = e.message
  } finally {
    reqSaving.value = false
  }
}

onMounted(loadFileCompanies)
</script>

<style scoped>
/* ── Shared primitives (this component is self-contained) ── */
.panel-hint { font-size: 12.5px; color: var(--muted-foreground); }
.table-wrap { border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden; background: var(--card); }
table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13.5px; }
th { text-align: left; font-family: var(--font-ui); font-size: 11px; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; color: var(--muted-foreground); padding: 11px 14px; background: var(--muted); border-bottom: 1px solid var(--border); }
td { padding: 11px 14px; border-bottom: 1px solid var(--border-subtle); color: var(--foreground); vertical-align: middle; }
tbody tr:last-child td { border-bottom: none; }
tbody tr:hover td { background: var(--accent); }
.ta-r { text-align: right; white-space: nowrap; }
.empty { text-align: center; color: var(--muted-foreground); padding: 28px; }
.btn-primary { display: inline-flex; align-items: center; gap: 6px; background: var(--primary); color: var(--primary-foreground); font-family: var(--font-ui); font-size: 13.5px; font-weight: 600; padding: 8px 14px; border-radius: var(--radius-sm); cursor: pointer; border: 1px solid var(--primary); transition: filter 0.15s; }
.btn-primary:hover { filter: brightness(0.94); }
.btn-primary:disabled { opacity: 0.6; }
.btn-primary svg { width: 15px; height: 15px; }
.btn-outline { display: inline-flex; align-items: center; gap: 6px; background: var(--card); color: var(--foreground); border: 1px solid var(--border); font-family: var(--font-ui); font-size: 13.5px; font-weight: 550; padding: 8px 14px; border-radius: var(--radius-sm); cursor: pointer; transition: border-color 0.15s, color 0.15s, background 0.15s; }
.btn-outline:hover { border-color: var(--primary); color: var(--primary); background: var(--accent); }
.btn-outline svg { width: 15px; height: 15px; }
.btn-ghost { color: var(--muted-foreground); font-family: var(--font-ui); font-size: 13.5px; font-weight: 500; padding: 8px 14px; border-radius: var(--radius-sm); cursor: pointer; }
.btn-ghost:hover { background: var(--muted); color: var(--foreground); }

/* Modal */
.modal-overlay { position: fixed; inset: 0; z-index: 60; background: oklch(0 0 0 / 0.45); display: flex; align-items: center; justify-content: center; padding: 20px; }
.modal { width: 100%; max-width: 440px; background: var(--popover); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 22px; box-shadow: 0 20px 50px oklch(0 0 0 / 0.25); }
.modal-title { font-family: var(--font-ui); font-size: 1.15rem; font-weight: 600; color: var(--foreground); margin: 0 0 14px; }
.form-error { color: var(--destructive); font-size: 0.85rem; margin: 0 0 10px; }
.field { display: block; margin-bottom: 13px; }
.field > span { display: block; font-family: var(--font-ui); font-size: 12px; font-weight: 600; color: var(--muted-foreground); margin-bottom: 5px; }
.field input, .field select { width: 100%; height: 38px; padding: 0 11px; border-radius: var(--radius-sm); border: 1px solid var(--input); background: var(--background); color: var(--foreground); font-size: 14px; }
.field input:focus, .field select:focus { outline: 2px solid var(--ring); outline-offset: -1px; border-color: var(--ring); }
.field textarea { width: 100%; padding: 8px 11px; border-radius: var(--radius-sm); border: 1px solid var(--input); background: var(--background); color: var(--foreground); font: inherit; font-size: 14px; resize: vertical; }
.field textarea:focus { outline: 2px solid var(--ring); outline-offset: -1px; border-color: var(--ring); }
.field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 18px; }
.modal-enter-active, .modal-leave-active { transition: opacity 0.18s; }
.modal-enter-from, .modal-leave-to { opacity: 0; }

/* ── Files: segmented modes + inbox ── */
.files-modes { display: flex; align-items: center; gap: 6px; margin-bottom: 16px; }
.refresh-btn { display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 12px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--card); color: var(--muted-foreground); font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; transition: color 0.15s, border-color 0.15s; }
.refresh-btn svg { width: 15px; height: 15px; }
.refresh-btn:hover { color: var(--primary); border-color: var(--primary); }
.refresh-btn:disabled { opacity: 0.6; cursor: default; }
.files-modes .fm-new { margin-left: auto; }
.files-modes .fm-new svg { width: 15px; height: 15px; }
.refresh-btn.is-spinning svg { animation: rspin 0.7s linear infinite; }
@keyframes rspin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .refresh-btn.is-spinning svg { animation: none; } }
.seg { display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--card); color: var(--muted-foreground); font: inherit; font-size: 13.5px; font-weight: 550; cursor: pointer; }
.seg:hover { color: var(--foreground); }
.seg--active { border-color: var(--primary); background: color-mix(in srgb, var(--primary) 8%, var(--card)); color: var(--primary); }
.seg-badge { font-size: 11px; font-weight: 700; background: var(--primary); color: var(--primary-foreground); border-radius: 999px; padding: 1px 7px; }
.inbox-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.inbox-filters { display: flex; align-items: center; gap: 10px; }
.inbox-select { height: 34px; padding: 0 10px; border-radius: var(--radius-sm); border: 1px solid var(--input); background: var(--background); color: var(--foreground); font: inherit; font-size: 13px; }
.sm-seg { display: inline-flex; border: 1px solid var(--border); border-radius: var(--radius-sm); overflow: hidden; }
.sm-seg button { border: none; background: var(--card); color: var(--muted-foreground); font: inherit; font-size: 12.5px; font-weight: 550; padding: 6px 12px; cursor: pointer; }
.sm-seg button.on { background: color-mix(in srgb, var(--primary) 10%, var(--card)); color: var(--primary); }
.mini-btn { height: 28px; padding: 0 10px; border-radius: var(--radius-sm); border: 1px solid var(--border); background: var(--card); font: inherit; font-size: 12px; font-weight: 600; cursor: pointer; transition: background 0.13s, border-color 0.13s, color 0.13s; }
.mini-btn--approve { color: var(--success); border-color: color-mix(in srgb, var(--success) 40%, var(--border)); }
.mini-btn--approve:hover { background: color-mix(in srgb, var(--success) 12%, var(--card)); }
.mini-btn--revision { color: var(--destructive); border-color: color-mix(in srgb, var(--destructive) 38%, var(--border)); }
.mini-btn--revision:hover { background: color-mix(in srgb, var(--destructive) 10%, var(--card)); }
.rv-pill { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.02em; padding: 3px 9px; border-radius: 999px; }
.rv-pill--approved { color: var(--success); background: color-mix(in srgb, var(--success) 14%, transparent); }
.rv-pill--revision { color: var(--destructive); background: color-mix(in srgb, var(--destructive) 14%, transparent); }
.link { background: none; border: none; color: var(--brand-accent); cursor: pointer; font: inherit; padding: 0; }
.link:hover { text-decoration: underline; }
.dim { color: var(--muted-foreground); font-size: 12px; }
.is-processed td { color: var(--muted-foreground); }
.row-active > td { background: color-mix(in srgb, var(--primary) 8%, var(--card)); }

/* Row action group */
.row-acts { display: inline-flex; align-items: center; gap: 6px; justify-content: flex-end; }
.act { position: relative; display: inline-grid; place-items: center; width: 30px; height: 30px; border: 1px solid transparent; border-radius: var(--radius-sm); background: none; color: var(--muted-foreground); cursor: pointer; transition: background-color 0.13s ease, color 0.13s ease, border-color 0.13s ease; }
.act-badge { position: absolute; top: -5px; right: -5px; min-width: 16px; height: 16px; padding: 0 4px; border-radius: 999px; background: var(--primary); color: var(--primary-foreground); font-size: 10px; font-weight: 700; line-height: 16px; text-align: center; box-shadow: 0 0 0 2px var(--card); }
.act--comment:hover { color: var(--primary); }
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
/* Comments modal */
.comments-modal { max-width: 480px; }
.comments-file { font-size: 0.82rem; color: var(--muted-foreground); margin: -8px 0 10px; word-break: break-word; }
.comments-internal { display: flex; align-items: center; gap: 6px; font-size: 0.72rem; font-weight: 600; color: var(--muted-foreground); background: var(--muted); border-radius: var(--radius-sm); padding: 6px 10px; margin: 0 0 12px; }
.comments-internal svg { width: 13px; height: 13px; flex-shrink: 0; }
.comments-thread { max-height: 40vh; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; margin-bottom: 12px; }
.comment { border-left: 2px solid var(--border); padding-left: 10px; }
.comment-head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 2px; }
.comment-author { font-size: 0.82rem; font-weight: 650; color: var(--foreground); }
.comment-time { font-size: 0.7rem; color: var(--muted-foreground); }
.comment-body { font-size: 0.86rem; color: var(--foreground); line-height: 1.45; margin: 0; white-space: pre-wrap; }
.comments-empty { font-size: 0.85rem; color: var(--muted-foreground); text-align: center; padding: 16px 0; }
.comment-input { width: 100%; border: 1px solid var(--input); border-radius: var(--radius-sm); background: var(--background); color: var(--foreground); font: inherit; font-size: 13.5px; padding: 8px 11px; resize: vertical; }
.comment-input:focus { outline: 2px solid var(--ring); outline-offset: -1px; }
.act-tag--comment { color: var(--info); background: color-mix(in srgb, var(--info) 10%, transparent); }

.act-group { margin-bottom: 20px; }
.act-company { display: flex; align-items: center; gap: 8px; font-family: var(--font-ui); font-size: 0.95rem; font-weight: 600; color: var(--foreground); margin: 0 0 8px; }
.act-count { font-size: 11px; font-weight: 700; color: var(--muted-foreground); background: var(--muted); border-radius: 999px; padding: 1px 8px; }

/* Inbox loading skeleton */
.sk-row td { padding: 10px; }
.sk-bar { display: block; height: 16px; border-radius: var(--radius-sm); background: linear-gradient(90deg, var(--muted) 25%, var(--secondary) 37%, var(--muted) 63%); background-size: 400% 100%; animation: sk-shimmer 1.4s ease infinite; }
@keyframes sk-shimmer { 0% { background-position: 100% 0; } 100% { background-position: 0 0; } }

/* ── By-company switcher + detail ── */
.files-admin { display: flex; gap: 20px; align-items: flex-start; }
.files-admin .company-switcher { flex: 0 0 280px; }
.files-admin .files-detail { flex: 1 1 auto; min-width: 0; }
.company-switcher { border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 10px; background: var(--card); }
.cs-search { width: 100%; height: 36px; padding: 0 11px; border-radius: var(--radius-sm); border: 1px solid var(--input); background: var(--background); color: var(--foreground); font-size: 13.5px; margin-bottom: 8px; }
.cs-search:focus { outline: 2px solid var(--ring); outline-offset: -1px; }
.cs-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; max-height: 60vh; overflow-y: auto; }
.cs-item { width: 100%; text-align: left; display: flex; flex-direction: column; gap: 2px; padding: 9px 11px; border-radius: var(--radius-sm); cursor: pointer; background: none; border: 1px solid transparent; transition: background-color 0.12s ease, border-color 0.12s ease; }
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
.fd-bucket-title { display: flex; align-items: center; gap: 10px; min-width: 0; flex-wrap: wrap; }
.fd-path { font-size: 0.74rem; color: var(--muted-foreground); }
.field-check { display: flex; gap: 9px; align-items: flex-start; margin-top: 0.9rem; font-size: 0.83rem; color: var(--foreground); }
.field-check input { margin-top: 3px; flex-shrink: 0; }
.field-check em { display: block; margin-top: 3px; font-style: normal; font-size: 0.78rem; color: var(--muted-foreground); }
.kind-tag { font-size: 0.62rem; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; color: var(--info); border: 1px solid color-mix(in srgb, var(--info) 35%, var(--border)); background: color-mix(in srgb, var(--info) 10%, transparent); border-radius: 999px; padding: 1px 8px; }
.fd-desc { font-size: 0.85rem; color: var(--muted-foreground); margin: -2px 0 10px; max-width: 70ch; }
.fd-placeholder { color: var(--muted-foreground); font-size: 0.95rem; padding: 24px 0; }
.fd-edit { background: none; border: none; color: var(--muted-foreground); cursor: pointer; padding: 2px; border-radius: var(--radius-sm); display: inline-grid; place-items: center; }
.fd-edit:hover { background: var(--muted); color: var(--foreground); }
.due { font-size: 0.72rem; font-weight: 550; color: var(--muted-foreground); }
.due--soon { color: var(--warning); font-weight: 650; }
.due--over { color: var(--destructive); font-weight: 650; }

/* Checklist */
.checklist { border: 1px solid var(--border); border-radius: var(--radius-md); padding: 12px 14px; margin: 0 0 14px; background: var(--card); }
.checklist-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.checklist-label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; color: var(--muted-foreground); }
.checklist-progress { font-size: 0.78rem; color: var(--muted-foreground); }
.progress-bar { height: 5px; border-radius: 999px; background: var(--secondary); overflow: hidden; margin-bottom: 10px; }
.progress-bar div { height: 100%; background: var(--success); transition: width 0.3s ease; }
.check-row { display: grid; grid-template-columns: 14px 1fr 200px 24px; align-items: center; gap: 8px; padding: 4px 0; }
.check-dot { width: 9px; height: 9px; border-radius: 50%; border: 1.5px solid var(--input); }
.check-dot--on { background: var(--success); border-color: var(--success); }
.check-text { font-size: 0.85rem; color: var(--foreground); }
.check-link { height: 30px; border: 1px solid var(--input); border-radius: var(--radius-sm); background: var(--background); color: var(--foreground); font: inherit; font-size: 12.5px; padding: 0 8px; max-width: 200px; }
.check-add { display: flex; gap: 8px; margin-top: 8px; }
.check-add input { flex: 1; height: 32px; border: 1px solid var(--input); border-radius: var(--radius-sm); background: var(--background); color: var(--foreground); font: inherit; font-size: 13px; padding: 0 10px; }
.ico-sm { width: 24px; height: 24px; display: inline-grid; place-items: center; border: none; background: none; color: var(--muted-foreground); border-radius: var(--radius-sm); cursor: pointer; font-size: 16px; }
.ico-sm svg { width: 13px; height: 13px; }
.ico-sm:hover { background: var(--secondary); color: var(--foreground); }

/* File rows (company view) */
.fd-rows { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
/* Two columns now the review select and note button are gone. */
.fd-row { display: flex; align-items: center; gap: 12px; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); }

/* ── Client view: what they owe us, then their own filing ── */
.fd-section-title {
  font-size: 0.7rem; font-weight: 700; letter-spacing: 0.06em;
  text-transform: uppercase; color: var(--muted-foreground);
  margin: 0 0 10px;
}
.fd-needed { margin-bottom: 26px; }
.fd-req {
  padding: 12px 14px; margin-bottom: 10px;
  border: 1px solid var(--border); border-radius: var(--radius-md);
  background: var(--card);
}
/* The only accent on the page — a request that actually blocks the client. */
.fd-req--required { border-color: color-mix(in srgb, var(--warning) 50%, var(--border)); }
.kind-tag--required { color: var(--warning); border-color: color-mix(in srgb, var(--warning) 40%, var(--border)); background: color-mix(in srgb, var(--warning) 10%, transparent); }
.kind-tag--done { color: var(--success); border-color: color-mix(in srgb, var(--success) 35%, var(--border)); background: color-mix(in srgb, var(--success) 10%, transparent); }
.check-text--done { color: var(--muted-foreground); text-decoration: line-through; }

.fd-browser { display: grid; grid-template-columns: 250px minmax(0, 1fr); gap: 20px; align-items: start; }
@media (max-width: 900px) { .fd-browser { grid-template-columns: 1fr; } }
.fd-tree { border: 1px solid var(--border); border-radius: var(--radius-md); padding: 8px; }
.fd-tree .fs-tree { list-style: none; margin: 4px 0 0; padding: 0; }
.fd-tree-general {
  display: flex; align-items: center; gap: 7px; width: 100%;
  border: 0; background: none; border-radius: 7px; cursor: pointer;
  padding: 6px 8px; text-align: left;
  font-family: var(--font-ui); font-size: 0.84rem; font-weight: 600; color: var(--foreground);
}
.fd-tree-general:hover { background: color-mix(in srgb, var(--accent) 60%, transparent); }
.fd-tree-general.is-active { background: var(--accent); }
.fd-tree-general-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fd-tree-empty { font-size: 0.78rem; color: var(--muted-foreground); padding: 6px 8px; margin: 0; }
/* FolderNode's badges are scoped to it, so General uploads needs its own
   copies to sit level with the folders below it. */
.fd-tree-general .fn-count { font-size: 0.72rem; color: var(--muted-foreground); font-variant-numeric: tabular-nums; }
.fd-tree-general .fn-newcount {
  font-size: 0.68rem; font-weight: 700;
  color: var(--primary); background: color-mix(in srgb, var(--primary) 12%, transparent);
  border-radius: 999px; padding: 1px 7px;
}

.fd-folder-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }
.fd-folder-head h5 { font-size: 1rem; font-weight: 700; color: var(--foreground); margin: 0; }
.btn-ghost.sm { font-size: 0.76rem; padding: 3px 9px; }

.cs-name { display: flex; align-items: center; gap: 8px; }
.cs-new {
  font-size: 0.62rem; font-weight: 700; letter-spacing: 0.02em;
  color: var(--primary); background: color-mix(in srgb, var(--primary) 13%, transparent);
  border-radius: 999px; padding: 1px 7px; white-space: nowrap;
}
.cs-req { color: var(--warning); }
.fd-file { min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.fd-name { font-size: 0.88rem; font-weight: 550; color: var(--foreground); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fd-sub { font-size: 0.74rem; color: var(--muted-foreground); }
.fd-note { font-size: 0.74rem; color: var(--destructive); margin-top: 2px; }
.review-select { height: 30px; border: 1px solid var(--input); border-radius: var(--radius-sm); background: var(--background); color: var(--foreground); color-scheme: light dark; font: inherit; font-size: 12.5px; font-weight: 600; padding: 0 8px; min-width: 120px; }
.review-select option { background: var(--popover); color: var(--foreground); }
.rv--pending { color: var(--warning); border-color: color-mix(in srgb, var(--warning) 45%, var(--input)); }
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
