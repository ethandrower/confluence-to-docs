<template>
  <div class="doc-search-page">
    <h1>CiteMed Support Documentation</h1>
    <p class="subtitle">Search our documentation or browse topics in the sidebar.</p>
    <div class="search-box">
      <input
        type="text"
        v-model="query"
        @input="onInput"
        placeholder="Search documentation..."
        class="search-input-lg"
        autofocus
      />
    </div>
    <div v-if="results.length" class="search-results">
      <RouterLink
        v-for="r in results"
        :key="r.slug"
        :to="{ name: 'doc-page', params: { slug: r.slug } }"
        class="result-card"
      >
        <strong>{{ r.title }}</strong>
      </RouterLink>
    </div>
    <div v-else-if="query && !loading" class="no-results">
      No results for "{{ query }}"
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useDocsStore } from '@/stores/docs.js'

const store = useDocsStore()
const query = ref('')
const results = ref([])
const loading = ref(false)

let timer = null
async function onInput() {
  clearTimeout(timer)
  timer = setTimeout(async () => {
    loading.value = true
    await store.search(query.value)
    results.value = store.searchResults
    loading.value = false
  }, 200)
}
</script>

<style scoped>
.doc-search-page { max-width: 720px; }
h1 { font-size: 2rem; font-weight: 700; margin-bottom: 0.5rem; }
.subtitle { color: var(--text-secondary); margin-bottom: 2rem; }
.search-input-lg {
  width: 100%;
  padding: 12px 16px;
  font-size: 1rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  outline: none;
  background: white;
}
.search-input-lg:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-light); }
.search-results { margin-top: 1.5rem; display: flex; flex-direction: column; gap: 0.5rem; }
.result-card {
  display: block;
  padding: 12px 16px;
  border: 1px solid var(--border);
  border-radius: 8px;
  text-decoration: none;
  color: var(--text-primary);
  background: white;
}
.result-card:hover { border-color: var(--accent); background: var(--accent-light); }
.no-results { margin-top: 1.5rem; color: var(--text-secondary); }
</style>
