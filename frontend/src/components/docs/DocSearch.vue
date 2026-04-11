<template>
  <div class="px-6 lg:px-10 py-10 max-w-3xl">
    <!-- Hero -->
    <div class="mb-10">
      <div class="flex items-center gap-2.5 mb-3">
        <div class="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
          <svg class="w-4 h-4 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.292m0-14.25v14.25" />
          </svg>
        </div>
        <span class="text-xs font-semibold uppercase tracking-wider text-primary/70">Documentation</span>
      </div>
      <h1 class="text-[1.75rem] font-bold tracking-tight text-foreground leading-tight">
        CiteMed Support Documentation
      </h1>
      <p class="mt-2.5 text-[15px] leading-relaxed text-muted-foreground">
        Find answers, guides, and policies across all CiteMed spaces.
      </p>
    </div>

    <!-- Search -->
    <div class="relative group">
      <div class="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground/40 group-focus-within:text-primary transition-colors" aria-hidden="true">
        <svg class="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
        </svg>
      </div>
      <input
        type="search"
        v-model="query"
        @input="onInput"
        aria-label="Search documentation"
        placeholder="Search documentation..."
        class="w-full h-12 pl-11 pr-4 rounded-xl border border-border/80 bg-card text-[15px] placeholder:text-muted-foreground/35 shadow-sm focus:outline-none focus:ring-2 focus:ring-primary/25 focus:border-primary/30 transition-all"
        autofocus
      />
      <div v-if="loading" class="absolute right-4 top-1/2 -translate-y-1/2">
        <div class="w-4 h-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
      </div>
    </div>

    <!-- Search Results -->
    <div v-if="results.length" class="mt-3 rounded-xl border bg-card shadow-md overflow-hidden divide-y divide-border/40">
      <RouterLink
        v-for="r in results"
        :key="r.slug"
        :to="{ name: 'doc-page', params: { slug: r.slug }, query: query.trim() ? { q: query.trim() } : undefined }"
        class="flex gap-3 px-4 py-3.5 text-sm text-foreground hover:bg-accent/60 transition-colors"
      >
        <div class="w-8 h-8 rounded-lg bg-primary/8 flex items-center justify-center shrink-0 mt-0.5">
          <svg class="w-4 h-4 text-primary/60" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
          </svg>
        </div>
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <span class="font-medium truncate">{{ r.title }}</span>
            <span v-if="r.space" class="shrink-0 text-[10px] font-semibold text-primary/50 bg-primary/6 px-1.5 py-0.5 rounded-md">{{ r.space }}</span>
          </div>
          <div v-if="r.section" class="text-xs text-primary/70 mt-0.5 truncate font-medium">
            <svg class="w-3 h-3 inline-block mr-0.5 -mt-px" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" d="m9 5 7 7-7 7" />
            </svg>
            {{ r.section }}
          </div>
          <p v-if="r.snippet" class="text-xs text-muted-foreground/60 mt-1 line-clamp-2 leading-relaxed" v-html="highlightSnippet(r.snippet, query)" />
        </div>
        <svg class="w-3.5 h-3.5 text-muted-foreground/20 shrink-0 mt-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" d="m9 5 7 7-7 7" />
        </svg>
      </RouterLink>
    </div>

    <!-- No Results -->
    <div v-else-if="query && !loading" class="mt-6 text-center py-10 rounded-xl border border-dashed bg-muted/30">
      <div class="w-12 h-12 rounded-full bg-muted/60 flex items-center justify-center mx-auto mb-3">
        <svg class="w-5 h-5 text-muted-foreground/40" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
        </svg>
      </div>
      <p class="text-sm text-muted-foreground">No results for "<span class="font-semibold text-foreground">{{ query }}</span>"</p>
      <p class="text-xs text-muted-foreground/50 mt-1.5">Try different keywords or browse by space below</p>
    </div>

    <!-- Browse Sections -->
    <div v-if="!query && sections.length" class="mt-12">
      <p class="text-xs font-semibold uppercase tracking-wider text-muted-foreground/40 mb-4">Browse by space</p>

      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <RouterLink
          v-for="(section, i) in sections"
          :key="section.space_key"
          :to="section.pages[0]?.slug ? { name: 'doc-page', params: { slug: section.pages[0].slug } } : '/docs'"
          class="group relative flex items-center gap-4 p-4 rounded-xl border bg-card hover:shadow-lg hover:border-primary/25 hover:-translate-y-px transition-all duration-200"
        >
          <div
            class="w-10 h-10 rounded-xl flex items-center justify-center text-white shrink-0 shadow-sm"
            :style="{ background: sectionColors[i % sectionColors.length] }"
          >
            <svg class="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
              <component :is="'path'" stroke-linecap="round" stroke-linejoin="round" :d="sectionIcons[i % sectionIcons.length]" />
            </svg>
          </div>
          <div class="min-w-0 flex-1">
            <span class="font-semibold text-[14px] text-foreground group-hover:text-primary transition-colors">
              {{ section.label }}
            </span>
            <p class="text-xs text-muted-foreground/50 mt-0.5">
              {{ countPages(section) }} {{ countPages(section) === 1 ? 'page' : 'pages' }}
            </p>
          </div>
          <svg class="w-4 h-4 text-muted-foreground/15 group-hover:text-primary/40 group-hover:translate-x-0.5 transition-all shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="m9 5 7 7-7 7" />
          </svg>
        </RouterLink>
      </div>
    </div>

    <!-- Keyboard hint -->
    <div v-if="!query" class="mt-10 flex items-center justify-center gap-1.5 text-xs text-muted-foreground/35">
      <kbd class="inline-flex h-5 items-center gap-0.5 rounded-md border bg-muted/40 px-1.5 font-mono text-[10px]">{{ isMac ? '⌘' : 'Ctrl' }}</kbd>
      <span>+</span>
      <kbd class="inline-flex h-5 items-center gap-0.5 rounded-md border bg-muted/40 px-1.5 font-mono text-[10px]">K</kbd>
      <span class="ml-1">to search from anywhere</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useDocsStore } from '@/stores/docs.js'
import { useDebouncedSearch } from '@/lib/useDebounce.js'

const store = useDocsStore()
const query = ref('')
const isMac = ref(false)

const { results, loading, search: doSearch } = useDebouncedSearch(async (q) => {
  await store.search(q)
  return store.searchResults
})

const sections = computed(() => store.sections || [])

const sectionColors = [
  'oklch(0.42 0.12 165)',  // emerald
  'oklch(0.44 0.10 245)',  // slate-indigo
  'oklch(0.48 0.13 20)',   // terracotta
  'oklch(0.46 0.12 145)',  // forest
  'oklch(0.52 0.14 60)',   // warm amber
  'oklch(0.43 0.10 295)',  // plum
]

const sectionIcons = [
  'M18 18.72a9.094 9.094 0 0 0 3.741-.479 3 3 0 0 0-4.682-2.72m.94 3.198.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0 1 12 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 0 1 6 18.719m12 0a5.971 5.971 0 0 0-.941-3.197m0 0A5.995 5.995 0 0 0 12 12.75a5.995 5.995 0 0 0-5.058 2.772m0 0a3 3 0 0 0-4.681 2.72 8.986 8.986 0 0 0 3.74.477m.94-3.197a5.971 5.971 0 0 0-.94 3.197M15 6.75a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm6 3a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Zm-13.5 0a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Z',
  'M3.75 3v11.25A2.25 2.25 0 0 0 6 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0 1 18 16.5h-2.25m-7.5 0h7.5m-7.5 0-1 3m8.5-3 1 3m0 0 .5 1.5m-.5-1.5h-9.5m0 0-.5 1.5M9 11.25v1.5M12 9v3.75m3-6v6',
  'M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z',
  'M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12Z',
  'M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75Z',
  'M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z',
]

function countPages(section) {
  let n = 0
  function walk(pages) { for (const p of pages) { n++; if (p.children) walk(p.children) } }
  walk(section.pages)
  return n
}

function onInput() {
  doSearch(query.value)
}

function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function highlightSnippet(text, q) {
  if (!q || !text) return escapeHtml(text || '')
  const safe = escapeHtml(text)
  const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return safe.replace(new RegExp(`(${escapeHtml(escaped)})`, 'gi'), '<mark>$1</mark>')
}

onMounted(() => {
  isMac.value = /Mac|iPhone|iPod|iPad/i.test(navigator.userAgentData?.platform || navigator.userAgent)
})
</script>
