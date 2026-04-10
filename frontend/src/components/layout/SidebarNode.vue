<template>
  <li>
    <div
      class="group flex items-center rounded-lg transition-colors duration-100"
      :class="isActive ? 'bg-accent text-accent-foreground' : 'hover:bg-muted/40'"
    >
      <button
        v-if="hasChildren"
        @click.stop="expanded = !expanded"
        class="shrink-0 w-5 h-5 flex items-center justify-center text-muted-foreground/30 hover:text-muted-foreground transition-colors"
        :style="{ marginLeft: `${depth * 12 + 6}px` }"
        :aria-label="expanded ? 'Collapse' : 'Expand'"
      >
        <svg
          class="w-3 h-3 transition-transform duration-150"
          :class="expanded ? 'rotate-90' : ''"
          fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"
        >
          <path stroke-linecap="round" stroke-linejoin="round" d="m9 5 7 7-7 7" />
        </svg>
      </button>
      <span v-else class="shrink-0 w-5" :style="{ marginLeft: `${depth * 12 + 6}px` }" />

      <RouterLink
        :to="{ name: 'doc-page', params: { slug: page.slug } }"
        class="flex-1 py-[6px] px-1.5 text-[13px] leading-snug truncate transition-colors duration-100"
        :class="isActive
          ? 'text-primary font-medium'
          : 'text-muted-foreground hover:text-foreground'"
      >{{ page.title }}</RouterLink>
    </div>

    <ul v-if="expanded && hasChildren" class="space-y-px">
      <SidebarNode
        v-for="child in page.children"
        :key="child.id"
        :page="child"
        :depth="depth + 1"
      />
    </ul>
  </li>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'

const props = defineProps({ page: Object, depth: Number })
const route = useRoute()
const currentSlug = computed(() => route.params.slug)
const hasChildren = computed(() => props.page.children?.length > 0)
const isActive = computed(() => currentSlug.value === props.page.slug)

function subtreeContains(page, slug) {
  if (!slug) return false
  if (page.slug === slug) return true
  return (page.children || []).some(c => subtreeContains(c, slug))
}

const expanded = ref(subtreeContains(props.page, currentSlug.value))

watch(currentSlug, (slug) => {
  if (subtreeContains(props.page, slug)) expanded.value = true
})
</script>
