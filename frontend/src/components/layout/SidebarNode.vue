<template>
  <li class="list-none">
    <div
      class="flex items-center gap-1 pr-2 rounded-md group"
      :style="{ paddingLeft: `${depth * 14 + 8}px` }"
    >
      <button
        v-if="page.children && page.children.length"
        @click="expanded = !expanded"
        :aria-expanded="expanded"
        class="flex-shrink-0 w-5 h-5 flex items-center justify-center rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
      >
        <svg
          class="w-3 h-3 transition-transform duration-150"
          :class="expanded ? 'rotate-90' : ''"
          fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"
        >
          <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
        </svg>
      </button>
      <span v-else class="flex-shrink-0 w-5" />

      <RouterLink
        :to="{ name: 'doc-page', params: { slug: page.slug } }"
        class="flex-1 py-1.5 text-sm truncate rounded-md no-underline transition-colors"
        :class="currentSlug === page.slug
          ? 'text-blue-600 font-medium'
          : 'text-gray-700 hover:text-gray-900'"
      >{{ page.title }}</RouterLink>
    </div>

    <ul v-if="expanded && page.children && page.children.length" class="list-none m-0 p-0">
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

function subtreeContains(page, slug) {
  if (!slug) return false
  if (page.slug === slug) return true
  return (page.children || []).some(child => subtreeContains(child, slug))
}

const expanded = ref(subtreeContains(props.page, currentSlug.value))

// When navigating into this subtree, expand — but don't collapse when leaving
watch(currentSlug, (slug) => {
  if (subtreeContains(props.page, slug)) {
    expanded.value = true
  }
})
</script>
