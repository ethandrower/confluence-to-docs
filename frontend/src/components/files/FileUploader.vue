<template>
  <div
    class="uploader"
    :class="{ dragging }"
    role="button"
    tabindex="0"
    aria-label="Upload files — drag and drop or click to browse"
    @dragover.prevent="dragging = true"
    @dragleave.prevent="dragging = false"
    @drop.prevent="onDrop"
    @click="open"
    @keydown.enter="open"
    @keydown.space.prevent="open"
  >
    <input ref="input" type="file" multiple hidden @change="onPick" />
    <svg class="uploader-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
      <path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
    </svg>
    <p class="uploader-title">Drag files here or click to browse</p>
    <p class="uploader-sub">PDF, Office docs, CSV, reference-library exports (RIS/ENW/NBIB/XML), images, zip</p>

    <ul v-if="active.length" class="uploader-progress" @click.stop>
      <li v-for="(a, i) in active" :key="i" :class="{ failed: a.error }">
        <span class="name">{{ a.name }}</span>
        <span class="bar"><span class="fill" :style="{ width: Math.round(a.pct * 100) + '%' }" /></span>
        <span v-if="a.error" class="err">{{ a.error }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useFilesStore } from '@/stores/files'

const props = defineProps({ bucketId: { type: Number, default: null } })
const store = useFilesStore()
const input = ref(null)
const dragging = ref(false)
const active = ref([])

function open() {
  input.value?.click()
}

async function handle(fileList) {
  for (const file of Array.from(fileList)) {
    const entry = { name: file.name, pct: 0, error: '' }
    active.value.push(entry)
    try {
      await store.upload(file, props.bucketId, (p) => (entry.pct = p))
      entry.pct = 1
    } catch (e) {
      entry.error = e.message || 'Failed'
    }
  }
  // Clear successful rows shortly after; keep failures visible.
  setTimeout(() => {
    active.value = active.value.filter((a) => a.error)
  }, 1400)
}

function onDrop(e) {
  dragging.value = false
  handle(e.dataTransfer.files)
}
function onPick(e) {
  handle(e.target.files)
  e.target.value = ''
}
</script>

<style scoped>
.uploader {
  border: 2px dashed var(--border);
  border-radius: 12px;
  padding: 2rem 1.5rem;
  text-align: center;
  cursor: pointer;
  background: var(--card);
  transition: border-color 0.15s, background 0.15s;
}
.uploader.dragging,
.uploader:hover {
  border-color: var(--brand-accent);
  background: color-mix(in srgb, var(--brand-accent) 6%, var(--card));
}
.uploader:focus-visible {
  outline: 2px solid var(--brand-accent);
  outline-offset: 2px;
}
.uploader-icon {
  width: 32px;
  height: 32px;
  margin: 0 auto 0.5rem;
  color: var(--brand-accent);
}
.uploader-title {
  font-weight: 600;
  color: var(--foreground);
}
.uploader-sub {
  font-size: 0.78rem;
  color: var(--muted-foreground);
  margin-top: 0.25rem;
}
.uploader-progress {
  list-style: none;
  margin: 1.25rem 0 0;
  padding: 0;
  text-align: left;
  display: grid;
  gap: 0.5rem;
  cursor: default;
}
.uploader-progress li {
  display: grid;
  grid-template-columns: 1fr 120px;
  gap: 0.5rem 0.75rem;
  align-items: center;
  font-size: 0.8rem;
  color: var(--foreground);
}
.name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bar {
  height: 6px;
  border-radius: 999px;
  background: var(--muted);
  overflow: hidden;
}
.fill {
  display: block;
  height: 100%;
  background: var(--brand-accent);
  transition: width 0.2s ease;
}
.failed .fill {
  background: #b42318;
}
.err {
  grid-column: 1 / -1;
  color: #b42318;
  font-size: 0.75rem;
}
</style>
