<template>
  <nav class="text-[13px]" aria-label="Documentation">
    <div v-if="store.loading" class="px-4 py-8 space-y-2">
      <div class="h-2.5 w-20 bg-muted rounded-full animate-pulse" />
      <div class="h-2.5 w-32 bg-muted rounded-full animate-pulse" />
      <div class="h-2.5 w-24 bg-muted rounded-full animate-pulse" />
    </div>
    <div v-else-if="store.error" class="px-4 py-8 text-destructive text-xs">{{ store.error }}</div>
    <template v-else>
      <!-- Quick-find filter — type to prune the tree. Essential wayfinding
           at scale; reviewers can locate any document by name instantly. -->
      <div class="px-2 pt-1 pb-2">
        <div class="sidebar-filter">
          <svg class="sidebar-filter-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
          </svg>
          <input
            v-model="filterQuery"
            type="text"
            class="sidebar-filter-input"
            placeholder="Filter pages…"
            aria-label="Filter documentation pages by title"
            autocomplete="off"
            spellcheck="false"
          />
          <button
            v-if="filterQuery"
            @click="filterQuery = ''"
            class="sidebar-filter-clear"
            aria-label="Clear filter"
            type="button"
          >
            <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      <!-- No-results state when filtering -->
      <p v-if="fq && noMatches" class="px-4 py-6 text-xs text-muted-foreground text-center">
        No pages match “{{ filterQuery }}”.
      </p>

      <!-- Home -->
      <ul v-show="!fq" class="space-y-px px-2 mb-2">
        <li>
          <RouterLink
            to="/docs"
            class="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-[13.5px] leading-snug transition-colors duration-100"
            :class="isHome
              ? 'bg-primary/10 text-primary font-semibold'
              : 'text-muted-foreground hover:text-foreground hover:bg-muted'"
          >
            <svg class="w-4 h-4 shrink-0" :class="isHome ? 'text-primary' : 'text-muted-foreground'" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
              <path stroke-linecap="round" stroke-linejoin="round" d="m2.25 12 8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
            </svg>
            Home
          </RouterLink>
        </li>
      </ul>

      <div
        v-for="(section, i) in store.sections"
        v-show="!fq || sectionHasMatches(section)"
        :key="section.space_key"
      >
        <!-- Section divider -->
        <div class="mx-4 my-2.5 border-t" />

        <!-- Section header -->
        <button
          @click="toggleSection(section.space_key)"
          class="flex items-center w-full px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground hover:text-muted-foreground transition-colors"
        >
          <svg
            class="w-3 h-3 mr-1.5 transition-transform duration-200"
            :class="collapsed[section.space_key] ? '' : 'rotate-90'"
            fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"
          >
            <path stroke-linecap="round" stroke-linejoin="round" d="m9 5 7 7-7 7" />
          </svg>
          {{ section.label }}
          <span class="ml-auto font-normal text-[10px] tabular-nums opacity-50">{{ countPages(section) }}</span>
        </button>

        <!-- Version switcher (if space has versions) -->
        <VersionSwitcher
          v-if="section.versions?.length"
          :space-key="section.space_key"
          :space-label="section.label"
        />

        <!-- Version docs -->
        <Transition name="sidebar-expand">
          <div v-show="fq || !collapsed[section.space_key]">
            <ul v-if="getVersionPages(section).length" class="space-y-px px-2">
              <SidebarNode
                v-for="page in getVersionPages(section)"
                :key="page.id"
                :page="page"
                :depth="0"
                :filtering="!!fq"
              />
            </ul>

            <!-- Other Documentation (non-version pages) -->
            <template v-if="section.versions?.length && getOtherPages(section).length">
              <div class="mx-4 my-2 border-t" />
              <div class="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">Other Documentation</div>
            </template>

            <ul v-if="getOtherPages(section).length" class="space-y-px px-2">
              <SidebarNode
                v-for="page in getOtherPages(section)"
                :key="page.id"
                :page="page"
                :depth="0"
                :filtering="!!fq"
              />
            </ul>
          </div>
        </Transition>
      </div>
    </template>
  </nav>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { useDocsStore } from '@/stores/docs.js'
import SidebarNode from './SidebarNode.vue'
import VersionSwitcher from './VersionSwitcher.vue'

const store = useDocsStore()
const route = useRoute()
const isHome = computed(() => route.name === 'docs-home')
const collapsed = reactive({})
const filterQuery = ref('')
const fq = computed(() => filterQuery.value.trim().toLowerCase())

/**
 * Prune a page tree to entries matching the query (case-insensitive title).
 * A matching node keeps its whole subtree; a non-matching node survives only
 * if some descendant matches, preserving the path to every hit.
 */
function pruneTree(pages, q) {
  if (!q) return pages
  const out = []
  for (const p of pages) {
    if ((p.title || '').toLowerCase().includes(q)) {
      out.push(p)
      continue
    }
    const kids = p.children ? pruneTree(p.children, q) : []
    if (kids.length) out.push({ ...p, children: kids })
  }
  return out
}

function countTree(list) {
  let n = 0
  for (const p of list) { n++; if (p.children) n += countTree(p.children) }
  return n
}

function sectionHasMatches(section) {
  return getVersionPages(section).length > 0 || getOtherPages(section).length > 0
}

const noMatches = computed(() =>
  fq.value && store.sections.every(s => !sectionHasMatches(s))
)

watch(() => route.params.slug, () => {
  nextTick(() => {
    const active = document.querySelector('[data-sidebar-active]')
    if (active) {
      active.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }
  })
})

function toggleSection(key) {
  collapsed[key] = !collapsed[key]
}

/**
 * Get the selected version's pre-built page tree.
 * Returns empty array for non-versioned spaces.
 */
function getVersionPages(section) {
  if (!section.versions?.length) return pruneTree(section.pages, fq.value)

  const selectedLabel = store.getSelectedVersion(section.space_key)
  if (!selectedLabel) return []

  const selectedVersion = section.versions.find(v => v.label === selectedLabel)
  return pruneTree(selectedVersion?.pages || [], fq.value)
}

/** Non-version "Other Documentation" pages for a versioned space (pruned). */
function getOtherPages(section) {
  if (!section.versions?.length) return []
  return pruneTree(section.pages, fq.value)
}

function countPages(section) {
  return countTree(getVersionPages(section)) + countTree(getOtherPages(section))
}
</script>

<style scoped>
.sidebar-filter {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 8px;
  border-radius: 8px;
  background: var(--background);
  border: 1px solid var(--border-subtle);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.sidebar-filter:focus-within {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px oklch(0.52 0.20 260 / 0.1);
}
.sidebar-filter-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  color: var(--muted-foreground);
}
.sidebar-filter-input {
  flex: 1;
  min-width: 0;
  border: none;
  background: transparent;
  outline: none;
  font-family: var(--font-ui);
  font-size: 12.5px;
  color: var(--foreground);
}
.sidebar-filter-input::placeholder {
  color: var(--muted-foreground);
}
.sidebar-filter-clear {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 4px;
  color: var(--muted-foreground);
  transition: color 0.15s, background 0.15s;
}
.sidebar-filter-clear:hover {
  color: var(--foreground);
  background: var(--muted);
}
</style>
