<template>
  <nav v-if="headings.length" aria-label="Table of contents">
    <p class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">On this page</p>
    <ul class="toc-list">
      <li v-for="h in headings" :key="h.id">
        <a
          :href="`#${h.id}`"
          @click.prevent="scrollTo(h.id)"
          class="toc-link"
          :class="[
            h.level === 3 ? 'toc-link--nested' : '',
            activeId === h.id ? 'toc-link--active' : ''
          ]"
        >{{ h.text }}</a>
      </li>
    </ul>
  </nav>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'

const props = defineProps({ html: String })
const activeId = ref('')
const headings = ref([])

function parseHeadings() {
  // Parse from rendered DOM instead of creating throwaway elements
  const content = document.querySelector('.confluence-content')
  if (!content) {
    // Fallback: parse from HTML string
    if (!props.html || typeof document === 'undefined') { headings.value = []; return }
    const div = document.createElement('div')
    div.innerHTML = props.html
    headings.value = [...div.querySelectorAll('h2, h3')]
      .map(h => {
        let text = h.textContent.replace(/^#\s*/, '').trim()
        return {
          id: h.id || text.toLowerCase().replace(/\s+/g, '-').replace(/[^\w-]/g, ''),
          text,
          level: parseInt(h.tagName[1])
        }
      })
      .filter(h => h.text && !h.text.includes('Image unavailable') && h.text.length > 1)
    return
  }
  headings.value = [...content.querySelectorAll('h2, h3')]
    .map(h => {
      // Strip the anchor "#" prefix that ProseContent adds
      let text = h.textContent.replace(/^#\s*/, '').trim()
      return {
        id: h.id || text.toLowerCase().replace(/\s+/g, '-').replace(/[^\w-]/g, ''),
        text,
        level: parseInt(h.tagName[1])
      }
    })
    // Filter out image placeholders and empty headings
    .filter(h => h.text && !h.text.includes('Image unavailable') && h.text.length > 1)
}

function scrollTo(id) {
  const el = document.getElementById(id)
  if (!el) return
  const main = el.closest('main')
  if (main) {
    const top = el.offsetTop - 24
    main.scrollTo({ top, behavior: 'smooth' })
  } else {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

let observer = null

function setupObserver() {
  observer?.disconnect()
  // Use the scrolling main container as root, not viewport
  const main = document.querySelector('main')
  observer = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (e.isIntersecting) activeId.value = e.target.id
      }
    },
    { root: main || null, rootMargin: '-24px 0px -80% 0px' }
  )
  headings.value.forEach(h => {
    const el = document.getElementById(h.id)
    if (el) observer.observe(el)
  })
}

watch(() => props.html, async () => {
  await nextTick()
  parseHeadings()
  setTimeout(setupObserver, 100)
})

onMounted(async () => {
  await nextTick()
  parseHeadings()
  setTimeout(setupObserver, 200)
})

onBeforeUnmount(() => observer?.disconnect())
</script>

<style scoped>
.toc-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.toc-link {
  display: block;
  font-size: 12px;
  line-height: 1.5;
  padding: 3px 8px;
  border-radius: 4px;
  color: oklch(0.35 0.015 50);
  transition: all 0.15s ease;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.toc-link:hover {
  color: var(--foreground);
  background: var(--muted);
}

.toc-link--nested {
  padding-left: 20px;
  font-size: 11.5px;
}

.toc-link--active {
  color: var(--primary);
  font-weight: 600;
  background: var(--accent);
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
