<template>
  <li :class="['tree-item', { 'tree-item--active': isActive, 'tree-item--in-path': isInSubtree }]">
    <div class="tree-row group" :class="isActive ? 'bg-accent' : 'hover:bg-muted'">
      <button
        v-if="hasChildren"
        @click.stop="expanded = !expanded"
        class="tree-toggle"
        :class="isActive || isInSubtree ? 'text-primary/70' : 'text-muted-foreground/30 hover:text-muted-foreground'"
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

      <RouterLink
        :to="{ name: 'doc-page', params: { slug: page.slug } }"
        :title="page.title"
        class="tree-label"
        :class="isActive
          ? 'text-primary font-semibold'
          : 'text-muted-foreground hover:text-foreground'"
        :data-sidebar-active="isActive || undefined"
      >{{ page.title }}</RouterLink>
      <span
        v-if="hasChildren && !expanded"
        class="tree-badge"
      >{{ childCount }}</span>
    </div>

    <ul v-if="expanded && hasChildren" class="tree-children">
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
const isInSubtree = computed(() => !isActive.value && subtreeContains(props.page, currentSlug.value))
const childCount = computed(() => {
  if (!hasChildren.value) return 0
  let n = 0
  function walk(pages) { for (const p of pages) { n++; if (p.children) walk(p.children) } }
  walk(props.page.children)
  return n
})

function subtreeContains(page, slug) {
  if (!slug) return false
  if (page.slug === slug) return true
  return (page.children || []).some(c => subtreeContains(c, slug))
}

// Auto-collapse deep branches not in the current path
// Depth 3+ starts collapsed unless you're navigating within it
const inPath = subtreeContains(props.page, currentSlug.value)
const expanded = ref(props.depth < 3 ? inPath : inPath)

watch(currentSlug, (slug) => {
  if (subtreeContains(props.page, slug)) expanded.value = true
})
</script>

<style scoped>
/*
 * Git-graph tree connector system.
 * Based on https://iamkate.com/code/tree-views/
 * Uses border-left for trunk, ::before for L-connector, ::after for node dot.
 */

.tree-item {
  --tree-spacing: 14px;
  --tree-node: 5px;
  --tree-line-color: var(--border);
  display: block;
  position: relative;
}

.tree-item--active {
  --tree-line-color: oklch(0.52 0.20 260 / 0.35);
  --tree-node-color: oklch(0.52 0.20 260);
}

.tree-item--in-path {
  --tree-line-color: oklch(0.52 0.20 260 / 0.2);
}

/* Row layout */
.tree-row {
  display: flex;
  align-items: center;
  position: relative;
  border-radius: 6px;
  margin: 0 4px;
  transition: background-color 0.1s;
}

.tree-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  transition: color 0.15s;
}

.tree-label {
  flex: 1;
  min-width: 0;
  padding: 5px 6px;
  font-size: 13px;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color 0.1s;
}

/* Slightly smaller text at deep levels */
.tree-children .tree-children .tree-children .tree-label {
  font-size: 12.5px;
}

/* Child count badge on collapsed items */
.tree-badge {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 600;
  color: var(--muted-foreground);
  opacity: 0.5;
  padding: 0 4px;
  margin-right: 4px;
  font-variant-numeric: tabular-nums;
}

/* ── Children container: draws the vertical trunk via border-left ── */

.tree-children {
  margin-left: calc(var(--tree-spacing) + 6px);
  padding-left: 0;
  list-style: none;
}

.tree-children > .tree-item {
  border-left: 1.5px solid var(--tree-line-color);
  padding-left: calc(var(--tree-spacing));
}

/* Last child: stop the trunk */
.tree-children > .tree-item:last-child {
  border-left-color: transparent;
}

/* ── L-shaped connector (::before) ── */
/* Draws from the trunk left edge, curves to the right toward the node */

.tree-children > .tree-item::before {
  content: '';
  display: block;
  position: absolute;
  top: 0;
  left: -1.5px;
  width: calc(var(--tree-spacing) - var(--tree-node));
  height: calc(50% + 1px);
  border: solid var(--tree-line-color);
  border-width: 0 0 1.5px 1.5px;
  border-bottom-left-radius: 8px;
}

/* ── Node circle (::after) ── */
/* Sits at the end of the L-connector */

.tree-children > .tree-item::after {
  content: '';
  display: block;
  position: absolute;
  top: calc(50% - var(--tree-node) / 2);
  left: calc(var(--tree-spacing) - var(--tree-node) - 2px);
  width: var(--tree-node);
  height: var(--tree-node);
  border-radius: 50%;
  background: var(--tree-line-color);
  z-index: 1;
}

/* Active node: bigger + colored */
.tree-children > .tree-item--active::after {
  --tree-node: 7px;
  background: var(--tree-node-color, oklch(0.52 0.20 260));
  box-shadow: 0 0 0 3px oklch(0.52 0.20 260 / 0.12);
}

/* In-path node: slightly bigger */
.tree-children > .tree-item--in-path::after {
  --tree-node: 6px;
  background: oklch(0.52 0.20 260 / 0.4);
}
</style>
