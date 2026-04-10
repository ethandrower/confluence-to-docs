<template>
  <div class="search-bar" ref="containerRef">
    <input
      type="text"
      v-model="query"
      @input="onInput"
      @focus="showResults = true"
      @keydown.escape="showResults = false"
      placeholder="Search docs..."
      class="search-input"
      autocomplete="off"
    />
    <div v-if="showResults && results.length" class="search-dropdown">
      <RouterLink
        v-for="r in results"
        :key="r.slug"
        :to="{ name: 'doc-page', params: { slug: r.slug } }"
        class="search-result"
        @click="showResults = false"
      >
        {{ r.title }}
      </RouterLink>
    </div>
    <div v-if="showResults && query && !results.length" class="search-dropdown search-empty">
      No results for "{{ query }}"
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useDocsStore } from '@/stores/docs.js'

const store = useDocsStore()
const query = ref('')
const showResults = ref(false)
const results = ref([])
const containerRef = ref(null)

let debounceTimer = null
function onInput() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(async () => {
    if (query.value.trim()) {
      await store.search(query.value)
      results.value = store.searchResults
      showResults.value = true
    } else {
      results.value = []
    }
  }, 200)
}

function handleClickOutside(e) {
  if (containerRef.value && !containerRef.value.contains(e.target)) {
    showResults.value = false
  }
}

onMounted(() => document.addEventListener('click', handleClickOutside))
onBeforeUnmount(() => document.removeEventListener('click', handleClickOutside))
</script>

<style scoped>
.search-bar { position: relative; }
.search-input {
  width: 100%;
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.875rem;
  background: var(--surface-1);
  color: var(--text-primary);
  outline: none;
}
.search-input:focus { border-color: var(--accent); background: white; }
.search-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  background: white;
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.1);
  z-index: 500;
  max-height: 320px;
  overflow-y: auto;
}
.search-result {
  display: block;
  padding: 8px 12px;
  font-size: 0.875rem;
  color: var(--text-primary);
  text-decoration: none;
  border-bottom: 1px solid var(--border);
}
.search-result:last-child { border-bottom: none; }
.search-result:hover { background: var(--surface-1); color: var(--accent); }
.search-empty { padding: 12px; font-size: 0.875rem; color: var(--text-secondary); }
</style>
