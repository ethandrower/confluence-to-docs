<template>
  <AppShell hide-sidebar>
    <template #content>
  <div class="files-page">
    <header class="files-head">
      <h1>Share Files</h1>
      <p class="sub">
        Upload documents for the CiteMed team — reference libraries, PDFs, and
        related files. Everything here is private to your organization.
      </p>
    </header>

    <FileUploader :bucket-id="generalBucketId" />

    <div v-if="totalFiles" class="search-wrap">
      <input v-model="q" class="search" type="search" placeholder="Search files…" aria-label="Search files" />
    </div>

    <section v-for="b in store.buckets" :key="b.id" class="bucket">
      <div class="bucket-head">
        <h2>{{ b.title }}</h2>
        <span v-if="b.kind === 'request'" class="pill">Requested</span>
      </div>
      <p v-if="b.description" class="bucket-desc">{{ b.description }}</p>

      <table v-if="filtered(b).length" class="file-table">
        <thead>
          <tr><th>Name</th><th class="num">Size</th><th>Uploaded</th><th class="actions-col"></th></tr>
        </thead>
        <tbody>
          <tr v-for="f in filtered(b)" :key="f.id">
            <td class="name-cell">
              <svg class="file-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
              </svg>
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
              <span v-else class="fname">{{ f.original_name }}</span>
            </td>
            <td class="num">{{ fmtSize(f.size_bytes) }}</td>
            <td>{{ fmtDate(f.uploaded_at) }}</td>
            <td class="row-actions">
              <a :href="store.downloadUrl(f.id)">Download</a>
              <button @click="startRename(f)">Rename</button>
              <button class="danger" @click="confirmId = f.id">Delete</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="empty">{{ q ? 'No files match your search.' : 'No files yet.' }}</p>
    </section>

    <div v-if="confirmId" class="modal-backdrop" @click="confirmId = null">
      <div class="modal" role="dialog" aria-modal="true" @click.stop>
        <p class="modal-title">Delete this file?</p>
        <p class="modal-body">It will be removed from your file list.</p>
        <div class="modal-actions">
          <button class="btn-ghost" @click="confirmId = null">Cancel</button>
          <button class="btn-danger" @click="doDelete">Delete</button>
        </div>
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

const generalBucketId = computed(() => store.buckets.find((b) => b.kind === 'general')?.id ?? null)
const totalFiles = computed(() => store.buckets.reduce((n, b) => n + b.files.length, 0))

function filtered(b) {
  const t = q.value.toLowerCase().trim()
  if (!t) return b.files
  return b.files.filter((f) => f.original_name.toLowerCase().includes(t))
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
function fmtDate(d) {
  return new Date(d).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}
</script>

<style scoped>
.files-page {
  max-width: 960px;
  margin: 0 auto;
  padding: clamp(1.25rem, 3vw, 2.5rem);
}
.files-head h1 {
  font-family: 'Archivo Variable', system-ui, sans-serif;
  font-size: 1.6rem;
  font-weight: 700;
  color: var(--foreground);
}
.sub {
  color: var(--muted-foreground);
  margin: 0.35rem 0 1.5rem;
  max-width: 60ch;
}
.search-wrap { margin-top: 1.5rem; }
.search {
  width: 100%;
  max-width: 340px;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--card);
  color: var(--foreground);
}
.search:focus-visible { outline: 2px solid var(--brand-accent); outline-offset: 1px; }

.bucket { margin-top: 2rem; }
.bucket-head { display: flex; align-items: center; gap: 0.6rem; }
.bucket-head h2 { font-size: 1.1rem; font-weight: 650; color: var(--foreground); }
.pill {
  font-size: 0.68rem;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--brand-accent);
  background: color-mix(in srgb, var(--brand-accent) 12%, transparent);
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
}
.bucket-desc { color: var(--muted-foreground); font-size: 0.9rem; margin: 0.25rem 0 0.75rem; }

.file-table { width: 100%; border-collapse: collapse; margin-top: 0.5rem; }
.file-table th, .file-table td {
  text-align: left;
  padding: 0.6rem 0.5rem;
  border-bottom: 1px solid var(--border);
  font-size: 0.9rem;
  color: var(--foreground);
}
.file-table th { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.03em; color: var(--muted-foreground); font-weight: 600; }
.num { text-align: right; white-space: nowrap; }
.actions-col { width: 1%; }
.name-cell { display: flex; align-items: center; gap: 0.5rem; }
.file-icon { width: 18px; height: 18px; color: var(--muted-foreground); flex-shrink: 0; }
.fname { overflow: hidden; text-overflow: ellipsis; }
.rename-input {
  font: inherit;
  padding: 0.2rem 0.4rem;
  border: 1px solid var(--brand-accent);
  border-radius: 6px;
  background: var(--card);
  color: var(--foreground);
  width: 100%;
  max-width: 320px;
}
.row-actions { display: flex; gap: 0.85rem; justify-content: flex-end; white-space: nowrap; }
.row-actions a, .row-actions button {
  background: none; border: none; color: var(--brand-accent);
  cursor: pointer; font: inherit; padding: 0;
}
.row-actions a:hover, .row-actions button:hover { text-decoration: underline; }
.row-actions .danger { color: #b42318; }
.empty { color: var(--muted-foreground); font-size: 0.9rem; padding: 0.75rem 0; }

.modal-backdrop {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0, 0, 0, 0.45);
  display: flex; align-items: center; justify-content: center;
  padding: 1rem;
}
.modal {
  background: var(--card);
  border-radius: 12px;
  padding: 1.5rem;
  max-width: 380px;
  width: 100%;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.3);
}
.modal-title { font-weight: 650; color: var(--foreground); }
.modal-body { color: var(--muted-foreground); font-size: 0.9rem; margin-top: 0.35rem; }
.modal-actions { display: flex; justify-content: flex-end; gap: 0.6rem; margin-top: 1.25rem; }
.btn-ghost {
  background: none; border: 1px solid var(--border); color: var(--foreground);
  border-radius: 8px; padding: 0.45rem 0.9rem; cursor: pointer; font: inherit;
}
.btn-danger {
  background: #b42318; color: #fff; border: none;
  border-radius: 8px; padding: 0.45rem 0.9rem; cursor: pointer; font: inherit;
}
</style>
