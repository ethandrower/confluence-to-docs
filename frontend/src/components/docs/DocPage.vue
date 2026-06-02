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
          <div class="max-w-[var(--content-max-width)]">

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

            <!-- Document metadata trust bar — version / currency / provenance.
                 Traceability signals for regulatory review. -->
            <div class="doc-meta" aria-label="Document information">
              <span v-if="store.currentPage.confluence_version" class="doc-meta-item">
                <svg class="doc-meta-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                </svg>
                Version {{ store.currentPage.confluence_version }}
              </span>
              <span v-if="store.currentPage.last_synced" class="doc-meta-item">
                <svg class="doc-meta-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                </svg>
                Updated <time :datetime="store.currentPage.last_synced">{{ formatDate(store.currentPage.last_synced) }}</time>
              </span>
            </div>

            <div class="mt-5 pt-6 border-t border-border-subtle">
              <ProseContent :html="store.currentPage.rendered_html" />
            </div>

          </div>

          <!-- Back to top — spans the full article width, aligned right. -->
          <footer class="doc-foot">
            <button type="button" @click="scrollToTop" class="doc-prov-top">
              <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="m4.5 15.75 7.5-7.5 7.5 7.5" />
              </svg>
              Back to top
            </button>
          </footer>
        </article>

        <!-- TOC -->
        <div class="hidden lg:block w-40 xl:w-52 shrink-0">
          <div class="sticky top-6 py-8 pr-4 xl:pr-6">
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

  // Container/root pages often have no body — open their first child instead.
  const cp = store.currentPage
  if (cp) {
    const text = (cp.rendered_html || '').replace(/<[^>]*>/g, '').replace(/&nbsp;/gi, ' ').trim()
    if (!text) {
      const child = store.firstChildSlug(cp.slug)
      if (child && child !== props.slug) {
        router.replace({ name: 'doc-page', params: { slug: child } })
        return
      }
    }
  }

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

/* ── Document metadata trust bar ─────────────────────────────────────── */
.doc-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 16px;
  margin-top: 12px;
}
.doc-meta-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-family: var(--font-ui);
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--muted-foreground);
  letter-spacing: -0.005em;
}
.doc-meta-icon {
  width: 13px;
  height: 13px;
  flex-shrink: 0;
  opacity: 0.8;
}

/* ── Back-to-top footer (full article width, right-aligned) ──────────── */
.doc-foot {
  display: flex;
  justify-content: flex-end;
  margin-top: 3.5rem;
  padding-top: 1.25rem;
  border-top: 1px solid var(--border);
  font-family: var(--font-ui);
}
.doc-prov-top {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--muted-foreground);
  border-radius: 6px;
  padding: 4px 8px;
  transition: color 0.15s, background 0.15s;
}
.doc-prov-top:hover {
  color: var(--foreground);
  background: var(--muted);
}
.doc-prov-top:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

/* ── Print / PDF: controlled-document layout ─────────────────────────────
   Auditors export pages as evidence. Strip the app chrome and present a
   clean document with a provenance footer (title · version · date · URL)
   on every printed page. */
@media print {
  /* Hide everything except the article via global rules (scoped styles can't
     reach app shell, so this block is intentionally broad through :global). */
  .doc-meta { margin-top: 8px; }
  .doc-meta-item { color: #444; }
}
</style>

<!-- Global print rules (unscoped) — hide app chrome, format the document -->
<style>
@media print {
  /* Hide app chrome: top nav, sidebar, TOC, search banner, back-to-top */
  header[class*="border-b"], aside, nav[aria-label="Documentation"],
  .version-switcher, [aria-label="Search documentation"] { display: none !important; }
  .hidden.lg\:block { display: none !important; }

  /* Reset layout to full-width single column */
  main, article, .page-pad { all: unset !important; }
  body { background: #fff !important; color: #000 !important; }
  .confluence-content {
    max-width: 100% !important;
    font-family: 'Source Sans 3 Variable', Georgia, serif;
    font-size: 11pt;
    line-height: 1.5;
    color: #000;
  }

  /* Page setup with a controlled-document footer */
  @page {
    margin: 18mm 16mm 22mm 16mm;
  }

  /* Expand links to show their destination (traceability) */
  .confluence-content a[href^="http"]::after {
    content: " (" attr(href) ")";
    font-size: 8pt;
    color: #555;
    word-break: break-all;
  }

  /* Drop the back-to-top button from printed copies */
  .doc-foot { display: none !important; }

  /* Avoid awkward breaks */
  .confluence-content h1, .confluence-content h2, .confluence-content h3 {
    break-after: avoid;
  }
  .confluence-content img, .confluence-content table, .confluence-content pre {
    break-inside: avoid;
    max-width: 100% !important;
  }
}
</style>
