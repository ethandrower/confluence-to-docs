<template>
  <AppShell hide-sidebar>
    <template #content>
      <div class="fs" :class="{ 'has-preview': preview }">
        <!-- Sidebar -->
        <aside class="fs-side" aria-label="File buckets">
          <div class="fs-group">
            <div class="fs-group-head">
              <h2 class="fs-group-title">Requests from CiteMed</h2>
              <button class="refresh-mini" :class="store.loading && 'is-spinning'" :disabled="store.loading" title="Refresh" aria-label="Refresh requests" @click="store.load()">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v5h-5"/></svg>
                Refresh
              </button>
            </div>
            <p v-if="!store.requests.length && !store.loading" class="fs-group-empty">Nothing requested yet.</p>
            <button
              v-for="b in store.requests"
              :key="b.id"
              class="b-card"
              :class="{ 'is-active': b.id === store.activeBucketId }"
              @click="store.select(b.id)"
            >
              <span class="b-title">{{ b.title }}</span>
              <span class="b-meta">
                <span class="status" :class="`status--${statusTone(b)}`">
                  <span class="dot" /> {{ statusLabel(b) }}
                </span>
                <span v-if="duePill(b)" class="due" :class="`due--${duePill(b).tone}`">{{ duePill(b).label }}</span>
              </span>
            </button>
          </div>

          <div class="fs-group">
            <h2 class="fs-group-title">Your files</h2>
            <button
              v-if="store.generalBucket"
              class="b-card"
              :class="{ 'is-active': store.generalBucket.id === store.activeBucketId }"
              @click="store.select(store.generalBucket.id)"
            >
              <span class="b-title">{{ store.generalBucket.title }}</span>
              <span class="b-meta">
                <span class="status status--muted"><span class="dot" /> {{ store.generalBucket.files.length }} file{{ store.generalBucket.files.length === 1 ? '' : 's' }}</span>
              </span>
            </button>
          </div>
        </aside>

        <!-- Detail -->
        <section class="fs-main">
          <template v-if="store.loading && !store.buckets.length">
            <div class="skeleton-head" />
            <div class="skeleton-drop" />
            <div class="skeleton-row" v-for="n in 3" :key="n" />
          </template>

          <template v-else-if="active">
            <header class="fs-head">
              <div>
                <h1>{{ active.title }}</h1>
                <p v-if="active.kind === 'request'" class="fs-submeta">
                  <span v-if="active.requested_by_name">Requested by {{ active.requested_by_name }}</span>
                  <span v-if="active.created_at"> · {{ relDate(active.created_at) }}</span>
                  <span v-if="active.due_at" class="fs-due" :class="duePill(active) ? `due--${duePill(active).tone}` : ''"> · Due {{ shortDate(active.due_at) }}</span>
                </p>
              </div>
              <button class="refresh-btn" :class="store.loading && 'is-spinning'" :disabled="store.loading" title="Refresh" aria-label="Refresh" @click="store.load()">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v5h-5"/></svg>
                {{ store.loading ? 'Refreshing…' : 'Refresh' }}
              </button>
            </header>

            <p v-if="active.description" class="fs-desc">{{ active.description }}</p>

            <div v-if="active.kind === 'request' && active.checklist && active.checklist.length" class="fs-check">
              <div class="fs-check-head">
                <span class="fs-check-label">Requested documents</span>
                <span class="fs-check-count">{{ checklistReceived(active) }} / {{ active.checklist.length }} received</span>
              </div>
              <div class="fs-check-bar"><div :style="{ width: checklistPct(active) + '%' }" /></div>
              <ul class="fs-check-list">
                <li v-for="c in active.checklist" :key="c.id" :class="{ done: c.linked_file }">
                  <span class="fs-check-dot" :class="c.linked_file && 'on'" />
                  <span class="fs-check-text">{{ c.text }}</span>
                  <span v-if="c.linked_file" class="fs-check-recv">Received</span>
                </li>
              </ul>
            </div>

            <FileUploader :bucket-id="active.id" :label="uploadLabel" :key="active.id" @uploaded="onUploaded" />

            <div class="files">
              <div class="files-bar">
                <span class="files-count">{{ active.files.length }} file{{ active.files.length === 1 ? '' : 's' }}</span>
                <input v-if="active.files.length" v-model="q" class="files-search" type="search" placeholder="Search…" aria-label="Search files" />
              </div>

              <ul v-if="filtered.length" class="rows">
                <li v-for="f in filtered" :key="f.id" class="row" :class="{ flash: flash.has(f.original_name), 'row-active': preview && preview.id === f.id }">
                  <span class="tile" :data-cat="cat(f.original_name)">{{ ext(f.original_name) }}</span>
                  <div class="row-main">
                    <template v-if="editingId === f.id">
                      <input ref="renameInput" v-model="editName" class="rename" @keydown.enter="saveRename(f)" @keydown.esc="cancelRename" @blur="saveRename(f)" />
                    </template>
                    <span v-else class="row-name" :title="f.original_name">{{ f.original_name }}</span>
                    <span class="row-sub">
                      {{ fmtSize(f.size_bytes) }} · {{ relDate(f.uploaded_at) }}
                      <span v-if="f.review_status" class="rv-badge" :class="`rv-badge--${f.review_status}`">{{ reviewLabel(f.review_status) }}</span>
                    </span>
                    <span v-if="f.review_notes" class="rv-note">{{ f.review_notes }}</span>
                  </div>
                  <span class="row-actions">
                    <button v-if="previewable(f.original_name)" class="ico" :class="preview && preview.id === f.id && 'ico--on'" :title="preview && preview.id === f.id ? 'Close preview' : 'Preview'" aria-label="Preview" @click="openPreview(f)">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8Z"/><circle cx="12" cy="12" r="3"/></svg>
                    </button>
                    <a class="ico" :href="store.downloadUrl(f.id)" title="Download" aria-label="Download">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                    </a>
                    <button class="ico" title="Rename" aria-label="Rename" @click="startRename(f)">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 1 1 3 3L7 19l-4 1 1-4Z"/></svg>
                    </button>
                    <button class="ico ico--danger" title="Delete" aria-label="Delete" @click="confirmId = f.id">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                    </button>
                  </span>
                </li>
              </ul>
              <div v-else class="empty">
                <p v-if="q">No files match “{{ q }}”.</p>
                <p v-else>Nothing here yet — drop files above to send them to CiteMed.</p>
              </div>
            </div>
          </template>

          <p v-else class="fs-placeholder">Select a request or your files to get started.</p>
        </section>

        <Transition name="pane"><FilePreviewPane v-if="preview" :src="preview.src" :name="preview.name" @close="preview = null" /></Transition>
      </div>

      <!-- toast -->
      <Transition name="toast">
        <div v-if="toast" class="toast" role="status">{{ toast }}</div>
      </Transition>

      <!-- delete confirm -->
      <div v-if="confirmId" class="scrim" @click="confirmId = null">
        <div class="dialog" role="dialog" aria-modal="true" @click.stop>
          <p class="dialog-title">Delete this file?</p>
          <p class="dialog-body">It will be removed and CiteMed staff will no longer have access to it.</p>
          <div class="dialog-actions">
            <button class="btn-ghost" @click="confirmId = null">Cancel</button>
            <button class="btn-danger" @click="doDelete">Delete</button>
          </div>
        </div>
      </div>
    </template>
  </AppShell>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import AppShell from '@/components/layout/AppShell.vue'
import FileUploader from '@/components/files/FileUploader.vue'
import FilePreviewPane from '@/components/files/FilePreviewPane.vue'
import { useFilesStore } from '@/stores/files'

const store = useFilesStore()
const q = ref('')
const confirmId = ref(null)
const editingId = ref(null)
const editName = ref('')
const renameInput = ref(null)
const toast = ref('')
const flash = ref(new Set())
const preview = ref(null)  // { id, src, name }

function previewable(name) { return /\.(pdf|png|jpe?g|gif|webp)$/i.test(name) }
function openPreview(f) {
  if (preview.value?.id === f.id) { preview.value = null; return }  // toggle
  preview.value = { id: f.id, src: `/api/files/${f.id}/view`, name: f.original_name }
}

onMounted(store.load)

const active = computed(() => store.activeBucket)
const uploadLabel = computed(() => (active.value?.kind === 'request' ? 'this request' : ''))
const filtered = computed(() => {
  if (!active.value) return []
  const t = q.value.toLowerCase().trim()
  return t ? active.value.files.filter((f) => f.original_name.toLowerCase().includes(t)) : active.value.files
})

/* Status: quiet dot + label. Color reserved for action/urgency only. */
// Customer-facing request status, derived from what's actually happened
// (not the raw admin 'open' flag) so it never goes stale.
function reqState(b) {
  if (b.status === 'complete') return ['Complete', 'success']
  if (!b.files.length) return ['Awaiting your upload', 'warning']
  if (b.files.some((f) => f.review_status === 'revision')) return ['Action needed', 'danger']
  if (b.files.every((f) => f.review_status === 'approved')) return ['Approved', 'success']
  return ['Awaiting review', 'warning']  // files uploaded, not yet approved/revised
}
function statusLabel(b) { return reqState(b)[0] }
function statusTone(b) { return reqState(b)[1] }
function duePill(b) {
  if (!b.due_at || b.status === 'complete') return null
  const days = Math.ceil((new Date(b.due_at) - Date.now()) / 86400000)
  if (days < 0) return { label: 'Overdue', tone: 'over' }
  if (days === 0) return { label: 'Due today', tone: 'soon' }
  if (days <= 3) return { label: `Due ${days}d`, tone: 'soon' }
  return { label: `Due ${days}d`, tone: 'ok' }
}

async function onUploaded(names) {
  toast.value = names.length === 1 ? `Uploaded ${names[0]}` : `Uploaded ${names.length} files`
  setTimeout(() => (toast.value = ''), 2200)
  names.forEach((n) => flash.value.add(n))
  setTimeout(() => { names.forEach((n) => flash.value.delete(n)) }, 1800)
}

async function startRename(f) {
  editingId.value = f.id
  editName.value = f.original_name
  await nextTick()
  const el = Array.isArray(renameInput.value) ? renameInput.value[0] : renameInput.value
  el?.focus(); el?.select()
}
function cancelRename() { editingId.value = null; editName.value = '' }
async function saveRename(f) {
  if (editingId.value !== f.id) return
  const name = editName.value.trim()
  editingId.value = null
  if (name && name !== f.original_name) await store.rename(f.id, name)
}
async function doDelete() {
  const id = confirmId.value
  confirmId.value = null
  await store.remove(id)
}

function fmtSize(b) {
  if (!b) return '—'
  const u = ['B', 'KB', 'MB', 'GB']; let i = 0
  while (b >= 1024 && i < 3) { b /= 1024; i++ }
  return `${b.toFixed(i ? 1 : 0)} ${u[i]}`
}
function relDate(d) {
  const days = Math.floor((Date.now() - new Date(d).getTime()) / 86400000)
  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 7) return `${days} days ago`
  return new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}
function shortDate(d) { return new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) }
function reviewLabel(s) { return { pending: 'Awaiting review', review: 'In review', approved: 'Approved', revision: 'Needs revision' }[s] || '' }
function checklistReceived(b) { return (b.checklist || []).filter((c) => c.linked_file).length }
function checklistPct(b) {
  const total = (b.checklist || []).length
  return total ? Math.round(checklistReceived(b) / total * 100) : 0
}
function ext(name) {
  const dot = name.lastIndexOf('.')
  return dot === -1 ? 'FILE' : name.slice(dot + 1).toUpperCase().slice(0, 4)
}
function cat(name) {
  const e = (name.split('.').pop() || '').toLowerCase()
  if (['pdf'].includes(e)) return 'pdf'
  if (['doc', 'docx', 'rtf', 'txt'].includes(e)) return 'doc'
  if (['xls', 'xlsx', 'csv'].includes(e)) return 'sheet'
  if (['png', 'jpg', 'jpeg', 'gif'].includes(e)) return 'img'
  if (['zip'].includes(e)) return 'zip'
  return 'other'
}
</script>

<style scoped>
.fs {
  display: flex;
  gap: 28px;
  align-items: flex-start;
  max-width: 1120px;
  margin: 0 auto;
  padding: clamp(1.25rem, 3vw, 2rem);
}
.fs.has-preview { max-width: 1320px; }
.fs-side { flex: 0 0 272px; }
.fs-main { flex: 1 1 auto; min-width: 0; }
.fs :deep(.pvp) { flex: 0 0 clamp(340px, 42%, 600px); }
@media (max-width: 1100px) { .fs.has-preview .fs-side { display: none; } }
@media (max-width: 840px) { .fs { flex-wrap: wrap; } .fs-side { flex-basis: 100%; } }

/* Pane reveal: width + fade together, eased out */
.pane-enter-active, .pane-leave-active { transition: max-width 0.34s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.3s ease, transform 0.34s cubic-bezier(0.4, 0, 0.2, 1); overflow: hidden; }
.pane-enter-from, .pane-leave-to { max-width: 0; opacity: 0; transform: translateX(18px); }
.pane-enter-to, .pane-leave-from { max-width: 640px; }
@media (prefers-reduced-motion: reduce) {
  .pane-enter-active, .pane-leave-active { transition: none; }
  .pane-enter-from, .pane-leave-to { max-width: 640px; transform: none; }
}
.row.row-active { border-color: var(--brand-accent); background: color-mix(in srgb, var(--brand-accent) 6%, var(--card)); }
.ico--on { background: var(--accent); color: var(--primary); }

/* ── Sidebar ── */
.fs-group { margin-bottom: 1.5rem; }
.fs-group-title {
  font-family: var(--font-ui);
  font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.07em;
  font-weight: 700; color: var(--muted-foreground); margin-bottom: 0.6rem;
}
.fs-group-empty { font-size: 0.83rem; color: var(--muted-foreground); }
.b-card {
  width: 100%; text-align: left; display: flex; flex-direction: column; gap: 0.45rem;
  padding: 0.7rem 0.8rem; margin-bottom: 0.4rem;
  border: 1px solid var(--border); border-radius: var(--radius-md);
  background: var(--card); cursor: pointer;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}
.b-card:hover { border-color: color-mix(in srgb, var(--brand-accent) 45%, var(--border)); }
.b-card.is-active {
  border-color: var(--brand-accent);
  background: color-mix(in srgb, var(--brand-accent) 7%, var(--card));
}
.b-title { font-size: 0.9rem; font-weight: 600; color: var(--foreground); line-height: 1.3; }
.b-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 0.6rem; }

.status { display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.72rem; font-weight: 600; color: var(--muted-foreground); }
.status .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.status--success { color: var(--success); }
.status--warning { color: var(--warning); }
.status--info { color: var(--info); }
.status--danger { color: var(--destructive); }
.status--muted { color: var(--muted-foreground); }

.due { font-size: 0.72rem; font-weight: 550; color: var(--muted-foreground); }
.due--soon { color: var(--warning); font-weight: 650; }
.due--over { color: var(--destructive); font-weight: 650; }

/* ── Detail ── */
.fs-main { min-width: 0; }
.fs-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; }
.fs-head h1 { font-family: var(--font-ui); font-size: 1.5rem; font-weight: 700; letter-spacing: -0.01em; color: var(--foreground); }
.refresh-btn { flex-shrink: 0; display: inline-flex; align-items: center; gap: 6px; height: 34px; padding: 0 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--card); color: var(--muted-foreground); font: inherit; font-size: 0.82rem; font-weight: 600; cursor: pointer; transition: color 0.15s, border-color 0.15s, background 0.15s; }
.refresh-btn svg { width: 15px; height: 15px; }
.refresh-btn:hover { color: var(--brand-accent); border-color: var(--brand-accent); }
.refresh-btn:disabled { opacity: 0.6; cursor: default; }
.refresh-btn.is-spinning svg { animation: rspin 0.7s linear infinite; }
@keyframes rspin { to { transform: rotate(360deg); } }

.fs-group-head { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; margin-bottom: 0.6rem; }
.fs-group-head .fs-group-title { margin-bottom: 0; }
.refresh-mini { display: inline-flex; align-items: center; gap: 4px; background: none; border: none; color: var(--muted-foreground); font: inherit; font-size: 0.68rem; font-weight: 600; cursor: pointer; padding: 2px 4px; border-radius: 6px; }
.refresh-mini svg { width: 12px; height: 12px; }
.refresh-mini:hover { color: var(--brand-accent); }
.refresh-mini:disabled { opacity: 0.6; cursor: default; }
.refresh-mini.is-spinning svg { animation: rspin 0.7s linear infinite; }
@media (prefers-reduced-motion: reduce) { .refresh-btn.is-spinning svg, .refresh-mini.is-spinning svg { animation: none; } }
.fs-submeta { color: var(--muted-foreground); font-size: 0.85rem; margin-top: 0.25rem; }
.fs-due.due--over { color: var(--destructive); font-weight: 600; }
.fs-due.due--soon { color: var(--muted-foreground); font-weight: 600; }
.fs-desc {
  margin: 1rem 0 1.25rem;
  padding: 0.8rem 1rem;
  border: 1px solid var(--border);
  border-left: 3px solid var(--brand-accent);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--brand-accent) 5%, var(--card));
  color: var(--foreground); font-size: 0.9rem; line-height: 1.55;
}
.fs-placeholder { color: var(--muted-foreground); padding: 3rem 0; text-align: center; }

/* Requested-documents checklist (read-only for customer) */
.fs-check { border: 1px solid var(--border); border-radius: var(--radius-md); padding: 0.85rem 1rem; margin: 1rem 0 1.25rem; background: var(--card); }
.fs-check-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem; }
.fs-check-label { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; color: var(--muted-foreground); }
.fs-check-count { font-size: 0.78rem; color: var(--muted-foreground); }
.fs-check-bar { height: 5px; border-radius: 999px; background: var(--secondary); overflow: hidden; margin-bottom: 0.6rem; }
.fs-check-bar div { height: 100%; background: var(--success); transition: width 0.3s ease; }
.fs-check-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.3rem; }
.fs-check-list li { display: flex; align-items: center; gap: 0.5rem; font-size: 0.86rem; color: var(--foreground); }
.fs-check-dot { width: 9px; height: 9px; border-radius: 50%; border: 1.5px solid var(--input); flex-shrink: 0; }
.fs-check-dot.on { background: var(--success); border-color: var(--success); }
.fs-check-recv { margin-left: auto; font-size: 0.68rem; font-weight: 700; color: var(--success); }

/* Review status badge + note (customer) — colour carries the state */
.rv-badge { display: inline-block; margin-left: 0.4rem; font-size: 0.66rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.02em; padding: 0.05rem 0.4rem; border-radius: 999px; color: var(--muted-foreground); background: var(--secondary); }
.rv-badge--pending { color: var(--warning); background: color-mix(in srgb, var(--warning) 16%, transparent); }
.rv-badge--review { color: var(--info); background: color-mix(in srgb, var(--info) 14%, transparent); }
.rv-badge--approved { color: var(--success); background: color-mix(in srgb, var(--success) 14%, transparent); }
.rv-badge--revision { color: var(--destructive); background: color-mix(in srgb, var(--destructive) 14%, transparent); }
.rv-note { font-size: 0.76rem; color: var(--destructive); margin-top: 0.15rem; }

/* ── File list ── */
.files { margin-top: 1.5rem; }
.files-bar { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem; }
.files-count { font-size: 0.78rem; font-weight: 600; color: var(--muted-foreground); }
.files-search {
  margin-left: auto; width: 100%; max-width: 240px;
  padding: 0.4rem 0.7rem; border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--card); color: var(--foreground); font-size: 0.85rem;
}
.files-search:focus-visible { outline: 2px solid var(--ring); outline-offset: 1px; }

.rows { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.4rem; }
.row {
  display: grid; grid-template-columns: 40px 1fr auto;
  align-items: center; gap: 0.85rem;
  padding: 0.6rem 0.7rem;
  border: 1px solid var(--border); border-radius: var(--radius-md);
  background: var(--card);
  transition: border-color 0.15s ease, background-color 0.6s ease;
}
.row:hover { border-color: color-mix(in srgb, var(--brand-accent) 35%, var(--border)); }
.row.flash { animation: flash 1.6s ease; }
@keyframes flash {
  0% { background: color-mix(in srgb, var(--brand-accent) 16%, var(--card)); border-color: var(--brand-accent); }
  100% { background: var(--card); }
}

.tile {
  /* Uniform, calm tile — the extension label carries the file type, not color.
     Color is reserved for states that need attention, never for decoration. */
  width: 40px; height: 40px; display: grid; place-items: center;
  border-radius: var(--radius-sm);
  font-size: 0.58rem; font-weight: 700; letter-spacing: 0.02em;
  background: var(--accent); color: var(--accent-foreground);
}

.row-main { min-width: 0; display: flex; flex-direction: column; gap: 0.15rem; }
.row-name { font-size: 0.9rem; font-weight: 550; color: var(--foreground); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row-sub { font-size: 0.76rem; color: var(--muted-foreground); }
.rename { font: inherit; font-size: 0.9rem; padding: 0.2rem 0.4rem; border: 1px solid var(--brand-accent); border-radius: 6px; background: var(--card); color: var(--foreground); width: 100%; max-width: 340px; }

.row-actions { display: flex; gap: 0.15rem; opacity: 0; transition: opacity 0.12s ease; }
.row:hover .row-actions, .row:focus-within .row-actions { opacity: 1; }
@media (hover: none) { .row-actions { opacity: 1; } }
.ico { width: 30px; height: 30px; display: grid; place-items: center; border: none; background: none; color: var(--muted-foreground); border-radius: 7px; cursor: pointer; }
.ico svg { width: 15px; height: 15px; }
.ico:hover { background: var(--secondary); color: var(--foreground); }
.ico--danger:hover { background: color-mix(in srgb, var(--destructive) 14%, transparent); color: var(--destructive); }

.empty { padding: 2rem; text-align: center; color: var(--muted-foreground); font-size: 0.9rem; border: 1px dashed var(--border); border-radius: var(--radius-md); }

/* ── Skeletons ── */
.skeleton-head, .skeleton-drop, .skeleton-row {
  border-radius: var(--radius-md);
  background: linear-gradient(90deg, var(--muted) 25%, var(--secondary) 37%, var(--muted) 63%);
  background-size: 400% 100%;
  animation: shimmer 1.4s ease infinite;
}
.skeleton-head { height: 28px; width: 40%; margin-bottom: 1.25rem; }
.skeleton-drop { height: 120px; margin-bottom: 1.5rem; }
.skeleton-row { height: 54px; margin-bottom: 0.4rem; }
@keyframes shimmer { 0% { background-position: 100% 0; } 100% { background-position: 0 0; } }

/* ── Toast ── */
.toast {
  position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
  background: var(--primary); color: var(--primary-foreground);
  padding: 0.6rem 1.1rem; border-radius: 999px; font-size: 0.85rem; font-weight: 500;
  box-shadow: 0 10px 30px rgba(0,0,0,0.22); z-index: 1100;
}
.toast-enter-active, .toast-leave-active { transition: opacity 0.2s ease, transform 0.2s ease; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translate(-50%, 12px); }

/* ── Delete dialog ── */
.scrim { position: fixed; inset: 0; z-index: 1000; background: rgba(0,0,0,0.42); display: flex; align-items: center; justify-content: center; padding: 1rem; }
.dialog { background: var(--popover); color: var(--popover-foreground); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 1.4rem; max-width: 380px; width: 100%; box-shadow: 0 20px 50px rgba(0,0,0,0.28); }
.dialog-title { font-weight: 650; color: var(--foreground); }
.dialog-body { color: var(--muted-foreground); font-size: 0.88rem; margin-top: 0.35rem; }
.dialog-actions { display: flex; justify-content: flex-end; gap: 0.6rem; margin-top: 1.25rem; }
.btn-ghost { background: none; border: 1px solid var(--border); color: var(--foreground); border-radius: var(--radius-sm); padding: 0.45rem 0.9rem; cursor: pointer; font: inherit; }
.btn-danger { background: var(--destructive); color: #fff; border: none; border-radius: var(--radius-sm); padding: 0.45rem 0.9rem; cursor: pointer; font: inherit; }

@media (prefers-reduced-motion: reduce) {
  .row, .row.flash, .skeleton-head, .skeleton-drop, .skeleton-row, .toast-enter-active, .toast-leave-active, .row-actions { animation: none; transition: none; }
}
</style>
