<template>
  <aside class="pvp">
    <header class="pvp-head">
      <span class="pvp-name" :title="name">{{ name }}</span>
      <span class="pvp-actions">
        <a :href="src" target="_blank" rel="noopener" class="pvp-btn" title="Open in new tab">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
        </a>
        <button class="pvp-btn" aria-label="Close preview" @click="$emit('close')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 18 18 6M6 6l12 12"/></svg>
        </button>
      </span>
    </header>
    <div class="pvp-body">
      <img v-if="isImage" :src="src" :alt="name" class="pvp-img" />
      <iframe v-else :src="src" :title="name" class="pvp-frame" />
    </div>
  </aside>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({
  src: { type: String, required: true },
  name: { type: String, default: '' },
})
defineEmits(['close'])
const isImage = computed(() => /\.(png|jpe?g|gif|webp)$/i.test(props.name))
</script>

<style scoped>
.pvp {
  position: sticky;
  top: 16px;
  align-self: start;
  display: flex;
  flex-direction: column;
  height: calc(100vh - 96px);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: var(--card);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}
.pvp-head {
  display: flex; align-items: center; gap: 0.75rem;
  padding: 0.55rem 0.8rem; border-bottom: 1px solid var(--border);
}
.pvp-name { font-size: 0.85rem; font-weight: 600; color: var(--foreground); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pvp-actions { margin-left: auto; display: flex; gap: 0.2rem; }
.pvp-btn { display: grid; place-items: center; width: 30px; height: 30px; border: none; background: none; color: var(--muted-foreground); border-radius: 7px; cursor: pointer; }
.pvp-btn svg { width: 16px; height: 16px; }
.pvp-btn:hover { background: var(--secondary); color: var(--foreground); }
.pvp-body { flex: 1; min-height: 0; background: var(--muted); display: flex; align-items: center; justify-content: center; }
.pvp-frame { width: 100%; height: 100%; border: none; background: #fff; }
.pvp-img { max-width: 100%; max-height: 100%; object-fit: contain; }
</style>
