<template>
  <div class="w-full">
    <!-- Loading skeleton -->
    <div v-if="store.loading" class="page-pad py-10">
      <div class="h-3 w-24 bg-muted rounded-full animate-pulse" />
      <div class="h-7 w-2/3 bg-muted rounded-lg mt-4 animate-pulse" />
      <div class="h-px bg-border mt-6 mb-8" />
      <div class="space-y-3.5">
        <div class="h-3.5 w-full bg-muted rounded-full animate-pulse" />
        <div class="h-3.5 w-[92%] bg-muted rounded-full animate-pulse" />
        <div class="h-3.5 w-5/6 bg-muted rounded-full animate-pulse" />
        <div class="h-3.5 w-3/4 bg-muted rounded-full animate-pulse" />
      </div>
      <div class="mt-8 space-y-3.5">
        <div class="h-5 w-40 bg-muted rounded-lg animate-pulse" />
        <div class="h-3.5 w-full bg-muted rounded-full animate-pulse" />
        <div class="h-3.5 w-[88%] bg-muted rounded-full animate-pulse" />
      </div>
    </div>

    <!-- Error -->
    <div v-else-if="store.error" class="page-pad py-24 text-center">
      <div class="w-12 h-12 rounded-full bg-muted flex items-center justify-center mx-auto mb-4">
        <svg class="w-6 h-6 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
        </svg>
      </div>
      <p class="text-sm font-medium text-foreground mb-1">Something went wrong</p>
      <p class="text-sm text-muted-foreground">{{ store.error }}</p>
    </div>

    <!-- Content -->
    <template v-else-if="store.currentPage">
      <div class="flex">
        <article ref="articleRef" class="flex-1 min-w-0 page-pad py-8">
          <Breadcrumbs :crumbs="store.currentPage.breadcrumbs" />

          <!-- Search match banner -->
          <div v-if="searchQuery && matchCount > 0" class="flex items-center gap-2 mb-4 px-3 py-2 rounded-lg bg-accent border border-primary/20 text-xs text-accent-foreground">
            <svg class="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
            </svg>
            <span>{{ matchCount }} match{{ matchCount === 1 ? '' : 'es' }} for "<strong>{{ searchQuery }}</strong>"</span>
            <button @click="clearHighlights" aria-label="Dismiss search highlights" class="ml-auto text-muted-foreground hover:text-foreground transition-colors">
              <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <h1 class="text-[1.75rem] font-bold tracking-tight leading-tight text-foreground mt-1">
            {{ store.currentPage.title }}
          </h1>

          <div class="mt-6 pt-6 border-t border-border-subtle">
            <ProseContent :html="store.currentPage.rendered_html" />
          </div>

          <!-- Footer -->
          <footer class="mt-12 pt-6 border-t">
            <div class="flex items-center justify-between text-xs text-muted-foreground">
              <span v-if="store.currentPage.last_synced">
                Last updated {{ formatDate(store.currentPage.last_synced) }}
              </span>
              <a
                :href="`#`"
                @click.prevent="scrollToTop"
                class="inline-flex items-center gap-1 hover:text-muted-foreground transition-colors"
              >
                <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="m4.5 15.75 7.5-7.5 7.5 7.5" />
                </svg>
                Back to top
              </a>
            </div>
          </footer>
        </article>

        <!-- TOC -->
        <div class="hidden xl:block w-52 shrink-0">
          <div class="sticky top-[72px] py-8 pr-6">
            <TableOfContents :html="store.currentPage.rendered_html" />
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDocsStore } from '@/stores/docs.js'
import Breadcrumbs from '@/components/layout/Breadcrumbs.vue'
import TableOfContents from './TableOfContents.vue'
import ProseContent from './ProseContent.vue'

const props = defineProps({ slug: String })
const store = useDocsStore()
const route = useRoute()
const router = useRouter()
const articleRef = ref(null)
const matchCount = ref(0)

const searchQuery = computed(() => route.query.q || '')

async function loadPage() {
  await store.fetchPage(props.slug)
  await nextTick()
  if (window.Prism) window.Prism.highlightAll()
  // Highlight after content renders
  await nextTick()
  if (searchQuery.value) {
    highlightMatches(searchQuery.value)
  }
}

function highlightMatches(query) {
  if (!articleRef.value || !query) return

  // Clear previous highlights first
  clearHighlightMarks()

  const content = articleRef.value.querySelector('.confluence-content')
  if (!content) return

  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const regex = new RegExp(escaped, 'gi')
  let count = 0

  // Walk text nodes and wrap matches in <mark>
  const walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT)
  const nodesToReplace = []

  let node
  while ((node = walker.nextNode())) {
    if (node.parentElement?.tagName === 'SCRIPT' || node.parentElement?.tagName === 'STYLE') continue
    if (regex.test(node.textContent)) {
      nodesToReplace.push(node)
      regex.lastIndex = 0
    }
  }

  for (const textNode of nodesToReplace) {
    const fragment = document.createDocumentFragment()
    let lastIndex = 0
    const text = textNode.textContent
    let match

    regex.lastIndex = 0
    while ((match = regex.exec(text)) !== null) {
      // Add text before match
      if (match.index > lastIndex) {
        fragment.appendChild(document.createTextNode(text.slice(lastIndex, match.index)))
      }
      // Add highlighted match
      const mark = document.createElement('mark')
      mark.className = 'search-highlight'
      mark.textContent = match[0]
      fragment.appendChild(mark)
      count++
      lastIndex = regex.lastIndex
    }
    // Add remaining text
    if (lastIndex < text.length) {
      fragment.appendChild(document.createTextNode(text.slice(lastIndex)))
    }

    textNode.parentNode.replaceChild(fragment, textNode)
  }

  matchCount.value = count

  // Scroll to first match
  if (count > 0) {
    setTimeout(() => {
      const firstMark = articleRef.value?.querySelector('.search-highlight')
      if (firstMark) {
        const main = firstMark.closest('main')
        if (main) {
          const rect = firstMark.getBoundingClientRect()
          const mainRect = main.getBoundingClientRect()
          main.scrollTo({ top: main.scrollTop + rect.top - mainRect.top - 100, behavior: 'smooth' })
        } else {
          firstMark.scrollIntoView({ behavior: 'smooth', block: 'center' })
        }
      }
    }, 100)
  }
}

function clearHighlightMarks() {
  if (!articleRef.value) return
  articleRef.value.querySelectorAll('mark.search-highlight').forEach(mark => {
    const parent = mark.parentNode
    parent.replaceChild(document.createTextNode(mark.textContent), mark)
    parent.normalize()
  })
  matchCount.value = 0
}

function clearHighlights() {
  clearHighlightMarks()
  // Remove q from URL without triggering navigation
  router.replace({ query: {} })
}

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function scrollToTop() {
  const main = document.querySelector('main')
  if (main) {
    main.scrollTo({ top: 0, behavior: 'smooth' })
  } else {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
}

watch(() => props.slug, loadPage, { immediate: true })
</script>

<style scoped>
.page-pad {
  padding-left: clamp(1.5rem, 4vw, 3rem);
  padding-right: clamp(1.5rem, 4vw, 3rem);
}
</style>
