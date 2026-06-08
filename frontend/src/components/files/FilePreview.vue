<template>
  <Transition name="preview">
    <div v-if="src" class="pv-scrim" @click="$emit('close')">
      <div class="pv" role="dialog" aria-modal="true" :aria-label="`Preview ${name}`" @click.stop>
        <header class="pv-head">
          <span class="pv-name" :title="name">{{ name }}</span>
          <span class="pv-actions">
            <a :href="src" target="_blank" rel="noopener" class="pv-btn" title="Open in new tab">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
            </a>
            <button class="pv-btn" aria-label="Close preview" @click="$emit('close')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 18 18 6M6 6l12 12"/></svg>
            </button>
          </span>
        </header>
        <div class="pv-body">
          <img v-if="isImage" :src="src" :alt="name" class="pv-img" />
          <iframe v-else :src="src" :title="name" class="pv-frame" />
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({
  src: { type: String, default: null },
  name: { type: String, default: '' },
})
defineEmits(['close'])
const isImage = computed(() => /\.(png|jpe?g|gif|webp)$/i.test(props.name))
</script>

<style scoped>
.pv-scrim {
  position: fixed; inset: 0; z-index: 1200;
  background: rgba(0, 0, 0, 0.55);
  display: flex; align-items: center; justify-content: center;
  padding: clamp(0.75rem, 3vw, 2.5rem);
}
.pv {
  display: flex; flex-direction: column;
  width: min(960px, 100%); height: min(85vh, 100%);
  background: var(--card); border: 1px solid var(--border);
  border-radius: var(--radius-lg); overflow: hidden;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.4);
}
.pv-head {
  display: flex; align-items: center; gap: 1rem;
  padding: 0.6rem 0.9rem; border-bottom: 1px solid var(--border);
  background: var(--card);
}
.pv-name { font-size: 0.9rem; font-weight: 600; color: var(--foreground); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pv-actions { margin-left: auto; display: flex; gap: 0.25rem; }
.pv-btn {
  display: grid; place-items: center; width: 32px; height: 32px;
  border: none; background: none; color: var(--muted-foreground);
  border-radius: 7px; cursor: pointer;
}
.pv-btn svg { width: 17px; height: 17px; }
.pv-btn:hover { background: var(--secondary); color: var(--foreground); }
.pv-body { flex: 1; min-height: 0; background: var(--muted); display: flex; align-items: center; justify-content: center; }
.pv-frame { width: 100%; height: 100%; border: none; background: #fff; }
.pv-img { max-width: 100%; max-height: 100%; object-fit: contain; }

.preview-enter-active, .preview-leave-active { transition: opacity 0.18s ease; }
.preview-enter-from, .preview-leave-to { opacity: 0; }
@media (prefers-reduced-motion: reduce) { .preview-enter-active, .preview-leave-active { transition: none; } }
</style>
