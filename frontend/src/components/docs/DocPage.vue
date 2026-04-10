<template>
  <div class="doc-page">
    <div v-if="store.loading" class="loading-state">Loading...</div>
    <div v-else-if="store.error" class="error-state">{{ store.error }}</div>
    <template v-else-if="store.currentPage">
      <Breadcrumbs :crumbs="store.currentPage.breadcrumbs" />
      <div class="doc-layout">
        <div class="doc-body">
          <h1 class="doc-title">{{ store.currentPage.title }}</h1>
          <article
            class="confluence-content"
            v-html="store.currentPage.rendered_html"
          />
        </div>
        <aside class="toc-aside">
          <TableOfContents :html="store.currentPage.rendered_html" />
        </aside>
      </div>
    </template>
  </div>
</template>

<script setup>
import { watch, nextTick, onMounted } from 'vue'
import { useDocsStore } from '@/stores/docs.js'
import Breadcrumbs from '@/components/layout/Breadcrumbs.vue'
import TableOfContents from './TableOfContents.vue'

const props = defineProps({ slug: String })
const store = useDocsStore()

async function loadPage() {
  await store.fetchPage(props.slug)
  await nextTick()
  // Syntax highlight code blocks
  if (typeof window !== 'undefined' && window.Prism) {
    window.Prism.highlightAll()
  }
}

watch(() => props.slug, loadPage, { immediate: true })
</script>

<style scoped>
.doc-page { width: 100%; }
.loading-state, .error-state { padding: 2rem; color: var(--text-secondary); }
.error-state { color: #ef4444; }
.doc-layout { display: flex; gap: 2rem; align-items: flex-start; }
.doc-body { flex: 1; min-width: 0; }
.doc-title { font-size: 2rem; font-weight: 700; margin: 0 0 1.5rem; color: var(--text-primary); }
.toc-aside { width: 200px; min-width: 200px; position: sticky; top: 80px; }

@media (max-width: 1024px) {
  .toc-aside { display: none; }
}
</style>
