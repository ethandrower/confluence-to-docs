<template>
  <button
    type="button"
    @click="toggleTheme"
    class="theme-toggle"
    :aria-label="theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'"
    :title="theme === 'dark' ? 'Light theme' : 'Dark theme'"
  >
    <!-- Sun (shown in dark mode → click for light) -->
    <svg v-if="theme === 'dark'" class="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path stroke-linecap="round" d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M4.93 19.07l1.41-1.41m11.32-11.32 1.41-1.41" />
    </svg>
    <!-- Moon (shown in light mode → click for dark) -->
    <svg v-else class="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
      <path stroke-linecap="round" stroke-linejoin="round" d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79Z" />
    </svg>
  </button>
</template>

<script setup>
import { useTheme } from '@/lib/useTheme.js'
const { theme, toggleTheme } = useTheme()
</script>

<style scoped>
.theme-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  color: var(--muted-foreground);
  transition: color 0.15s, background 0.15s;
}
.theme-toggle:hover {
  color: var(--foreground);
  background: var(--muted);
}
.theme-toggle:focus-visible {
  outline: 2px solid var(--ring);
  outline-offset: 2px;
}
</style>
