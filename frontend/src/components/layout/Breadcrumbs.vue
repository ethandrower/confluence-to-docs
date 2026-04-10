<template>
  <nav v-if="crumbs.length" class="flex items-center gap-1.5 text-[13px] text-muted-foreground/60 mb-4" aria-label="Breadcrumb">
    <RouterLink to="/docs" class="hover:text-foreground transition-colors shrink-0">Docs</RouterLink>
    <template v-for="(crumb, i) in crumbs" :key="crumb.slug">
      <svg class="w-3 h-3 opacity-30 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="m9 5 7 7-7 7" />
      </svg>
      <RouterLink
        v-if="i < crumbs.length - 1"
        :to="{ name: 'doc-page', params: { slug: crumb.slug } }"
        class="hover:text-foreground transition-colors truncate max-w-[160px]"
      >{{ crumb.title }}</RouterLink>
      <span v-else class="text-muted-foreground truncate max-w-[200px]">{{ crumb.title }}</span>
    </template>
  </nav>
</template>

<script setup>
defineProps({ crumbs: { type: Array, default: () => [] } })
</script>
