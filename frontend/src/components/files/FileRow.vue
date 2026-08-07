<template>
  <!-- One client file in the agent view. Extracted so the request section and
       the folder browser can't drift apart — they show the same thing. -->
  <span class="fr-file">
    <span class="fr-name">
      <span v-if="file.seen === false" class="fr-dot" title="Not looked at yet" aria-label="New" />
      {{ file.original_name }}
    </span>
    <span class="fr-sub">{{ fmtSize(file.size_bytes) }} · {{ fmtDate(file.uploaded_at) }} · {{ file.uploaded_by_name || '—' }}</span>
  </span>

  <span class="row-acts">
    <button
      class="act act--seen"
      :class="file.seen && 'act--on'"
      :title="file.seen ? 'Mark as not looked at' : 'Mark as seen'"
      :aria-label="file.seen ? 'Mark as not looked at' : 'Mark as seen'"
      @click="$emit('seen', file, !file.seen)"
    >
      <svg v-if="file.seen" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
      <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/></svg>
    </button>
    <button
      v-if="previewable(file.original_name)"
      class="act"
      :class="previewId === file.id && 'act--on'"
      :title="previewId === file.id ? 'Close preview' : 'Preview'"
      aria-label="Preview"
      @click="$emit('preview', file.id, file.original_name)"
    >
      <svg v-if="previewId === file.id" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 18 18 6M6 6l12 12"/></svg>
      <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8Z"/><circle cx="12" cy="12" r="3"/></svg>
    </button>
    <a class="act" :href="`/api/admin/files/${file.id}/download`" title="Download" aria-label="Download">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
    </a>
    <button class="act act--comment" title="Internal comments" aria-label="Comments" @click="$emit('comments', file.id, file.original_name)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
      <span v-if="file.comment_count" class="act-badge">{{ file.comment_count }}</span>
    </button>
  </span>
</template>

<script setup>
defineProps({
  file: { type: Object, required: true },
  previewId: { type: [Number, null, Boolean], default: null },
})
defineEmits(['preview', 'comments', 'seen'])

function previewable(name) { return /\.(pdf|png|jpe?g|gif|webp)$/i.test(name) }

function fmtSize(b) {
  if (!b && b !== 0) return '—'
  if (b < 1024) return `${b} B`
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / 1048576).toFixed(1)} MB`
}

function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}
</script>

<style scoped>
.fr-file { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.fr-name {
  display: flex; align-items: center; gap: 7px;
  font-family: var(--font-ui); font-size: 0.88rem; color: var(--foreground);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
/* The whole notification model in one element: a file nobody has opened. */
.fr-dot {
  width: 7px; height: 7px; flex-shrink: 0;
  border-radius: 999px; background: var(--primary);
}
.fr-sub { font-size: 0.76rem; color: var(--muted-foreground); }

.row-acts { display: flex; align-items: center; gap: 2px; flex-shrink: 0; }
.act {
  display: grid; place-items: center; position: relative;
  width: 30px; height: 30px;
  border: 0; border-radius: 7px; background: none; cursor: pointer;
  color: var(--muted-foreground); text-decoration: none;
}
.act:hover { background: var(--accent); color: var(--foreground); }
.act svg { width: 16px; height: 16px; }
.act--on { color: var(--primary); }
.act--seen.act--on { color: var(--success); }
.act-badge {
  position: absolute; top: 2px; right: 2px;
  min-width: 14px; height: 14px; padding: 0 3px;
  border-radius: 999px; background: var(--primary); color: var(--primary-foreground);
  font-size: 0.6rem; line-height: 14px; text-align: center;
}
</style>
