<template>
  <nav class="doc-sidebar">
    <div v-if="store.loading" class="sidebar-loading">Loading...</div>
    <div v-else-if="store.error" class="sidebar-error">{{ store.error }}</div>
    <ul v-else class="page-tree">
      <SidebarNode v-for="page in store.tree" :key="page.id" :page="page" :depth="0" />
    </ul>
  </nav>
</template>

<script setup>
import { useDocsStore } from '@/stores/docs.js'
import SidebarNode from './SidebarNode.vue'

const store = useDocsStore()
</script>

<style scoped>
.doc-sidebar { width: 100%; }
.page-tree { list-style: none; margin: 0; padding: 0; }
.sidebar-loading, .sidebar-error { padding: 1rem; font-size: 0.875rem; color: var(--text-secondary); }
</style>
