<template>
  <CommandDialog :open="open" @update:open="$emit('update:open', $event)">
    <!-- Custom search input — same pattern as DocSearch home page -->
    <div class="flex h-12 items-center gap-2.5 border-b px-4">
      <svg class="size-4 shrink-0 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
      </svg>
      <input
        ref="searchInputRef"
        v-model="query"
        type="text"
        placeholder="Type to search documentation..."
        class="flex h-11 w-full bg-transparent py-3 text-[15px] outline-hidden placeholder:text-muted-foreground/50"
        @input="onInput"
      />
      <div v-if="loading" class="shrink-0">
        <div class="w-4 h-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
      </div>
    </div>

    <div class="max-h-[360px] overflow-y-auto">
      <!-- Initial state -->
      <div v-if="!hasSearched" class="py-10 text-center">
        <div class="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-3">
          <svg class="w-5 h-5 text-primary/70" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.292m0-14.25v14.25" />
          </svg>
        </div>
        <p class="text-sm text-muted-foreground">Search across all documentation</p>
        <p class="text-xs text-muted-foreground mt-1">Start typing to find pages</p>
      </div>

      <!-- Results -->
      <div v-if="results.length" class="py-1">
        <div class="px-4 py-1.5 text-xs font-semibold text-muted-foreground">Pages</div>
        <button
          v-for="r in results"
          :key="r.slug"
          @click="navigate(r.slug)"
          class="flex items-center gap-3 w-full px-4 py-2.5 text-left hover:bg-accent transition-colors cursor-pointer"
        >
          <div class="w-8 h-8 rounded-lg bg-muted flex items-center justify-center shrink-0">
            <svg class="h-3.5 w-3.5 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
              <path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
            </svg>
          </div>
          <div class="flex-1 min-w-0">
            <span class="block truncate font-medium text-sm">{{ r.title }}</span>
            <span v-if="r.section" class="block text-xs text-primary/70 truncate mt-0.5">{{ r.section }}</span>
            <span v-if="r.snippet" class="block text-[11px] text-muted-foreground truncate mt-0.5">{{ r.snippet }}</span>
          </div>
        </button>
      </div>

      <!-- No results -->
      <div v-else-if="hasSearched && !loading" class="py-10 text-center">
        <div class="w-12 h-12 rounded-full bg-muted flex items-center justify-center mx-auto mb-3">
          <svg class="w-5 h-5 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
          </svg>
        </div>
        <p class="text-sm font-medium text-muted-foreground">No results found</p>
        <p class="text-xs text-muted-foreground mt-1">Try a different search term</p>
      </div>
    </div>

    <!-- Footer -->
    <div class="flex items-center justify-between border-t px-4 py-2.5 text-[11px] text-muted-foreground">
      <div class="flex items-center gap-3">
        <span class="inline-flex items-center gap-1">
          <kbd class="inline-flex h-[18px] min-w-[18px] items-center justify-center rounded border bg-muted px-1 font-mono text-[10px]">&crarr;</kbd>
          <span class="ml-0.5">open</span>
        </span>
      </div>
      <span class="inline-flex items-center gap-1">
        <kbd class="inline-flex h-[18px] min-w-[18px] items-center justify-center rounded border bg-muted px-1 font-mono text-[10px]">esc</kbd>
        <span class="ml-0.5">close</span>
      </span>
    </div>
  </CommandDialog>
</template>

<script setup>
import { ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useDocsStore } from '@/stores/docs.js'
import { useDebouncedSearch } from '@/lib/useDebounce.js'
import { CommandDialog } from '@/components/ui/command'

const props = defineProps({ open: Boolean })
const emit = defineEmits(['update:open'])
const store = useDocsStore()
const router = useRouter()
const searchInputRef = ref(null)

const query = ref('')

const { results, loading, hasSearched, search: doSearch, reset } = useDebouncedSearch(async (q) => {
  await store.search(q)
  return store.searchResults
}, 150)

function onInput() {
  doSearch(query.value)
}

watch(() => props.open, (isOpen) => {
  if (isOpen) {
    reset()
    query.value = ''
    nextTick(() => {
      searchInputRef.value?.focus()
    })
  }
})

function navigate(slug) {
  emit('update:open', false)
  const q = query.value.trim()
  router.push({
    name: 'doc-page',
    params: { slug },
    query: q ? { q } : undefined
  })
}

function onKey(e) {
  if (e.key === 'Escape' && props.open) {
    e.preventDefault()
    e.stopPropagation()
    emit('update:open', false)
  }
}

onMounted(() => document.addEventListener('keydown', onKey, true))
onBeforeUnmount(() => document.removeEventListener('keydown', onKey, true))
</script>
