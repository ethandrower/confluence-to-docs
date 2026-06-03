<template>
  <div class="home">
    <div class="home-inner">
      <!-- Version banner -->
      <div v-if="primaryVersions.length" class="ver-banner">
        <svg class="ver-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" d="M9.568 3H5.25A2.25 2.25 0 0 0 3 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 0 0 5.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 0 0 9.568 3Z" />
          <path stroke-linecap="round" stroke-linejoin="round" d="M6 6h.008v.008H6V6Z" />
        </svg>
        <span class="ver-text">
          You're viewing the <strong>{{ isLatestSelected ? 'latest' : 'selected' }}</strong> release
        </span>
        <div class="ver-switch">
          <button class="ver-pill" @click="verOpen = !verOpen" :aria-expanded="verOpen" aria-haspopup="listbox">
            {{ selectedVersionLabel }}
            <svg class="w-3 h-3" :class="verOpen ? 'rotate-180' : ''" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" /></svg>
          </button>
          <Transition name="ver-drop">
            <ul v-if="verOpen" class="ver-menu" role="listbox">
              <li v-for="v in primaryVersions" :key="v.label">
                <button
                  role="option"
                  :aria-selected="v.label === selectedVersionLabel"
                  class="ver-opt"
                  :class="v.label === selectedVersionLabel ? 'ver-opt--active' : ''"
                  @click="switchVersion(v)"
                >
                  <span>{{ v.label }}</span>
                  <span v-if="v.is_latest" class="ver-latest">latest</span>
                </button>
              </li>
            </ul>
          </Transition>
        </div>
      </div>

      <!-- Hero -->
      <section class="hero">
        <div class="hero-mark" aria-hidden="true">
          <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.292m0-14.25v14.25" />
          </svg>
        </div>
        <div class="hero-body">
          <h1 class="hero-title">CiteMed documentation</h1>
          <p class="hero-sub">
            Guides, module references, and release notes for Evidence Cloud. Browse by
            module below, or use search to find an answer fast.
          </p>
        </div>
      </section>

      <!-- Browse by module -->
      <section v-if="modules.length" class="block">
        <p class="block-label">Browse by module</p>
        <div class="module-grid">
          <RouterLink
            v-for="(m, i) in modules"
            :key="m.id"
            :to="{ name: 'doc-page', params: { slug: m.slug } }"
            class="module-card"
            :style="{ '--delay': i * 40 + 'ms' }"
          >
            <span class="module-chip" aria-hidden="true">
              <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6">
                <path stroke-linecap="round" stroke-linejoin="round" :d="m.icon" />
              </svg>
            </span>
            <span class="module-title">{{ m.title }}</span>
            <span class="module-desc">{{ m.desc }}</span>
            <span class="module-meta">{{ m.count }} {{ m.count === 1 ? 'page' : 'pages' }}</span>
          </RouterLink>
        </div>
      </section>

      <!-- Recently viewed (this device) -->
      <section v-if="recent.length" class="block">
        <p class="block-label">Recently viewed</p>
        <ul class="recent-list">
          <li v-for="r in recent" :key="r.slug">
            <RouterLink :to="{ name: 'doc-page', params: { slug: r.slug } }" class="recent-row">
              <svg class="recent-icon w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" /></svg>
              <span class="recent-title">{{ r.title }}</span>
              <span class="recent-date">{{ relativeDate(r.ts) }}</span>
            </RouterLink>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useDocsStore } from '@/stores/docs.js'
import { useRecentlyViewed } from '@/lib/useRecentlyViewed.js'

const store = useDocsStore()
const isMac = ref(false)
const verOpen = ref(false)

// Professional, consistent line-icon set (Heroicons outline) per module.
const ICONS = {
  rocket: 'M15.59 14.37a6 6 0 0 1-5.84 7.38v-4.8m5.84-2.58a14.98 14.98 0 0 0 6.16-12.12A14.98 14.98 0 0 0 9.631 8.41m5.96 5.96a14.926 14.926 0 0 1-5.841 2.58m-.119-8.54a6 6 0 0 0-7.381 5.84h4.8m2.581-5.84a14.927 14.927 0 0 0-2.58 5.84m2.699 2.7c-.103.021-.207.041-.311.06a15.09 15.09 0 0 1-2.448-2.448 14.9 14.9 0 0 1 .06-.312m-2.24 2.39a4.493 4.493 0 0 0-1.757 4.306 4.493 4.493 0 0 0 4.306-1.758M16.5 9a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0Z',
  shield: 'M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z',
  book: 'M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.292m0-14.25v14.25',
  library: 'M12 21v-8.25M15.75 21v-8.25M8.25 21v-8.25M3 9l9-6 9 6m-1.5 12V10.332A48.36 48.36 0 0 0 12 9.75c-2.551 0-5.056.2-7.5.582V21M3 21h18M12 6.75h.008v.008H12V6.75Z',
  gear: 'M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.24-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.281Z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
  doc: 'M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z',
}

// Curated descriptions + icons by module name (case-insensitive). Falls back
// to a generic doc icon for any module not listed.
const MODULE_META = {
  'getting started': { icon: ICONS.rocket, desc: 'Setup, onboarding, and account access' },
  'vigilance module': { icon: ICONS.shield, desc: 'Post-market surveillance, safety signals, PSUR' },
  'literature module': { icon: ICONS.book, desc: 'Search, screening, and appraisal' },
  'citesource module': { icon: ICONS.library, desc: 'Reference library, lists, and export' },
  'admin module': { icon: ICONS.gear, desc: 'Users, permissions, and configuration' },
}

function metaFor(title) {
  const key = (title || '').toLowerCase().replace(/^v?\d+\.\d+(?:\.\d+)?\s+/, '').trim()
  return MODULE_META[key] || { icon: ICONS.doc, desc: 'Guides and reference' }
}

function stripVersionPrefix(t) {
  return (t || '').replace(/^[Vv]\d+\.\d+(?:\.\d+)?\s+[-–]\s*/, '').replace(/^[Vv]\d+\.\d+(?:\.\d+)?\s+/, '')
}
function firstSlug(node) {
  for (const c of node.children || []) {
    if (c.slug && !c.is_folder) return c.slug
    const d = firstSlug(c)
    if (d) return d
  }
  return ''
}
function countTree(list) {
  let n = 0
  for (const p of list || []) { n += 1; n += countTree(p.children) }
  return n
}

// The primary versioned space (Evidence Cloud).
const primarySection = computed(() =>
  store.sections.find(s => s.versions?.length) || store.sections[0] || null
)
const primaryVersions = computed(() => primarySection.value?.versions || [])
const selectedVersionLabel = computed(() =>
  primarySection.value ? store.getSelectedVersion(primarySection.value.space_key) : null
)
const isLatestSelected = computed(() =>
  primaryVersions.value.find(v => v.label === selectedVersionLabel.value)?.is_latest ?? true
)

function selectedVersionPages() {
  const s = primarySection.value
  if (!s) return []
  if (!s.versions?.length) return s.pages || []
  const v = s.versions.find(x => x.label === selectedVersionLabel.value) || s.versions[0]
  return v?.pages || []
}

// Module cards = top-level pages of the selected version.
const modules = computed(() =>
  selectedVersionPages()
    .map(p => {
      const meta = metaFor(p.title)
      return {
        id: p.id,
        title: stripVersionPrefix(p.title),
        slug: p.slug && !p.is_folder ? p.slug : firstSlug(p),
        count: countTree(p.children),
        icon: meta.icon,
        desc: meta.desc,
      }
    })
    .filter(m => m.slug)
)

// Recently viewed (this device) — accurate per-user history. We'll swap to a
// real "recently updated" feed once we sync Confluence's last-modified dates.
const { recent: recentRaw, load: loadRecent } = useRecentlyViewed()
const recent = computed(() =>
  recentRaw.value.map(p => ({ slug: p.slug, title: stripVersionPrefix(p.title), ts: p.ts }))
)

function relativeDate(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  const days = Math.round((Date.now() - d.getTime()) / 86400000)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 7) return `${days} days ago`
  if (days < 30) return `${Math.floor(days / 7)} week${days < 14 ? '' : 's'} ago`
  if (days < 365) return `${Math.floor(days / 30)} month${days < 60 ? '' : 's'} ago`
  return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
}

function switchVersion(v) {
  if (primarySection.value) store.selectVersion(primarySection.value.space_key, v.label)
  verOpen.value = false
}
function openSearch() {
  window.dispatchEvent(new CustomEvent('citemed:open-search'))
}

onMounted(() => {
  isMac.value = /Mac|iPhone|iPod|iPad/i.test(navigator.userAgentData?.platform || navigator.userAgent)
  loadRecent()
})
</script>

<style scoped>
.home { padding: 28px clamp(1.5rem, 4vw, 3rem) 64px; }
.home-inner { max-width: 880px; margin: 0 auto; }

/* ── Version banner ── */
.ver-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--card);
  font-size: 13px;
  color: var(--muted-foreground);
  margin-bottom: 22px;
}
.ver-icon { width: 16px; height: 16px; color: var(--primary); flex-shrink: 0; }
.ver-text strong { color: var(--foreground); font-weight: 600; }
.ver-switch { margin-left: auto; position: relative; }
.ver-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 7px;
  background: var(--accent);
  color: var(--primary);
  font-weight: 600;
  font-size: 12.5px;
  border: 1px solid transparent;
  transition: border-color 0.15s;
}
.dark .ver-pill { color: var(--accent-foreground); }
.ver-pill:hover { border-color: var(--accent-hover); }
.ver-pill svg { transition: transform 0.15s; }
.ver-menu {
  position: absolute;
  right: 0;
  top: calc(100% + 6px);
  z-index: 20;
  min-width: 220px;
  list-style: none;
  margin: 0;
  padding: 5px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--popover);
  box-shadow: 0 10px 30px oklch(0 0 0 / 0.12);
}
.ver-opt {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border-radius: 7px;
  font-size: 13px;
  color: var(--foreground);
  transition: background 0.12s;
}
.ver-opt:hover { background: var(--accent); }
.ver-opt--active { color: var(--primary); font-weight: 600; }
.dark .ver-opt--active { color: var(--accent-foreground); }
.ver-latest {
  margin-left: auto;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--brand-accent);
  background: color-mix(in srgb, var(--brand-accent) 14%, transparent);
  padding: 1px 7px;
  border-radius: 5px;
}
.ver-drop-enter-active, .ver-drop-leave-active { transition: opacity 0.14s, transform 0.14s; }
.ver-drop-enter-from, .ver-drop-leave-to { opacity: 0; transform: translateY(-4px); }

/* ── Hero ── */
.hero {
  display: flex;
  gap: 18px;
  padding: 26px;
  border-radius: 14px;
  background: var(--primary);
  color: #fff;
  position: relative;
  overflow: hidden;
}
.hero::after {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(120% 140% at 100% 0%, color-mix(in srgb, var(--brand-accent) 40%, transparent), transparent 55%);
  opacity: 0.5;
  pointer-events: none;
}
.hero-mark {
  position: relative;
  z-index: 1;
  width: 46px;
  height: 46px;
  border-radius: 11px;
  background: rgba(255, 255, 255, 0.14);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
}
.hero-body { position: relative; z-index: 1; min-width: 0; }
.hero-title {
  font-family: var(--font-ui);
  font-size: 28px;
  font-weight: 600;
  letter-spacing: -0.02em;
  line-height: 1.1;
  margin: 2px 0 0;
  color: #fff;
}
.hero-sub {
  margin: 8px 0 0;
  font-size: 14.5px;
  line-height: 1.5;
  color: rgba(255, 255, 255, 0.82);
  max-width: 60ch;
}
.hero-search {
  margin-top: 16px;
  display: inline-flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  max-width: 380px;
  padding: 9px 12px;
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.18);
  color: rgba(255, 255, 255, 0.9);
  font-size: 13.5px;
  transition: background 0.15s;
}
.hero-search:hover { background: rgba(255, 255, 255, 0.18); }
.hero-search span { flex: 1; text-align: left; }
.hero-search kbd {
  font-family: var(--font-ui);
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 5px;
  background: rgba(255, 255, 255, 0.16);
}

/* ── Blocks ── */
.block { margin-top: 34px; }
.block-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--muted-foreground);
  margin: 0 0 14px;
}

/* ── Module grid ── */
.module-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}
.module-card {
  position: relative;
  display: grid;
  grid-template-columns: auto 1fr;
  grid-template-areas: 'chip title' 'chip desc' 'chip meta';
  column-gap: 13px;
  row-gap: 2px;
  padding: 16px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: var(--card);
  transition: border-color 0.16s, box-shadow 0.16s, transform 0.16s;
  animation: card-in 0.4s ease both;
  animation-delay: var(--delay, 0ms);
}
.module-card:hover {
  border-color: color-mix(in srgb, var(--primary) 35%, var(--border));
  box-shadow: 0 6px 20px oklch(0 0 0 / 0.06);
  transform: translateY(-2px);
}
.module-chip {
  grid-area: chip;
  align-self: start;
  width: 38px;
  height: 38px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent);
  color: var(--primary);
}
.dark .module-chip { color: var(--accent-foreground); }
.module-title {
  grid-area: title;
  font-weight: 600;
  font-size: 14.5px;
  color: var(--foreground);
  letter-spacing: -0.01em;
}
.module-desc {
  grid-area: desc;
  font-size: 12.5px;
  line-height: 1.45;
  color: var(--muted-foreground);
  margin-top: 1px;
}
.module-meta {
  grid-area: meta;
  margin-top: 7px;
  font-size: 11px;
  font-weight: 600;
  color: var(--brand-accent);
  font-variant-numeric: tabular-nums;
}

/* ── Recently updated ── */
.recent-list { list-style: none; margin: 0; padding: 0; border-radius: 12px; border: 1px solid var(--border); background: var(--card); overflow: hidden; }
.recent-row {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 12px 15px;
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.12s;
}
.recent-list li:last-child .recent-row { border-bottom: none; }
.recent-row:hover { background: var(--accent); }
.recent-icon { color: var(--muted-foreground); flex-shrink: 0; }
.recent-title { font-size: 13.5px; color: var(--foreground); font-weight: 500; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.recent-date { margin-left: auto; font-size: 12px; color: var(--muted-foreground); flex-shrink: 0; }

@keyframes card-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
@media (prefers-reduced-motion: reduce) {
  .module-card { animation: none; }
}
</style>
