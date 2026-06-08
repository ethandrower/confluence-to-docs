<template>
  <div
    class="dropzone"
    :class="{ dragging, busy: active.length }"
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

    <span class="dz-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <polyline points="17 8 12 3 7 8" />
        <line x1="12" y1="3" x2="12" y2="15" />
      </svg>
    </span>
    <p class="dz-title"><strong>Drop files</strong> to upload<span v-if="label"> to {{ label }}</span></p>
    <p class="dz-sub">or click to browse · PDF, Office, CSV, RIS/ENW/NBIB/XML, images, zip</p>

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
import { ref, reactive } from 'vue'
import { useFilesStore } from '@/stores/files'

const props = defineProps({
  bucketId: { type: Number, default: null },
  label: { type: String, default: '' },
})
const emit = defineEmits(['uploaded'])

const store = useFilesStore()
const input = ref(null)
const dragging = ref(false)
const active = ref([])

function open() {
  input.value?.click()
}

async function handle(fileList) {
  const names = []
  for (const file of Array.from(fileList)) {
    const entry = reactive({ name: file.name, pct: 0, error: '' })
    active.value.push(entry)
    try {
      await store.upload(file, props.bucketId, (p) => (entry.pct = p))
      entry.pct = 1
      names.push(file.name)
    } catch (e) {
      entry.error = e.message || 'Failed'
    }
  }
  if (names.length) emit('uploaded', names)
  // Clear finished rows after a beat; keep failures pinned.
  setTimeout(() => {
    active.value = active.value.filter((a) => a.error)
  }, 1600)
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
  border-radius: 12px;
  background: var(--accent);
  color: var(--primary);
  margin-bottom: 0.25rem;
}
.dz-icon svg { width: 22px; height: 22px; }
.dz-title { font-size: 0.95rem; color: var(--foreground); }
.dz-title strong { font-weight: 650; }
.dz-sub { font-size: 0.76rem; color: var(--muted-foreground); }

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
