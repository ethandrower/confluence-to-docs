<template>
  <div v-if="headings.length">
    <p class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/40 mb-3">On this page</p>
    <ul class="space-y-0.5">
      <li v-for="h in headings" :key="h.id">
        <a
          :href="`#${h.id}`"
          @click.prevent="scrollTo(h.id)"
          class="block text-[12.5px] leading-relaxed py-0.5 border-l-2 transition-all duration-150"
          :class="[
            h.level === 3 ? 'pl-4' : 'pl-3',
            activeId === h.id
              ? 'border-primary text-foreground font-medium'
              : 'border-transparent text-muted-foreground/50 hover:text-foreground hover:border-border'
          ]"
        >{{ h.text }}</a>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onBeforeUnmount, watch } from 'vue'

const props = defineProps({ html: String })
const activeId = ref('')

const headings = computed(() => {
  if (!props.html || typeof document === 'undefined') return []
  const div = document.createElement('div')
  div.innerHTML = props.html
  return [...div.querySelectorAll('h2, h3')].map(h => ({
    id: h.id || h.textContent.toLowerCase().replace(/\s+/g, '-').replace(/[^\w-]/g, ''),
    text: h.textContent,
    level: parseInt(h.tagName[1])
  }))
})

function scrollTo(id) {
  const el = document.getElementById(id)
  if (!el) return
  // Content scrolls inside <main>, not window
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
  observer = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (e.isIntersecting) activeId.value = e.target.id
      }
    },
    { rootMargin: '-64px 0px -80% 0px' }
  )
  headings.value.forEach(h => {
    const el = document.getElementById(h.id)
    if (el) observer.observe(el)
  })
}

watch(headings, () => setTimeout(setupObserver, 100))
onMounted(() => setTimeout(setupObserver, 200))
onBeforeUnmount(() => observer?.disconnect())
</script>
