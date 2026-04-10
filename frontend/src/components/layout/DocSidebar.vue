<template>
  <nav class="text-[13px]" aria-label="Documentation">
    <div v-if="store.loading" class="px-4 py-8 space-y-2">
      <div class="h-2.5 w-20 bg-muted rounded-full animate-pulse" />
      <div class="h-2.5 w-32 bg-muted/60 rounded-full animate-pulse" />
      <div class="h-2.5 w-24 bg-muted/40 rounded-full animate-pulse" />
    </div>
    <div v-else-if="store.error" class="px-4 py-8 text-destructive text-xs">{{ store.error }}</div>
    <template v-else>
      <!-- Home -->
      <ul class="space-y-px px-2 mb-2">
        <li>
          <RouterLink
            to="/docs"
            class="flex items-center gap-2 rounded-lg px-2.5 py-[6px] text-[13px] leading-snug transition-colors duration-100"
            :class="isHome
              ? 'bg-accent text-accent-foreground font-medium'
              : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'"
          >
            <svg class="w-4 h-4 shrink-0" :class="isHome ? 'text-primary' : 'text-muted-foreground/50'" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
              <path stroke-linecap="round" stroke-linejoin="round" d="m2.25 12 8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
            </svg>
            Home
          </RouterLink>
        </li>
      </ul>

      <div v-for="(section, i) in store.sections" :key="section.space_key">
        <!-- Section divider -->
        <div class="mx-4 my-2.5 border-t" />

        <!-- Section header -->
        <button
          @click="toggleSection(section.space_key)"
          class="flex items-center w-full px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/50 hover:text-muted-foreground transition-colors"
        >
          <svg
            class="w-3 h-3 mr-1.5 transition-transform duration-200"
            :class="collapsed[section.space_key] ? '' : 'rotate-90'"
            fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"
          >
            <path stroke-linecap="round" stroke-linejoin="round" d="m9 5 7 7-7 7" />
          </svg>
          {{ section.label }}
          <span class="ml-auto font-normal text-[10px] tabular-nums opacity-40">{{ countPages(section) }}</span>
        </button>

        <!-- Pages -->
        <ul v-show="!collapsed[section.space_key]" class="space-y-px px-2">
          <SidebarNode v-for="page in section.pages" :key="page.id" :page="page" :depth="0" />
        </ul>
      </div>
    </template>
  </nav>
</template>

<script setup>
import { reactive, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useDocsStore } from '@/stores/docs.js'
import SidebarNode from './SidebarNode.vue'

const store = useDocsStore()
const route = useRoute()
const isHome = computed(() => route.name === 'docs-home')
const collapsed = reactive({})

function toggleSection(key) {
  collapsed[key] = !collapsed[key]
}

function countPages(section) {
  let count = 0
  function walk(pages) {
    for (const p of pages) {
      count++
      if (p.children) walk(p.children)
    }
  }
  walk(section.pages)
  return count
}
</script>
