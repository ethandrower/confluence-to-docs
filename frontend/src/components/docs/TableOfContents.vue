<template>
  <nav v-if="headings.length" aria-label="Table of contents" class="toc">
    <p class="toc-title">On this page</p>
    <ul class="toc-list" ref="listRef">
      <!-- Progress rail: a thumb tracks the active heading down the list -->
      <span class="toc-rail" aria-hidden="true" />
      <span
        v-if="thumb.visible"
        class="toc-rail-thumb"
        aria-hidden="true"
        :style="{ transform: `translateY(${thumb.top}px)`, height: `${thumb.height}px` }"
      />
      <li v-for="h in headings" :key="h.id" :ref="el => setItemRef(h.id, el)">
        <a
          :href="`#${h.id}`"
          @click.prevent="scrollTo(h.id)"
          class="toc-link"
          :class="[
            h.level === 3 ? 'toc-link--nested' : '',
            activeId === h.id ? 'toc-link--active' : ''
          ]"
          :aria-current="activeId === h.id ? 'location' : undefined"
        >{{ h.text }}</a>
      </li>
    </ul>
  </nav>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'

const props = defineProps({ html: String })
const activeId = ref('')
const headings = ref([])
const listRef = ref(null)
const itemEls = new Map()
const thumb = reactive({ top: 0, height: 0, visible: false })

function setItemRef(id, el) {
  if (el) itemEls.set(id, el)
  else itemEls.delete(id)
}

function slugify(text) {
  return text.toLowerCase().replace(/\s+/g, '-').replace(/[^\w-]/g, '')
}

function parseHeadings() {
  const content = document.querySelector('.confluence-content')
  if (!content) { headings.value = []; return }

  const found = []
  for (const h of content.querySelectorAll('h2, h3')) {
    // Strip the anchor "#" prefix that ProseContent adds
    const text = h.textContent.replace(/^#\s*/, '').trim()
    if (!text || text.includes('Image unavailable') || text.length < 2) continue
    // Guarantee a DOM id so getElementById / scrollTo always resolve.
    if (!h.id) {
      let base = slugify(text) || 'section'
      let id = base, n = 2
      while (document.getElementById(id)) id = `${base}-${n++}`
      h.id = id
    }
    found.push({ id: h.id, text, level: parseInt(h.tagName[1]) })
  }
  headings.value = found
}

function getScroller() {
  return document.querySelector('main') || document.scrollingElement || document.documentElement
}

// Deterministic active-section detection: the current section is the LAST
// heading whose top has scrolled above a fixed threshold line. This is stable
// in both scroll directions and never goes stale (unlike enter-only observers).
const THRESHOLD = 96 // px below the scroller's top edge

function computeActive() {
  const root = getScroller()
  if (!root || !headings.value.length) return

  // Bottom of page: force-activate the last heading so trailing short
  // sections (which never reach the threshold line) still highlight.
  if (root.scrollTop + root.clientHeight >= root.scrollHeight - 4) {
    setActive(headings.value[headings.value.length - 1].id)
    return
  }

  const rootTop = root.getBoundingClientRect().top
  let current = headings.value[0].id
  for (const h of headings.value) {
    const el = document.getElementById(h.id)
    if (!el) continue
    const top = el.getBoundingClientRect().top - rootTop
    if (top <= THRESHOLD) current = h.id
    else break // headings are in document order — nothing after qualifies
  }
  setActive(current)
}

function setActive(id) {
  if (activeId.value !== id) {
    activeId.value = id
    nextTick(updateThumb)
  }
}

function updateThumb() {
  const el = itemEls.get(activeId.value)
  const list = listRef.value
  if (!el || !list) { thumb.visible = false; return }
  thumb.top = el.offsetTop
  thumb.height = el.offsetHeight
  thumb.visible = true
}

function scrollTo(id) {
  const el = document.getElementById(id)
  if (!el) return
  const root = getScroller()
  if (root && root !== document.documentElement) {
    const top = el.getBoundingClientRect().top - root.getBoundingClientRect().top + root.scrollTop - 24
    root.scrollTo({ top, behavior: 'smooth' })
  } else {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  setActive(id)
}

let ticking = false
function onScroll() {
  if (ticking) return
  ticking = true
  requestAnimationFrame(() => { computeActive(); ticking = false })
}

let scroller = null
function bindScroll() {
  unbindScroll()
  scroller = getScroller()
  const target = scroller === document.documentElement ? window : scroller
  target?.addEventListener('scroll', onScroll, { passive: true })
  window.addEventListener('resize', onScroll, { passive: true })
}
function unbindScroll() {
  const target = scroller === document.documentElement ? window : scroller
  target?.removeEventListener('scroll', onScroll)
  window.removeEventListener('resize', onScroll)
}

async function refresh() {
  await nextTick()
  parseHeadings()
  await nextTick()
  bindScroll()
  computeActive()
  updateThumb()
}

watch(() => props.html, () => { setTimeout(refresh, 80) })
onMounted(() => setTimeout(refresh, 150))
onBeforeUnmount(unbindScroll)
</script>

<style scoped>
.toc-title {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--muted-foreground);
  margin-bottom: 10px;
}

.toc-list {
  position: relative;
  list-style: none;
  padding: 0 0 0 12px;
  margin: 0;
}

/* Static rail behind the links */
.toc-rail {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 2px;
  border-radius: 2px;
  background: var(--border);
}

/* Moving thumb that marks the active section */
.toc-rail-thumb {
  position: absolute;
  left: 0;
  top: 0;
  width: 2px;
  border-radius: 2px;
  background: var(--primary);
  transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1), height 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.toc-link {
  display: block;
  font-size: 12px;
  line-height: 1.5;
  padding: 3px 8px;
  border-radius: 4px;
  color: var(--muted-foreground);
  transition: color 0.15s ease, background 0.15s ease;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.toc-link:hover {
  color: var(--foreground);
  background: var(--muted);
}

.toc-link:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 1px;
}

.toc-link--nested {
  padding-left: 20px;
  font-size: 11.5px;
}

.toc-link--active {
  color: var(--primary);
  font-weight: 600;
}

@media (min-width: 1024px) and (max-width: 1279px) {
  .toc-link {
    font-size: 11px;
    padding: 2px 6px;
  }
  .toc-link--nested {
    padding-left: 16px;
    font-size: 10.5px;
  }
}
</style>
