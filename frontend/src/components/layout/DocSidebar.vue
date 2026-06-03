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
      <ul v-show="!fq" class="space-y-px px-2 mb-1">
        <li>
          <RouterLink to="/docs" class="sidebar-link" :class="isHome ? 'sidebar-link--active' : ''">
            <svg class="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6">
              <path stroke-linecap="round" stroke-linejoin="round" d="m2.25 12 8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
            </svg>
            Home
          </RouterLink>
        </li>
      </ul>

      <div
        v-for="section in store.sections"
        v-show="!fq || sectionHasMatches(section)"
        :key="section.space_key"
      >
        <!-- Release section header — doubles as a version switcher -->
        <div class="sidebar-ver-wrap">
          <p class="sidebar-section">
            <button
              v-if="section.versions?.length > 1"
              class="sidebar-ver-trigger"
              @click.stop="toggleVer(section.space_key)"
              :aria-expanded="openVer === section.space_key"
              aria-haspopup="listbox"
            >
              <span class="sidebar-section-label">{{ sectionHeading(section) }}</span>
              <svg class="sidebar-ver-chev" :class="openVer === section.space_key ? 'rotate-180' : ''" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
              </svg>
            </button>
            <span v-else class="sidebar-section-label">{{ sectionHeading(section) }}</span>
            <span class="sidebar-section-count tabular-nums">{{ countPages(section) }}</span>
          </p>
          <Transition name="ver-drop">
            <ul v-if="openVer === section.space_key" class="sidebar-ver-menu" role="listbox">
              <li v-for="v in section.versions" :key="v.label">
                <button
                  role="option"
                  :aria-selected="v.label === sectionHeading(section)"
                  class="sidebar-ver-opt"
                  :class="v.label === sectionHeading(section) ? 'sidebar-ver-opt--active' : ''"
                  @click="switchVer(section, v)"
                >
                  <span>{{ v.label }}</span>
                  <span v-if="v.is_latest" class="sidebar-ver-latest">latest</span>
                  <svg v-if="v.label === sectionHeading(section)" class="w-3.5 h-3.5 ml-auto shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="m4.5 12.75 6 6 9-13.5" /></svg>
                </button>
              </li>
            </ul>
          </Transition>
        </div>

        <ul v-if="getVersionPages(section).length" class="space-y-px px-2 mt-0.5">
          <SidebarNode
            v-for="page in getVersionPages(section)"
            :key="page.id"
            :page="page"
            :depth="0"
            :filtering="!!fq"
          />
        </ul>

        <!-- Resources: non-version pages (Release Notes, Policies) + contact -->
        <template v-if="getOtherPages(section).length || !fq">
          <p class="sidebar-section sidebar-section--spaced">
            <span class="sidebar-section-label">Resources</span>
          </p>
          <ul v-if="getOtherPages(section).length" class="space-y-px px-2">
            <SidebarNode
              v-for="page in getOtherPages(section)"
              :key="page.id"
              :page="page"
              :depth="0"
              :filtering="!!fq"
            />
          </ul>
          <ul v-show="!fq" class="space-y-px px-2">
            <li>
              <RouterLink to="/tickets" class="sidebar-link" :class="isContact ? 'sidebar-link--active' : ''">
                <svg class="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M8.625 9.75a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H8.25m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H12m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 0 1-2.555-.337A5.972 5.972 0 0 1 5.41 20.97a5.969 5.969 0 0 1-.474-.065 4.48 4.48 0 0 0 .978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25Z" />
                </svg>
                Contact support
              </RouterLink>
            </li>
          </ul>
        </template>
      </div>
    </template>
  </nav>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDocsStore } from '@/stores/docs.js'
import SidebarNode from './SidebarNode.vue'

const store = useDocsStore()
const route = useRoute()
const router = useRouter()
const isHome = computed(() => route.name === 'docs-home')
const isContact = computed(() => route.path === '/tickets')
const filterQuery = ref('')
const openVer = ref(null)

function toggleVer(spaceKey) {
  openVer.value = openVer.value === spaceKey ? null : spaceKey
}
function switchVer(section, v) {
  store.selectVersion(section.space_key, v.label)
  openVer.value = null
}
function onDocClick(e) {
  if (openVer.value && !e.target.closest('.sidebar-ver-wrap')) openVer.value = null
}
onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))

/**
 * The section's release header. For a versioned space, show the selected
 * version label (e.g. "Altus Release"); otherwise the space label.
 */
function sectionHeading(section) {
  if (section.versions?.length) {
    return store.getSelectedVersion(section.space_key) || section.label
  }
  return section.label
}
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
/* Nav links (Home, Contact support) — pill rows */
.sidebar-link {
  display: flex;
  align-items: center;
  gap: 9px;
  border-radius: 8px;
  padding: 7px 10px;
  font-size: 13.5px;
  font-weight: 500;
  color: var(--muted-foreground);
  transition: color 0.12s, background 0.12s;
}
.sidebar-link:hover {
  color: var(--foreground);
  background: var(--muted);
}
.sidebar-link--active {
  color: var(--sidebar-primary);
  background: var(--sidebar-accent);
  font-weight: 600;
}
.dark .sidebar-link--active { color: var(--sidebar-accent-foreground); }

/* Section labels (ALTUS RELEASE, RESOURCES) */
.sidebar-section {
  display: flex;
  align-items: center;
  margin: 0;
  padding: 0 14px;
  height: 28px;
}
.sidebar-section--spaced { margin-top: 14px; }
.sidebar-section-label {
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--muted-foreground);
}
.sidebar-section-count {
  margin-left: auto;
  font-size: 10px;
  font-weight: 600;
  color: var(--muted-foreground);
  opacity: 0.6;
}

/* Version switcher in the section header */
.sidebar-ver-wrap { position: relative; }
.sidebar-ver-trigger {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border-radius: 5px;
  margin: -2px -4px;
  padding: 2px 4px;
  transition: background 0.12s;
}
.sidebar-ver-trigger:hover { background: var(--muted); }
.sidebar-ver-trigger:hover .sidebar-section-label { color: var(--foreground); }
.sidebar-ver-chev {
  width: 11px;
  height: 11px;
  color: var(--muted-foreground);
  transition: transform 0.15s;
}
.sidebar-ver-menu {
  position: absolute;
  left: 12px;
  right: 12px;
  top: calc(100% + 2px);
  z-index: 30;
  list-style: none;
  margin: 0;
  padding: 4px;
  border-radius: 9px;
  border: 1px solid var(--border);
  background: var(--popover);
  box-shadow: 0 8px 24px oklch(0 0 0 / 0.12);
}
.sidebar-ver-opt {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 7px 9px;
  border-radius: 6px;
  font-size: 12.5px;
  color: var(--foreground);
  transition: background 0.1s;
}
.sidebar-ver-opt:hover { background: var(--accent); }
.sidebar-ver-opt--active { color: var(--sidebar-primary); font-weight: 600; }
.dark .sidebar-ver-opt--active { color: var(--sidebar-accent-foreground); }
.sidebar-ver-latest {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--brand-accent);
  background: color-mix(in srgb, var(--brand-accent) 14%, transparent);
  padding: 1px 6px;
  border-radius: 4px;
}
.ver-drop-enter-active, .ver-drop-leave-active { transition: opacity 0.14s, transform 0.14s; }
.ver-drop-enter-from, .ver-drop-leave-to { opacity: 0; transform: translateY(-4px); }

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
