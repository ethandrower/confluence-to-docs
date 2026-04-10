<template>
  <nav v-if="crumbs.length" class="breadcrumbs" aria-label="Breadcrumb">
    <RouterLink to="/docs" class="crumb">Docs</RouterLink>
    <span v-for="crumb in crumbs" :key="crumb.slug" class="crumb-item">
      <span class="separator">›</span>
      <RouterLink :to="{ name: 'doc-page', params: { slug: crumb.slug } }" class="crumb">
        {{ crumb.title }}
      </RouterLink>
    </span>
  </nav>
</template>

<script setup>
defineProps({ crumbs: { type: Array, default: () => [] } })
</script>

<style scoped>
.breadcrumbs { display: flex; align-items: center; gap: 4px; font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 1.5rem; }
.crumb { color: var(--text-secondary); text-decoration: none; }
.crumb:hover { color: var(--accent); }
.separator { margin: 0 4px; }
</style>
