<template>
  <div
    class="dropzone"
    :class="{ dragging, busy }"
    role="button"
    tabindex="0"
    :aria-label="`Upload files${label ? ' to ' + label : ''}`"
    @dragover.prevent="dragging = true"
    @dragleave.prevent="dragging = false"
    @drop.prevent="onDrop"
    @click="open"
    @keydown.enter="open"
    @keydown.space.prevent="open"
  >
    <input ref="input" type="file" multiple hidden @change="onPick" />
    <!-- webkitdirectory is a separate input on purpose: one input cannot offer
         both "pick files" and "pick a folder", and browsers show a different
         picker for each. -->
    <input ref="dirInput" type="file" multiple webkitdirectory hidden @change="onPick" />

    <span class="dz-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <polyline points="17 8 12 3 7 8" />
        <line x1="12" y1="3" x2="12" y2="15" />
      </svg>
    </span>
    <p class="dz-title"><strong>Drop files</strong> to upload<span v-if="label"> to {{ label }}</span></p>
    <p class="dz-sub">or click to browse · PDF, Office, CSV, RIS/ENW/NBIB/XML, images, zip</p>
    <button type="button" class="dz-folder" @click.stop="openFolder">
      Upload a folder <span class="dz-folder-note">(keeps its structure)</span>
    </button>

    <p v-if="skipped.length" class="dz-skipped" @click.stop>
      Skipped {{ skipped.length }} unsupported {{ skipped.length === 1 ? 'file' : 'files' }} —
      <span class="dz-skip-names">{{ skipped.slice(0, 4).join(', ') }}<span v-if="skipped.length > 4"> and {{ skipped.length - 4 }} more</span></span>
    </p>

    <p v-if="pausedFor" class="dz-paused" @click.stop>
      Upload limit reached — resuming in {{ pausedFor }}s<span v-if="pending"> · {{ pending }} waiting</span>
    </p>

    <ul v-if="active.length" class="dz-progress" @click.stop>
      <li v-for="(a, i) in active" :key="i" :class="{ failed: a.error, done: a.pct >= 1 && !a.error }">
        <span class="dz-name">{{ a.name }}</span>
        <span class="dz-bar"><span class="dz-fill" :style="{ width: Math.round(a.pct * 100) + '%' }" /></span>
        <span class="dz-state">
          <template v-if="a.error">{{ a.error }}</template>
          <template v-else-if="a.pct >= 1">Done</template>
          <template v-else>{{ Math.round(a.pct * 100) }}%</template>
        </span>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useFilesStore } from '@/stores/files'
import { createGate, runPool, RateLimited, UPLOAD_CONCURRENCY } from '@/lib/uploadQueue'
import {
  filesFromDrop, filesFromInput, partitionByExtension, pathsIn, mergeIfSameFolder,
} from '@/lib/folderDrop'

const props = defineProps({
  bucketId: { type: Number, default: null },
  label: { type: String, default: '' },
})
const emit = defineEmits(['uploaded'])

// How many times one file will sit out a rate-limit pause before giving up.
// The window is an hour, so this is generous on purpose: a big batch should
// drain slowly, not fail.
const MAX_WAITS = 60

const store = useFilesStore()
const input = ref(null)
const dragging = ref(false)
const active = ref([])
const pausedFor = ref(0)
const busy = ref(false)
const dirInput = ref(null)
const skipped = ref([])

const pending = computed(() => active.value.filter((a) => !a.error && a.pct < 1).length)

// Where a dropped tree's top-level folders should be created.
//
// Only a folder can contain a folder. The active bucket is usually "General
// uploads" or a document request, and neither may parent one — a tree dropped
// while looking at those belongs at the top level of the customer's own tree.
// Loose files still land in whatever bucket is open, which is why this is
// separate from props.bucketId rather than a replacement for it.
const folderRoot = computed(() => {
  const b = store.buckets.find((x) => x.id === props.bucketId)
  return b && b.kind === 'folder' ? b.id : null
})

function open() {
  input.value?.click()
}
function openFolder() {
  dirInput.value?.click()
}

/** Upload one file, sitting out any rate-limit pause rather than failing. */
async function runOne(gate, file, entry, bucketId) {
  for (let waits = 0; ; waits++) {
    await gate.pass()
    try {
      await store.upload(file, bucketId, (p) => (entry.pct = p))
      entry.pct = 1
      return file.name
    } catch (e) {
      if (e instanceof RateLimited && waits < MAX_WAITS) {
        // Everyone waits on the same barrier — N workers each backing off
        // independently would each earn a fresh 429.
        entry.pct = 0
        gate.pause(e.retryAfterMs)
        continue
      }
      entry.error = e.message || 'Failed'
      throw e
    }
  }
}

async function handle(items) {
  if (!items.length) return

  // Report what we won't take up front, rather than as a wall of red rows the
  // customer can do nothing about. The server is still the authority.
  const { ok, skipped: rejected } = partitionByExtension(items, store.allowedExt)
  skipped.value = rejected
  if (!ok.length) return

  busy.value = true

  // Re-uploading the folder you're standing in merges rather than nesting.
  const here = store.buckets.find((b) => b.id === folderRoot.value) || null
  const batch = mergeIfSameFolder(ok, here?.title)
  const reupload = batch !== ok

  let folders
  try {
    // Every folder in the batch, resolved in one call before any upload starts.
    folders = await store.ensurePaths(pathsIn(batch), folderRoot.value)
  } catch (e) {
    busy.value = false
    skipped.value = []
    active.value.push(reactive({ name: 'Folders', pct: 0, error: e.message || 'Failed' }))
    return
  }

  const entries = batch.map((it) => {
    const entry = reactive({ name: it.path ? `${it.path}/${it.file.name}` : it.file.name, pct: 0, error: '' })
    active.value.push(entry)
    return entry
  })

  const gate = createGate((secs) => (pausedFor.value = secs))
  const results = await runPool(
    batch,
    (it, i) => runOne(gate, it.file, entries[i], folders[it.path] ?? props.bucketId),
    UPLOAD_CONCURRENCY,
  )
  busy.value = false

  // One refresh for the whole batch. Reloading per file meant a 200-file drop
  // refetched the entire folder tree 200 times.
  await store.load()

  const names = results.filter((r) => r.ok).map((r) => r.value)

  // Where a folder upload actually landed, so the view can follow it there.
  // The tree was always built correctly, but the customer stayed parked on
  // whatever they had open — the files appeared to vanish and the only clue
  // was a new row in the sidebar. Resolved against the just-reloaded buckets
  // rather than the ensure-path response, because the server may have reused
  // an existing folder and matches titles case-insensitively.
  const roots = [...new Set(pathsIn(batch).map((p) => p.split('/')[0]).filter(Boolean))]
  let landed = null
  if (names.length) {
    if (reupload) {
      // Re-upload merged into the folder already on screen. Re-found by id
      // rather than reusing `here`, which came from the pre-refresh list.
      landed = store.buckets.find((b) => b.id === folderRoot.value) || null
    } else if (roots.length === 1) {
      const want = roots[0].toLowerCase()
      landed = store.buckets.find(
        (b) => b.kind === 'folder'
          && (b.parent ?? null) === folderRoot.value
          && (b.title || '').toLowerCase() === want,
      ) || null
    }
  }

  if (names.length) emit('uploaded', names, landed ? landed.id : null, landed ? landed.title : '')

  setTimeout(() => {
    active.value = active.value.filter((a) => a.error)
  }, 1600)
}

async function onDrop(e) {
  dragging.value = false
  // Must be awaited: filesFromDrop walks the directory tree asynchronously,
  // but it grabs every entry handle synchronously first (see folderDrop.js).
  handle(await filesFromDrop(e.dataTransfer))
}
function onPick(e) {
  handle(filesFromInput(e.target.files))
  e.target.value = ''
}
</script>

<style scoped>
.dropzone {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 0.35rem;
  padding: 1.75rem 1.5rem;
  border: 1.5px dashed var(--input);
  border-radius: var(--radius-lg);
  background:
    linear-gradient(var(--card), var(--card)) padding-box,
    radial-gradient(120% 140% at 50% -20%, color-mix(in srgb, var(--brand-accent) 7%, transparent), transparent 60%) border-box;
  color: var(--muted-foreground);
  cursor: pointer;
  transition: border-color 0.18s ease, background-color 0.18s ease, transform 0.06s ease;
}
.dropzone:hover {
  border-color: color-mix(in srgb, var(--brand-accent) 55%, var(--input));
}
.dropzone.dragging {
  border-color: var(--brand-accent);
  border-style: solid;
  background: color-mix(in srgb, var(--brand-accent) 8%, var(--card));
}
.dropzone:active { transform: translateY(1px); }
.dropzone:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }

.dz-icon {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border-radius: var(--radius-lg);
  background: var(--accent);
  color: var(--primary);
  margin-bottom: 0.25rem;
}
.dz-icon svg { width: 22px; height: 22px; }
.dz-title { font-size: 0.95rem; color: var(--foreground); }
.dz-title strong { font-weight: 650; }
.dz-sub { font-size: 0.76rem; color: var(--muted-foreground); }

.dz-folder {
  margin-top: 0.5rem;
  padding: 0.25rem 0.6rem;
  border: 1px solid var(--input);
  border-radius: var(--radius);
  background: var(--card);
  color: var(--foreground);
  font-family: var(--font-ui);
  font-size: 0.76rem;
  cursor: pointer;
}
.dz-folder:hover { border-color: var(--brand-accent); }
.dz-folder-note { color: var(--muted-foreground); }

.dz-skipped {
  width: 100%;
  margin-top: 0.75rem;
  padding: 0.4rem 0.6rem;
  border-radius: var(--radius);
  background: var(--secondary);
  color: var(--muted-foreground);
  font-size: 0.76rem;
  text-align: left;
  cursor: default;
}
.dz-skip-names { color: var(--foreground); }

.dz-paused {
  width: 100%;
  margin-top: 0.75rem;
  padding: 0.4rem 0.6rem;
  border-radius: var(--radius);
  background: color-mix(in srgb, var(--destructive) 10%, var(--card));
  color: var(--foreground);
  font-size: 0.76rem;
  cursor: default;
}

.dz-progress {
  width: 100%;
  list-style: none;
  margin: 0.9rem 0 0;
  padding: 0;
  display: grid;
  gap: 0.4rem;
  text-align: left;
  cursor: default;
}
.dz-progress li {
  display: grid;
  grid-template-columns: 1fr 90px auto;
  align-items: center;
  gap: 0.5rem 0.65rem;
  font-size: 0.78rem;
  color: var(--foreground);
}
.dz-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dz-bar { height: 5px; border-radius: 999px; background: var(--secondary); overflow: hidden; }
.dz-fill { display: block; height: 100%; background: var(--brand-accent); transition: width 0.2s ease; }
.dz-state { font-size: 0.72rem; color: var(--muted-foreground); white-space: nowrap; }
.done .dz-state { color: var(--primary); }
.failed .dz-fill { background: var(--destructive); }
.failed .dz-state { color: var(--destructive); }

@media (prefers-reduced-motion: reduce) {
  .dropzone, .dz-fill { transition: none; }
}
</style>
