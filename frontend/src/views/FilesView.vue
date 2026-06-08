<template>
  <AppShell hide-sidebar>
    <template #content>
      <div class="fs-shell">
        <!-- Sidebar: requests + general -->
        <aside class="fs-sidebar" aria-label="File buckets">
          <div class="fs-section">
            <h2 class="fs-section-title">Requests from CiteMed</h2>
            <p v-if="!store.requests.length" class="fs-section-empty">No open requests.</p>
            <button
              v-for="b in store.requests"
              :key="b.id"
              class="req-card"
              :class="{ 'req-card--active': b.id === store.activeBucketId }"
              @click="store.select(b.id)"
            >
              <span class="req-title">{{ b.title }}</span>
              <span class="req-pills">
                <span class="pill" :class="`pill--${b.status}`">{{ statusLabel(b.status) }}</span>
                <span v-if="duePill(b)" class="pill" :class="`pill--due-${duePill(b).tone}`">{{ duePill(b).label }}</span>
              </span>
            </button>
          </div>

          <div class="fs-section">
            <h2 class="fs-section-title">Your files</h2>
            <button
              v-if="store.generalBucket"
              class="req-card"
              :class="{ 'req-card--active': store.generalBucket.id === store.activeBucketId }"
              @click="store.select(store.generalBucket.id)"
            >
              <span class="req-title">{{ store.generalBucket.title }}</span>
              <span class="req-count">{{ store.generalBucket.files.length }}</span>
            </button>
          </div>
        </aside>

        <!-- Detail pane -->
        <section class="fs-detail">
          <template v-if="active">
            <header class="fs-detail-head">
              <div>
                <h1>{{ active.title }}</h1>
                <p v-if="active.kind === 'request'" class="fs-meta">
                  <span v-if="active.requested_by_name">Requested by {{ active.requested_by_name }}</span>
                  <span v-if="active.created_at"> · {{ relDate(active.created_at) }}</span>
                  <span v-if="active.due_at"> · Due {{ shortDate(active.due_at) }}</span>
                </p>
              </div>
            </header>

            <div v-if="active.description" class="fs-desc">{{ active.description }}</div>

            <FileUploader :bucket-id="active.id" :key="active.id" />

            <div class="list-card">
              <div class="list-toolbar">
                <span class="count">{{ active.files.length }} file{{ active.files.length === 1 ? '' : 's' }}</span>
                <input v-model="q" class="search" type="search" placeholder="Search files…" aria-label="Search files" />
              </div>

              <div v-if="filtered.length" class="file-rows">
                <div v-for="f in filtered" :key="f.id" class="file-row">
                  <span class="badge">{{ extBadge(f.original_name) }}</span>
                  <template v-if="editingId === f.id">
                    <input
                      ref="renameInput"
                      v-model="editName"
                      class="rename-input"
                      @keydown.enter="saveRename(f)"
                      @keydown.esc="cancelRename"
                      @blur="saveRename(f)"
                    />
                  </template>
                  <span v-else class="fname" :title="f.original_name">{{ f.original_name }}</span>
                  <span class="meta">{{ fmtSize(f.size_bytes) }}</span>
                  <span class="meta">{{ relDate(f.uploaded_at) }}</span>
                  <span class="row-actions">
                    <a class="icon-btn" :href="store.downloadUrl(f.id)" title="Download" aria-label="Download">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                    </a>
                    <button class="icon-btn" title="Rename" aria-label="Rename" @click="startRename(f)">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 1 1 3 3L7 19l-4 1 1-4Z"/></svg>
                    </button>
                    <button class="icon-btn icon-btn--danger" title="Delete" aria-label="Delete" @click="confirmId = f.id">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                    </button>
                  </span>
                </div>
              </div>
              <div v-else class="empty">
                <p>{{ q ? 'No files match your search.' : 'No files yet — drop files above to send them to CiteMed.' }}</p>
              </div>
            </div>
          </template>
          <p v-else class="fs-placeholder">Select a request or your files to get started.</p>
        </section>
      </div>

      <div v-if="confirmId" class="modal-backdrop" @click="confirmId = null">
        <div class="modal" role="dialog" aria-modal="true" @click.stop>
          <p class="modal-title">Delete this file?</p>
          <p class="modal-body">It will be removed and CiteMed staff will no longer have access to it.</p>
          <div class="modal-actions">
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
import { useFilesStore } from '@/stores/files'

const store = useFilesStore()
const q = ref('')
const confirmId = ref(null)
const editingId = ref(null)
const editName = ref('')
const renameInput = ref(null)

onMounted(store.load)

const active = computed(() => store.activeBucket)
const filtered = computed(() => {
  if (!active.value) return []
  const t = q.value.toLowerCase().trim()
  return t ? active.value.files.filter((f) => f.original_name.toLowerCase().includes(t)) : active.value.files
})

function statusLabel(s) {
  return { open: 'Open', partial: 'Partial', complete: 'Complete', general: '' }[s] || s
}
function duePill(b) {
  if (!b.due_at) return null
  const due = new Date(b.due_at)
  const days = Math.ceil((due - Date.now()) / 86400000)
  const label = days < 0 ? 'Overdue' : days === 0 ? 'Due today' : `Due in ${days}d`
  const tone = days < 0 ? 'over' : days <= 3 ? 'soon' : 'ok'
  return { label, tone }
}

async function startRename(f) {
  editingId.value = f.id
  editName.value = f.original_name
  await nextTick()
  const el = Array.isArray(renameInput.value) ? renameInput.value[0] : renameInput.value
  el?.focus()
  el?.select()
}
function cancelRename() {
  editingId.value = null
  editName.value = ''
}
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
  const u = ['B', 'KB', 'MB', 'GB']
  let i = 0
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
function shortDate(d) {
  return new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
function extBadge(name) {
  const dot = name.lastIndexOf('.')
  return dot === -1 ? 'FILE' : name.slice(dot + 1).toUpperCase().slice(0, 4)
}
</script>

<style scoped>
.fs-shell {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 24px;
  max-width: 1140px;
  margin: 0 auto;
  padding: clamp(1.25rem, 3vw, 2rem);
  align-items: start;
}
@media (max-width: 860px) { .fs-shell { grid-template-columns: 1fr; } }

/* Sidebar */
.fs-section { margin-bottom: 1.5rem; }
.fs-section-title {
  font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em;
  font-weight: 700; color: var(--muted-foreground); margin-bottom: 0.5rem;
}
.fs-section-empty { font-size: 0.85rem; color: var(--muted-foreground); }
.req-card {
  width: 100%; text-align: left; display: flex; flex-direction: column; gap: 0.4rem;
  padding: 0.65rem 0.75rem; margin-bottom: 0.35rem;
  border: 1px solid var(--border); border-radius: 10px;
  background: var(--card); cursor: pointer; transition: border-color 0.15s, background 0.15s;
}
.req-card:hover { border-color: var(--brand-accent); }
.req-card--active { border-color: var(--brand-accent); background: color-mix(in srgb, var(--brand-accent) 8%, var(--card)); }
.req-title { font-size: 0.9rem; font-weight: 600; color: var(--foreground); }
.req-pills { display: flex; flex-wrap: wrap; gap: 0.35rem; }
.req-card .req-count {
  align-self: flex-start; font-size: 0.72rem; font-weight: 600; color: var(--muted-foreground);
  background: var(--muted); border-radius: 999px; padding: 0.05rem 0.5rem;
}
.pill {
  font-size: 0.65rem; font-weight: 700; letter-spacing: 0.02em; text-transform: uppercase;
  padding: 0.1rem 0.45rem; border-radius: 999px;
}
.pill--open { color: #1d4ed8; background: #dbeafe; }
.pill--partial { color: #92400e; background: #fef3c7; }
.pill--complete { color: #166534; background: #dcfce7; }
.pill--due-ok { color: var(--muted-foreground); background: var(--muted); }
.pill--due-soon { color: #92400e; background: #fef3c7; }
.pill--due-over { color: #991b1b; background: #fee2e2; }

/* Detail */
.fs-detail { min-width: 0; }
.fs-detail-head h1 { font-family: 'Archivo Variable', system-ui, sans-serif; font-size: 1.45rem; font-weight: 700; color: var(--foreground); }
.fs-meta { color: var(--muted-foreground); font-size: 0.85rem; margin-top: 0.2rem; }
.fs-desc {
  background: color-mix(in srgb, var(--brand-accent) 6%, var(--card));
  border: 1px solid var(--border); border-left: 3px solid var(--brand-accent);
  border-radius: 8px; padding: 0.75rem 0.9rem; margin: 1rem 0;
  color: var(--foreground); font-size: 0.9rem; line-height: 1.5;
}
.fs-placeholder { color: var(--muted-foreground); padding: 3rem 0; text-align: center; }

.list-card { margin-top: 1.25rem; border: 1px solid var(--border); border-radius: 12px; overflow: hidden; background: var(--card); }
.list-toolbar { display: flex; align-items: center; gap: 0.75rem; padding: 0.6rem 0.9rem; border-bottom: 1px solid var(--border); }
.count { font-size: 0.8rem; color: var(--muted-foreground); }
.search { margin-left: auto; width: 100%; max-width: 260px; padding: 0.4rem 0.65rem; border: 1px solid var(--border); border-radius: 7px; background: var(--card); color: var(--foreground); font-size: 0.85rem; }
.search:focus-visible { outline: 2px solid var(--brand-accent); outline-offset: 1px; }

.file-row {
  display: grid; grid-template-columns: 34px 1fr 90px 110px auto;
  align-items: center; gap: 0.75rem;
  padding: 0.6rem 0.9rem; border-bottom: 1px solid var(--border);
}
.file-row:last-child { border-bottom: none; }
.file-row:hover { background: var(--muted); }
.badge { width: 34px; height: 26px; display: grid; place-items: center; font-size: 0.6rem; font-weight: 700; color: var(--brand-accent); background: color-mix(in srgb, var(--brand-accent) 12%, transparent); border-radius: 6px; }
.fname { font-size: 0.9rem; font-weight: 500; color: var(--foreground); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rename-input { font: inherit; padding: 0.2rem 0.4rem; border: 1px solid var(--brand-accent); border-radius: 6px; background: var(--card); color: var(--foreground); width: 100%; }
.meta { font-size: 0.8rem; color: var(--muted-foreground); white-space: nowrap; }
.row-actions { display: flex; gap: 0.2rem; justify-content: flex-end; }
.icon-btn { width: 28px; height: 28px; display: grid; place-items: center; border: none; background: none; color: var(--muted-foreground); border-radius: 6px; cursor: pointer; }
.icon-btn svg { width: 15px; height: 15px; }
.icon-btn:hover { background: var(--secondary, var(--muted)); color: var(--foreground); }
.icon-btn--danger:hover { background: #fee2e2; color: #b42318; }
.empty { padding: 2rem; text-align: center; color: var(--muted-foreground); font-size: 0.9rem; }

/* Delete modal */
.modal-backdrop { position: fixed; inset: 0; z-index: 1000; background: rgba(0,0,0,0.45); display: flex; align-items: center; justify-content: center; padding: 1rem; }
.modal { background: var(--card); border-radius: 12px; padding: 1.5rem; max-width: 380px; width: 100%; box-shadow: 0 20px 50px rgba(0,0,0,0.3); }
.modal-title { font-weight: 650; color: var(--foreground); }
.modal-body { color: var(--muted-foreground); font-size: 0.9rem; margin-top: 0.35rem; }
.modal-actions { display: flex; justify-content: flex-end; gap: 0.6rem; margin-top: 1.25rem; }
.btn-ghost { background: none; border: 1px solid var(--border); color: var(--foreground); border-radius: 8px; padding: 0.45rem 0.9rem; cursor: pointer; font: inherit; }
.btn-danger { background: #b42318; color: #fff; border: none; border-radius: 8px; padding: 0.45rem 0.9rem; cursor: pointer; font: inherit; }
</style>
