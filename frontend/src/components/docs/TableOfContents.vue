<template>
  <div v-if="headings.length" class="toc">
    <p class="toc-label">On this page</p>
    <ul class="toc-list">
      <li
        v-for="h in headings"
        :key="h.id"
        class="toc-item"
        :class="`toc-h${h.level}`"
      >
        <a :href="`#${h.id}`" class="toc-link">{{ h.text }}</a>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ html: String })

const headings = computed(() => {
  if (!props.html || typeof document === 'undefined') return []
  const div = document.createElement('div')
  div.innerHTML = props.html
  return [...div.querySelectorAll('h2, h3')].map(h => ({
    id: h.id || h.textContent.toLowerCase().replace(/\s+/g, '-').replace(/[^\w-]/g, ''),
    text: h.textContent,
    level: parseInt(h.tagName[1])
  }))
})
</script>

<style scoped>
.toc { font-size: 0.8rem; }
.toc-label { font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.05em; font-size: 0.7rem; margin: 0 0 0.5rem; }
.toc-list { list-style: none; margin: 0; padding: 0; }
.toc-item { margin-bottom: 2px; }
.toc-h3 { padding-left: 0.75rem; }
.toc-link { color: var(--text-secondary); text-decoration: none; line-height: 1.5; display: block; padding: 2px 0; }
.toc-link:hover { color: var(--accent); }
</style>
