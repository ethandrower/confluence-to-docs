<template>
  <AppShell hide-sidebar>
    <template #content>
      <div class="fs" :class="{ 'has-preview': preview }">
        <!-- Sidebar -->
        <aside
          class="fs-side"
          aria-label="File buckets"
          @dragover="onSideDragOver"
          @drop="dragKind = null"
        >
          <!-- Only the requests that genuinely block progress get this slot.
               An empty section is worse than no section: a standing "Requests
               from CiteMed" header teaches the customer to scroll past it. -->
          <div v-if="store.requiredRequests.length || store.doneRequests.length" class="fs-group">
            <div class="fs-group-head">
              <h2 class="fs-group-title">Needed from you</h2>
              <button class="refresh-mini" :class="store.loading && 'is-spinning'" :disabled="store.loading" title="Refresh" aria-label="Refresh requests" @click="store.load()">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v5h-5"/></svg>
                Refresh
              </button>
            </div>
            <button
              v-for="b in store.requiredRequests"
              :key="b.id"
              class="b-card b-card--required"
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

            <!-- A satisfied mandatory document stays here rather than moving in
                 with the optional ones. It has stopped being a task, so it
                 loses the card, but the customer still gets to see that the
                 thing they were chased for actually landed. -->
            <button
              v-for="b in store.doneRequests"
              :key="b.id"
              class="fs-req-done"
              :class="{ 'is-active': b.id === store.activeBucketId }"
              @click="store.select(b.id)"
            >
              <svg class="fs-req-tick" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
              <span class="fs-req-title">{{ b.title }}</span>
            </button>
          </div>

          <!-- Optional asks get their own heading rather than a twisty. They
               were previously behind a collapsed "Also shared with CiteMed",
               which is where content goes to never be read. A peer section
               keeps them visible while the absence of a card keeps them from
               reading as a blocker. -->
          <div v-if="store.optionalRequests.length" class="fs-group">
            <h2 class="fs-group-title fs-group-title--quiet">Nice to have</h2>
            <ul class="fs-opt-list">
              <li v-for="b in store.optionalRequests" :key="b.id">
                <button
                  class="fs-opt-item"
                  :class="{ 'is-active': b.id === store.activeBucketId }"
                  @click="store.select(b.id)"
                >
                  <span class="fs-opt-dot" />
                  <span class="fs-opt-title">{{ b.title }}</span>
                  <span v-if="b.files.length" class="fs-opt-n">{{ b.files.length }}</span>
                </button>
              </li>
            </ul>
          </div>

          <div class="fs-group">
            <div class="fs-group-head">
              <h2 class="fs-group-title">Your files</h2>
              <button class="refresh-mini" title="New folder" aria-label="New top-level folder" @click="promptFolder(null)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/><path d="M12 11v5"/><path d="M9.5 13.5h5"/></svg>
                New folder
              </button>
            </div>

            <!-- Only the top-level input lives out here; subfolder inputs
                 render inside the tree, under the folder being added to. -->
            <div v-if="creatingIn === null" class="fs-newfolder">
              <input
                ref="newFolderInput"
                v-model="newFolderName"
                class="fs-newfolder-input"
                placeholder="Folder name"
                @keydown.enter="submitFolder"
                @keydown.esc="cancelCreate"
              />
              <div class="fs-newfolder-actions">
                <button class="refresh-mini" @click="submitFolder">Create</button>
                <button class="refresh-mini" @click="cancelCreate">Cancel</button>
              </div>
            </div>

            <!-- The home the portal opens on, and a view rather than a bucket:
                 it lists every file wherever it lives, which is what makes
                 filing them possible at all. Always present — unlike "Not in a
                 folder", it must not vanish when empty, because it is also the
                 landing place for a customer who has nothing yet. -->
            <button
              class="fs-all"
              :class="{ 'is-active': isAll }"
              @click="store.select(ALL_FILES_ID)"
            >
              <svg class="fs-all-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>
              <span class="fs-all-title">All files</span>
              <span v-if="store.totalFileCount" class="fs-all-n">{{ store.totalFileCount }}</span>
            </button>

            <ul v-if="store.folderTree.length" class="fs-tree">
              <FolderNode
                v-for="node in store.folderTree"
                :key="node.id"
                :node="node"
                :active-id="store.activeBucketId"
                :creating-in="creatingIn"
                @select="store.select($event)"
                @drop-files="onDropFiles"
                @move-folder="onMoveFolder"
                @add-child="promptFolder"
                @create-submit="submitChildFolder"
                @create-cancel="cancelCreate"
              />
            </ul>
            <p v-else-if="!store.loading" class="fs-group-empty">
              No folders yet — make one to organise your uploads.
            </p>

            <!-- Files that aren't in a folder. Shown as a peer row rather than
                 the card it used to be, and hidden entirely when empty, so a
                 new customer sees folders rather than a bucket named after our
                 database. It reappears mid-drag because it is also how a file
                 gets back out of a folder without being deleted. -->
            <button
              v-if="store.generalBucket && (store.generalBucket.files.length || dragKind === 'file')"
              class="fs-loose"
              :class="{
                'is-active': store.generalBucket.id === store.activeBucketId,
                'is-drop': dropTarget === store.generalBucket.id,
              }"
              @click="store.select(store.generalBucket.id)"
              @dragover.prevent="dropTarget = store.generalBucket.id"
              @dragleave="dropTarget = null"
              @drop.prevent="onDropOn(store.generalBucket.id, $event)"
            >
              <svg class="fs-loose-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/></svg>
              <span class="fs-loose-title">Not in a folder</span>
              <span v-if="store.generalBucket.files.length" class="fs-loose-n">{{ store.generalBucket.files.length }}</span>
            </button>

            <!-- Only rendered while a folder is actually being dragged. A
                 permanent "drop here" strip is dead furniture the other 99% of
                 the time, and it was competing with real folders for weight. -->
            <div
              v-if="dragKind === 'folder'"
              class="fs-root-drop"
              :class="{ 'is-drop': dropTarget === 'root' }"
              @dragover.prevent="dropTarget = 'root'"
              @dragleave="dropTarget = null"
              @drop.prevent="onDropRoot"
            >Drop here to move to the top level</div>

            <p v-if="folderError" class="fs-folder-err">{{ folderError }}</p>

          </div>
        </aside>

        <!-- Detail -->
        <section class="fs-main">
          <template v-if="store.loading && !store.buckets.length">
            <div class="skeleton-head" />
            <div class="skeleton-drop" />
            <div class="skeleton-row" v-for="n in 3" :key="n" />
          </template>

          <template v-else-if="isAll || active">
            <header class="fs-head">
              <div>
                <template v-if="isAll">
                  <h1>All files</h1>
                  <p class="fs-submeta">
                    Everything you’ve uploaded, wherever it lives ·
                    {{ store.totalFileCount }} file{{ store.totalFileCount === 1 ? '' : 's' }}
                  </p>
                </template>
                <nav v-if="!isAll && breadcrumb.length > 1" class="fs-crumbs" aria-label="Folder path">
                  <template v-for="(c, i) in breadcrumb.slice(0, -1)" :key="c.id">
                    <button class="fs-crumb" @click="store.select(c.id)">{{ c.title }}</button>
                    <span class="fs-crumb-sep" aria-hidden="true">/</span>
                  </template>
                </nav>
                <input
                  v-if="!isAll && renamingFolder && active.kind === 'folder'"
                  ref="renameFolderInput"
                  v-model="renameFolderName"
                  class="fs-rename-h1"
                  @keydown.enter="submitFolderRename(active)"
                  @keydown.esc="renamingFolder = false"
                  @blur="submitFolderRename(active)"
                />
                <h1 v-else-if="!isAll">{{ active.title }}</h1>
                <p v-if="!isAll && active.kind === 'folder'" class="fs-submeta">
                  <!-- Both numbers, because "0 files" in a folder that holds
                       forty in subfolders reads as an empty folder. -->
                  {{ active.files.length }} file{{ active.files.length === 1 ? '' : 's' }} here
                  <span v-if="deepCount > active.files.length"> · {{ deepCount }} including subfolders</span>
                </p>
                <p v-if="!isAll && active.kind === 'request'" class="fs-submeta">
                  <span v-if="active.requested_by_name">Requested by {{ active.requested_by_name }}</span>
                  <span v-if="active.created_at"> · {{ relDate(active.created_at) }}</span>
                  <span v-if="duePill(active)" class="fs-due" :class="`due--${duePill(active).tone}`"> · Due {{ shortDate(active.due_at) }}</span>
                </p>
              </div>
              <div class="fs-head-actions">
                <template v-if="!isAll && active.kind === 'folder'">
                  <button class="refresh-btn" @click="promptRename(active)">Rename</button>
                  <button
                    class="refresh-btn"
                    :class="confirmDeleteFolder && 'is-danger'"
                    @click="removeFolder(active)"
                    @blur="confirmDeleteFolder = false"
                  >{{ confirmDeleteFolder ? 'Confirm delete' : 'Delete' }}</button>
                </template>
                <button class="refresh-btn" :class="store.loading && 'is-spinning'" :disabled="store.loading" title="Refresh" aria-label="Refresh" @click="store.load()">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v5h-5"/></svg>
                  {{ store.loading ? 'Refreshing…' : 'Refresh' }}
                </button>
              </div>
            </header>

            <p v-if="!isAll && active.description" class="fs-desc">{{ active.description }}</p>

            <div v-if="!isAll && active.kind === 'request' && active.checklist && active.checklist.length" class="fs-check">
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

            <FileUploader
              :bucket-id="uploadTarget"
              :label="uploadLabel"
              :key="store.activeBucketId"
              @uploaded="onUploaded"
            />

            <div class="files">
              <div class="files-bar">
                <label v-if="rows.length" class="files-checkall" :title="allVisibleSelected ? 'Clear selection' : 'Select all shown'">
                  <input type="checkbox" :checked="allVisibleSelected" @change="toggleAllVisible" />
                </label>
                <span class="files-count">{{ rows.length }} file{{ rows.length === 1 ? '' : 's' }}</span>
                <input v-if="rows.length" v-model="q" class="files-search" type="search" placeholder="Search…" aria-label="Search files" />
              </div>

              <!-- Only present once something is selected: an always-visible
                   toolbar is furniture, and this one carries a destructive-ish
                   verb that shouldn't sit under the cursor by default. -->
              <div v-if="selected.size" class="files-sel">
                <span class="files-sel-n">{{ selected.size }} selected</span>
                <div class="files-sel-move">
                  <button class="refresh-btn" @click="moveOpen = !moveOpen">Move to…</button>
                  <div v-if="moveOpen" class="movemenu-scrim" @click="moveOpen = false" />
                  <ul v-if="moveOpen" class="movemenu">
                    <li v-if="store.generalBucket">
                      <button class="movemenu-item" @click="moveSelectionTo(store.generalBucket.id)">Not in a folder</button>
                    </li>
                    <li v-for="t in moveTargets" :key="t.id">
                      <button
                        class="movemenu-item"
                        :style="{ paddingLeft: 12 + t.depth * 14 + 'px' }"
                        @click="moveSelectionTo(t.id)"
                      >{{ t.title }}</button>
                    </li>
                    <li v-if="!moveTargets.length" class="movemenu-empty">Make a folder first</li>
                  </ul>
                </div>
                <button class="refresh-btn" @click="clearSelection">Clear</button>
              </div>

              <ul v-if="filtered.length" class="rows">
                <li
                  v-for="f in filtered"
                  :key="f.id"
                  class="row"
                  :class="{
                    flash: flash.has(f.original_name),
                    'row-active': preview && preview.id === f.id,
                    'row-sel': selected.has(f.id),
                  }"
                  :draggable="true"
                  @dragstart="onFileDragStart(f, $event)"
                >
                  <label class="row-check" @click.stop>
                    <input
                      type="checkbox"
                      :checked="selected.has(f.id)"
                      :aria-label="`Select ${f.original_name}`"
                      @change="toggleFile(f.id)"
                    />
                  </label>
                  <span class="tile" :data-cat="cat(f.original_name)">{{ ext(f.original_name) }}</span>
                  <div class="row-main">
                    <template v-if="editingId === f.id">
                      <input ref="renameInput" v-model="editName" class="rename" @keydown.enter="saveRename(f)" @keydown.esc="cancelRename" @blur="saveRename(f)" />
                    </template>
                    <span v-else class="row-name" :title="f.original_name">{{ f.original_name }}</span>
                    <!-- No review badge: uploading is just uploading. -->
                    <span class="row-sub">
                      {{ fmtSize(f.size_bytes) }} · {{ relDate(f.uploaded_at) }}
                      <!-- Where it lives. Without this the flat list is forty
                           PDFs with no way to tell what still needs filing. -->
                      <button
                        v-if="isAll"
                        class="row-loc"
                        :class="{ 'row-loc--loose': f.bucketKind === 'general' }"
                        :title="`Go to ${f.location}`"
                        @click.stop="store.select(f.bucketId)"
                      >{{ f.location }}</button>
                    </span>
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
                <p v-else-if="isFirstRun">Welcome! Upload documents for the CiteMed team using the box above, and make folders on the left to organise them. If CiteMed needs something specific from you, it’ll appear under <strong>“Needed from you”</strong>.</p>
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
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import AppShell from '@/components/layout/AppShell.vue'
import FileUploader from '@/components/files/FileUploader.vue'
import FilePreviewPane from '@/components/files/FilePreviewPane.vue'
import FolderNode from '@/components/files/FolderNode.vue'
import { useFilesStore, ALL_FILES_ID } from '@/stores/files'

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

// ── Folders ─────────────────────────────────────────────────────────────
const folderError = ref('')
const dropTarget = ref(null)

const breadcrumb = computed(() =>
  store.activeBucketId ? store.pathTo(store.activeBucketId) : []
)
const deepCount = computed(() =>
  store.activeBucketId ? store.fileCount(store.activeBucketId, true) : 0
)

/** Server messages are the useful ones here ("a folder with that name is
 *  already here"), so surface them verbatim rather than a generic failure. */
async function guard(fn) {
  folderError.value = ''
  try {
    await fn()
  } catch (e) {
    folderError.value = e.message
  }
}

// What kind of thing is currently being dragged, so the sidebar can reveal
// only the drop target that applies. Read from dataTransfer.types rather than
// tracked via events from the tree: during a drag the *values* are protected,
// but the type keys are readable, which is exactly the question being asked
// here — and it means FolderNode doesn't have to report its drag state upward.
const dragKind = ref(null)

function onSideDragOver(e) {
  const types = Array.from(e.dataTransfer?.types || [])
  if (types.includes('application/x-folder-id')) dragKind.value = 'folder'
  else if (types.includes('application/x-file-ids')) dragKind.value = 'file'
}

// dragend fires on the source element, which may be inside the tree or the
// file list, so it's bound at the document rather than on the sidebar. Without
// this a cancelled drag would leave the drop targets showing.
function clearDrag() { dragKind.value = null; dropTarget.value = null }
onMounted(() => {
  document.addEventListener('dragend', clearDrag)
  document.addEventListener('drop', clearDrag)
})
onUnmounted(() => {
  document.removeEventListener('dragend', clearDrag)
  document.removeEventListener('drop', clearDrag)
})

// Inline rather than window.prompt/confirm: a native dialog blocks the whole
// page, can't be styled, and reads as a browser warning rather than part of
// the app.
const creatingIn = ref(undefined)   // undefined = idle, null = top level, id = subfolder
const newFolderName = ref('')
const newFolderInput = ref(null)
const renamingFolder = ref(false)
const renameFolderName = ref('')
const renameFolderInput = ref(null)
const confirmDeleteFolder = ref(false)

function promptFolder(parentId) {
  folderError.value = ''
  creatingIn.value = parentId ?? null
  newFolderName.value = ''
  if (creatingIn.value === null) nextTick(() => newFolderInput.value?.focus())
}

/** Submitted from a node's inline input inside the tree. */
function submitChildFolder({ title, parentId }) {
  guard(async () => {
    const f = await store.createFolder(title, parentId)
    cancelCreate()
    if (f) store.select(f.id)
  })
}

function cancelCreate() {
  creatingIn.value = undefined
  newFolderName.value = ''
}

function submitFolder() {
  const title = newFolderName.value.trim()
  if (!title) return cancelCreate()
  const parentId = creatingIn.value
  guard(async () => {
    const f = await store.createFolder(title, parentId)
    cancelCreate()
    if (f) store.select(f.id)
  })
}

function promptRename(folder) {
  folderError.value = ''
  renameFolderName.value = folder.title
  renamingFolder.value = true
  // Focus AND select: the field is pre-filled with the current name, so
  // without the select you have to clear it by hand before typing.
  nextTick(() => {
    renameFolderInput.value?.focus()
    renameFolderInput.value?.select()
  })
}

function submitFolderRename(folder) {
  const title = renameFolderName.value.trim()
  renamingFolder.value = false
  if (!title || title === folder.title) return
  guard(() => store.renameFolder(folder.id, title))
}

function removeFolder(folder) {
  // Two-step rather than a warning: the API refuses a non-empty folder, so
  // nothing is ever at stake here beyond the empty folder itself.
  if (!confirmDeleteFolder.value) {
    confirmDeleteFolder.value = true
    return
  }
  confirmDeleteFolder.value = false
  guard(() => store.deleteFolder(folder.id))
}

function onFileDragStart(f, e) {
  e.dataTransfer.effectAllowed = 'move'
  // Dragging a row that is part of the selection drags the whole selection.
  // Dragging an unselected row drags only that row and leaves the selection
  // alone — silently retargeting someone's selection to the row they happened
  // to grab is how you move forty files by accident.
  const ids = selected.value.has(f.id) ? selectedIds.value : [f.id]
  e.dataTransfer.setData('application/x-file-ids', JSON.stringify(ids))
}

function onDropFiles({ ids, bucketId }) {
  guard(() => store.moveFiles(ids, bucketId))
}

function onMoveFolder({ id, parentId }) {
  guard(() => store.moveFolder(id, parentId))
}

function onDropOn(bucketId, e) {
  dropTarget.value = null
  const raw = e.dataTransfer.getData('application/x-file-ids')
  if (raw) onDropFiles({ ids: JSON.parse(raw), bucketId })
}

function onDropRoot(e) {
  dropTarget.value = null
  const folderId = e.dataTransfer.getData('application/x-folder-id')
  if (folderId) onMoveFolder({ id: Number(folderId), parentId: null })
}

const active = computed(() => store.activeBucket)
const isAll = computed(() => store.activeBucketId === ALL_FILES_ID)
const uploadLabel = computed(() => (active.value?.kind === 'request' ? 'this request' : ''))
const isFirstRun = computed(() =>
  !store.requests.length && store.buckets.every((b) => !b.files.length)
)

/** Where a plain file drop lands while "All files" is open. That view is not a
 *  bucket and has no id of its own, so unfiled is the honest destination — the
 *  customer files it afterwards, which is the whole point of the view. */
const uploadTarget = computed(() =>
  isAll.value ? store.generalBucket?.id ?? null : active.value?.id ?? null
)

const rows = computed(() => (isAll.value ? store.allFiles : active.value?.files ?? []))
const filtered = computed(() => {
  const t = q.value.toLowerCase().trim()
  return t ? rows.value.filter((f) => f.original_name.toLowerCase().includes(t)) : rows.value
})

// ── Multi-select ────────────────────────────────────────────────────────
const selected = ref(new Set())
const moveOpen = ref(false)

// Moving files you can no longer see is not a feature. Changing view clears
// the selection so "3 selected" always refers to rows on this screen.
watch(() => store.activeBucketId, () => { selected.value = new Set(); moveOpen.value = false })

// A refresh can delete or re-home rows out from under a selection (another
// tab, or staff). Drop ids that no longer exist rather than sending them to
// the move endpoint, which refuses the whole batch if any id misses.
watch(rows, (list) => {
  if (!selected.value.size) return
  const live = new Set(list.map((f) => f.id))
  const next = new Set([...selected.value].filter((id) => live.has(id)))
  if (next.size !== selected.value.size) selected.value = next
})

const selectedIds = computed(() => [...selected.value])
const allVisibleSelected = computed(
  () => filtered.value.length > 0 && filtered.value.every((f) => selected.value.has(f.id))
)
function toggleFile(id) {
  const next = new Set(selected.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selected.value = next
}
function toggleAllVisible() {
  const next = new Set(selected.value)
  if (allVisibleSelected.value) filtered.value.forEach((f) => next.delete(f.id))
  else filtered.value.forEach((f) => next.add(f.id))
  selected.value = next
}
function clearSelection() { selected.value = new Set(); moveOpen.value = false }

/** Folder tree flattened to a list with depth, so the picker keeps its shape. */
function flattenFolders(nodes, depth = 0, out = []) {
  for (const n of nodes) {
    out.push({ id: n.id, title: n.title, depth })
    if (n.children?.length) flattenFolders(n.children, depth + 1, out)
  }
  return out
}
const moveTargets = computed(() => flattenFolders(store.folderTree))

async function moveSelectionTo(bucketId) {
  const n = selectedIds.value.length
  if (!n) return
  moveOpen.value = false
  const where = store.buckets.find((b) => b.id === bucketId)
  await guard(async () => {
    await store.moveFiles(selectedIds.value, bucketId)
    toast.value = `Moved ${n} file${n === 1 ? '' : 's'} to ${where ? where.title : 'Not in a folder'}`
    setTimeout(() => (toast.value = ''), 2200)
  })
  clearSelection()
}

/* Status: quiet dot + label. Color reserved for action/urgency only. */
// Customer-facing request status, derived from what's actually happened
// (not the raw admin 'open' flag) so it never goes stale.
function reqState(b) {
  // Two states the customer can act on, and one they can't. There is no
  // "awaiting review" any more — nothing was ever going to review it, and a
  // request that sits on "awaiting review" forever teaches them to ignore the
  // status entirely. Once they've sent something it's on us, and CiteMed
  // marking the request complete is what closes it.
  if (b.status === 'complete') return ['Complete', 'success']
  if (!b.files.length) return ['Awaiting your upload', 'warning']
  return ['Sent to CiteMed', 'muted']
}
function statusLabel(b) { return reqState(b)[0] }
function statusTone(b) { return reqState(b)[1] }
function duePill(b) {
  if (!b.due_at || b.status === 'complete') return null
  // Once the request is resolved (all approved / complete), the deadline is
  // no longer relevant — hide it.
  if (reqState(b)[1] === 'success') return null
  const days = Math.ceil((new Date(b.due_at) - Date.now()) / 86400000)
  if (days < 0) return { label: 'Overdue', tone: 'over' }
  if (days === 0) return { label: 'Due today', tone: 'soon' }
  if (days <= 3) return { label: `Due ${days}d`, tone: 'soon' }
  return { label: `Due ${days}d`, tone: 'ok' }
}

async function onUploaded(names, folderId = null, folderTitle = '') {
  // A folder upload follows its own result. Staying put would leave the
  // customer looking at a pane that didn't change while their files went
  // somewhere else entirely.
  if (folderId) {
    store.select(folderId)
    toast.value = `Uploaded ${names.length} file${names.length === 1 ? '' : 's'} into ${folderTitle}`
  } else {
    toast.value = names.length === 1 ? `Uploaded ${names[0]}` : `Uploaded ${names.length} files`
  }
  setTimeout(() => (toast.value = ''), 2600)
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

/* ── Folder tree ─────────────────────────────────────────────────────── */
.fs-tree { list-style: none; margin: 0.4rem 0 0; padding: 0; }

/* Nested folders can only be dragged back to the top level by dropping
   somewhere, and the top level has no row of its own to aim at. */
.fs-root-drop {
  margin-top: 0.4rem; padding: 7px 8px;
  border: 1px dashed var(--border); border-radius: 7px;
  font-size: 0.75rem; color: var(--muted-foreground); text-align: center;
}
.fs-root-drop.is-drop {
  border-color: var(--primary); border-style: solid;
  background: color-mix(in srgb, var(--primary) 12%, transparent);
  color: var(--foreground);
}
.fs-folder-err {
  margin-top: 0.5rem; font-size: 0.78rem; color: var(--destructive);
}

.fs-crumbs { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; margin-bottom: 2px; }
.fs-crumb {
  border: 0; background: none; padding: 0; cursor: pointer;
  font-family: var(--font-ui); font-size: 0.78rem; color: var(--muted-foreground);
}
.fs-crumb:hover { color: var(--foreground); text-decoration: underline; }
.fs-crumb-sep { font-size: 0.78rem; color: var(--muted-foreground); }

.fs-head-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; flex-wrap: wrap; justify-content: flex-end; }
.refresh-btn.is-danger { color: var(--destructive); border-color: color-mix(in srgb, var(--destructive) 45%, var(--border)); }

.fs-newfolder {
  margin-top: 0.5rem; padding: 8px;
  border: 1px solid var(--border); border-radius: 8px; background: var(--card);
}
.fs-newfolder-label { display: block; font-size: 0.72rem; color: var(--muted-foreground); margin-bottom: 4px; }
.fs-newfolder-input {
  width: 100%; height: 28px; padding: 0 8px;
  border: 1px solid var(--border); border-radius: 7px;
  background: var(--background); color: var(--foreground);
  font-family: var(--font-ui); font-size: 0.83rem;
}
.fs-newfolder-actions { display: flex; gap: 6px; margin-top: 6px; }

/* A required request is the one thing on this screen the customer must act
   on, so it gets the only accent border in the sidebar. */
.b-card--required { border-color: color-mix(in srgb, var(--warning) 55%, var(--border)); }

/* "Nice to have" — a peer section, but a deliberately quieter heading than
   "Needed from you" so the eye still lands on the blocker first. */
.fs-group-title--quiet { font-weight: 600; opacity: 0.75; }

.fs-opt-list { list-style: none; margin: 0; padding: 0; }
.fs-opt-item {
  display: flex; align-items: center; gap: 8px; width: 100%;
  border: 0; background: none; border-radius: 7px; cursor: pointer;
  padding: 6px 8px;
  font-family: var(--font-ui); font-size: 0.83rem; color: var(--foreground);
  text-align: left;
}
.fs-opt-item:hover { background: color-mix(in srgb, var(--accent) 60%, transparent); }
.fs-opt-item.is-active { background: var(--accent); }
.fs-opt-dot {
  width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0;
  background: var(--muted-foreground); opacity: 0.55;
}
.fs-opt-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fs-opt-n { margin-left: auto; font-size: 0.72rem; color: var(--muted-foreground); font-variant-numeric: tabular-nums; }

/* A required request that's been satisfied: no card, no status, just proof. */
.fs-req-done {
  display: flex; align-items: center; gap: 7px; width: 100%;
  border: 0; background: none; border-radius: 7px; cursor: pointer;
  padding: 6px 8px; margin-top: 2px;
  font-family: var(--font-ui); font-size: 0.83rem; color: var(--muted-foreground);
  text-align: left;
}
.fs-req-done:hover { background: color-mix(in srgb, var(--accent) 60%, transparent); }
.fs-req-done.is-active { background: var(--accent); }
.fs-req-tick { width: 13px; height: 13px; flex-shrink: 0; color: var(--success, var(--muted-foreground)); }
.fs-req-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Unfiled files. Sits below the tree as a peer of the folders, weighted like
   a tree row rather than the card it replaced. */
.fs-loose {
  display: flex; align-items: center; gap: 7px; width: 100%;
  margin-top: 0.45rem; padding: 6px 8px;
  border: 0; border-top: 1px solid var(--border); border-radius: 0 0 7px 7px;
  background: none; cursor: pointer;
  font-family: var(--font-ui); font-size: 0.83rem; color: var(--muted-foreground);
  text-align: left;
}
.fs-loose:hover { background: color-mix(in srgb, var(--accent) 60%, transparent); }
.fs-loose.is-active { background: var(--accent); color: var(--foreground); }
.fs-loose.is-drop {
  border: 1px solid var(--primary); border-radius: 7px;
  background: color-mix(in srgb, var(--primary) 12%, transparent);
  color: var(--foreground);
}
.fs-loose-ico { width: 14px; height: 14px; flex-shrink: 0; }
.fs-loose-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fs-loose-n { margin-left: auto; font-size: 0.72rem; font-variant-numeric: tabular-nums; }

/* "All files" — the home row. Sits above the tree and, unlike "Not in a
   folder", is always present: it is where the portal opens, including for a
   customer who has nothing yet. Weighted a step heavier than a folder so it
   reads as a destination rather than another node. */
.fs-all {
  display: flex; align-items: center; gap: 7px; width: 100%;
  margin-bottom: 0.35rem; padding: 7px 8px;
  border: 1px solid transparent; border-radius: 7px;
  background: none; cursor: pointer;
  font-family: var(--font-ui); font-size: 0.85rem; font-weight: 600;
  color: var(--foreground); text-align: left;
}
.fs-all:hover { background: color-mix(in srgb, var(--accent) 60%, transparent); }
.fs-all.is-active {
  background: var(--accent);
  border-color: color-mix(in srgb, var(--brand-accent) 35%, var(--border));
}
.fs-all-ico { width: 14px; height: 14px; flex-shrink: 0; color: var(--muted-foreground); }
.fs-all-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fs-all-n {
  margin-left: auto; font-size: 0.72rem; font-weight: 500;
  font-variant-numeric: tabular-nums; color: var(--muted-foreground);
}

.fs-rename-h1 {
  width: 100%; max-width: 420px;
  border: 1px solid var(--border); border-radius: 8px;
  padding: 2px 8px; background: var(--background); color: var(--foreground);
  font-family: var(--font-ui); font-size: 1.5rem; font-weight: 700; letter-spacing: -0.01em;
}
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
.refresh-btn { flex-shrink: 0; display: inline-flex; align-items: center; gap: 6px; height: 34px; padding: 0 12px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--card); color: var(--muted-foreground); font: inherit; font-size: 0.82rem; font-weight: 600; cursor: pointer; transition: color 0.15s, border-color 0.15s, background 0.15s; }
.refresh-btn svg { width: 15px; height: 15px; }
.refresh-btn:hover { color: var(--brand-accent); border-color: var(--brand-accent); }
.refresh-btn:disabled { opacity: 0.6; cursor: default; }
.refresh-btn.is-spinning svg { animation: rspin 0.7s linear infinite; }
@keyframes rspin { to { transform: rotate(360deg); } }

.fs-group-head { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; margin-bottom: 0.6rem; }
.fs-group-head .fs-group-title { margin-bottom: 0; }
.refresh-mini { display: inline-flex; align-items: center; gap: 4px; background: none; border: none; color: var(--muted-foreground); font: inherit; font-size: 0.68rem; font-weight: 600; cursor: pointer; padding: 2px 4px; border-radius: var(--radius-sm); }
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
  /* Leading column is the select checkbox. */
  display: grid; grid-template-columns: auto 40px 1fr auto;
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

.row-check { display: grid; place-items: center; cursor: pointer; }
.row-check input,
.files-checkall input {
  width: 15px; height: 15px; cursor: pointer; accent-color: var(--brand-accent);
}
.row.row-sel {
  border-color: var(--brand-accent);
  background: color-mix(in srgb, var(--brand-accent) 7%, var(--card));
}

/* Where a file lives, shown only in the All files view. A button, not a chip,
   because its job is to take you there. */
.row-loc {
  margin-left: 0.4rem; padding: 1px 7px;
  border: 1px solid var(--border); border-radius: 999px;
  background: var(--card); color: var(--muted-foreground);
  font: inherit; font-size: 0.7rem; cursor: pointer;
  max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.row-loc:hover { border-color: var(--brand-accent); color: var(--foreground); }
.row-loc--loose { font-style: italic; }

.files-checkall { display: grid; place-items: center; cursor: pointer; }
.files-sel {
  display: flex; align-items: center; gap: 0.6rem;
  margin-bottom: 0.5rem; padding: 0.45rem 0.6rem;
  border: 1px solid color-mix(in srgb, var(--brand-accent) 35%, var(--border));
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--brand-accent) 7%, var(--card));
}
.files-sel-n { font-size: 0.8rem; font-weight: 600; color: var(--foreground); }
.files-sel-move { position: relative; margin-left: auto; }

/* Full-viewport catcher so a click anywhere dismisses the menu. */
.movemenu-scrim { position: fixed; inset: 0; z-index: 20; }
.movemenu {
  position: absolute; right: 0; top: calc(100% + 4px); z-index: 21;
  min-width: 190px; max-height: 280px; overflow-y: auto;
  list-style: none; margin: 0; padding: 4px;
  border: 1px solid var(--border); border-radius: var(--radius-md);
  background: var(--card); box-shadow: 0 10px 30px rgb(0 0 0 / 0.14);
}
.movemenu-item {
  display: block; width: 100%; padding: 6px 10px;
  border: 0; border-radius: var(--radius-sm); background: none;
  font: inherit; font-size: 0.82rem; color: var(--foreground);
  text-align: left; cursor: pointer;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.movemenu-item:hover { background: var(--accent); }
.movemenu-empty { padding: 6px 10px; font-size: 0.78rem; color: var(--muted-foreground); }
.rename { font: inherit; font-size: 0.9rem; padding: 0.2rem 0.4rem; border: 1px solid var(--brand-accent); border-radius: var(--radius-sm); background: var(--card); color: var(--foreground); width: 100%; max-width: 340px; }

.row-actions { display: flex; gap: 0.15rem; opacity: 0; transition: opacity 0.12s ease; }
.row:hover .row-actions, .row:focus-within .row-actions { opacity: 1; }
@media (hover: none) { .row-actions { opacity: 1; } }
.ico { width: 30px; height: 30px; display: grid; place-items: center; border: none; background: none; color: var(--muted-foreground); border-radius: var(--radius-sm); cursor: pointer; }
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
