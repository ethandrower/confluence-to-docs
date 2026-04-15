<template>
  <div v-if="versions.length > 1" class="version-switcher">
    <button
      ref="triggerRef"
      @click="open = !open"
      class="version-trigger"
      :aria-expanded="open"
      aria-haspopup="listbox"
    >
      <svg class="w-3.5 h-3.5 text-primary/70" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M9.568 3H5.25A2.25 2.25 0 0 0 3 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 0 0 5.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 0 0 9.568 3Z" />
        <path stroke-linecap="round" stroke-linejoin="round" d="M6 6h.008v.008H6V6Z" />
      </svg>
      <span class="version-label">{{ selected || 'Version' }}</span>
      <svg
        class="w-3 h-3 text-muted-foreground transition-transform duration-150"
        :class="open ? 'rotate-180' : ''"
        fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"
      >
        <path stroke-linecap="round" stroke-linejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
      </svg>
    </button>

    <Transition name="dropdown">
      <div v-if="open" class="version-dropdown" role="listbox" :aria-label="`Select documentation version for ${spaceLabel}`">
        <button
          v-for="v in versions"
          :key="v.label"
          role="option"
          :aria-selected="v.label === selected"
          class="version-option"
          :class="v.label === selected ? 'version-option--active' : ''"
          @click="select(v)"
        >
          <span class="version-option-label">{{ v.label }}</span>
          <span v-if="v.is_latest" class="version-badge">latest</span>
          <svg v-if="v.label === selected" class="w-3.5 h-3.5 text-primary ml-auto shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="m4.5 12.75 6 6 9-13.5" />
          </svg>
        </button>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useDocsStore } from '@/stores/docs.js'

const props = defineProps({
  spaceKey: String,
  spaceLabel: String,
})

const store = useDocsStore()
const router = useRouter()
const open = ref(false)
const triggerRef = ref(null)

const versions = computed(() => store.getVersionsForSpace(props.spaceKey))
const selected = computed(() => store.getSelectedVersion(props.spaceKey))

function select(v) {
  store.selectVersion(props.spaceKey, v.label)
  open.value = false
  // Navigate to the version root page
  router.push({ name: 'doc-page', params: { slug: v.slug } })
}

// Close on click outside
function onClickOutside(e) {
  if (triggerRef.value && !triggerRef.value.parentElement.contains(e.target)) {
    open.value = false
  }
}

onMounted(() => document.addEventListener('click', onClickOutside))
onBeforeUnmount(() => document.removeEventListener('click', onClickOutside))
</script>

<style scoped>
.version-switcher {
  position: relative;
  margin: 0 8px 4px;
}

.version-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 5px 8px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  color: var(--muted-foreground);
  background: var(--muted);
  border: 1px solid var(--border);
  transition: all 0.15s;
  cursor: pointer;
}

.version-trigger:hover {
  background: var(--accent);
  color: var(--foreground);
}

.version-label {
  flex: 1;
  text-align: left;
}

.version-dropdown {
  position: absolute;
  z-index: 50;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  background: var(--popover);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 4px;
  box-shadow: 0 4px 12px oklch(0 0 0 / 0.08), 0 1px 3px oklch(0 0 0 / 0.04);
}

.version-option {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 6px 8px;
  border-radius: 5px;
  font-size: 12px;
  color: var(--foreground);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: background 0.1s;
}

.version-option:hover {
  background: var(--accent);
}

.version-option--active {
  font-weight: 600;
  color: var(--primary);
}

.version-option-label {
  font-variant-numeric: tabular-nums;
}

.version-badge {
  font-size: 10px;
  font-weight: 600;
  color: var(--primary);
  background: var(--accent);
  padding: 1px 6px;
  border-radius: 4px;
  letter-spacing: 0.02em;
}

/* Dropdown transition */
.dropdown-enter-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.dropdown-leave-active {
  transition: opacity 0.1s ease, transform 0.1s ease;
}
.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
