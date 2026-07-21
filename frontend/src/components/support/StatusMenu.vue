<template>
  <DropdownMenuRoot>
    <DropdownMenuTrigger
      :disabled="disabled"
      class="sm-chip"
      :class="`status--${statusTone(status, 'staff')}`"
      aria-label="Change ticket status"
    >
      <span class="dot" aria-hidden="true" />
      {{ statusLabel(status, 'staff') }}
      <svg class="car" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>
    </DropdownMenuTrigger>
    <DropdownMenuPortal>
      <DropdownMenuContent class="sm-menu" align="end" :side-offset="6">
        <DropdownMenuItem
          v-for="s in STATUS_KEYS"
          :key="s"
          class="sm-item"
          :class="{ 'sm-item--on': s === status }"
          @select="$emit('change', s)"
        >
          <span class="sm-dot" :class="`status--${statusTone(s, 'staff')}`" aria-hidden="true" />
          <span class="sm-label">{{ statusLabel(s, 'staff') }}</span>
          <svg v-if="s === status" class="sm-ck" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>
        </DropdownMenuItem>
        <p class="sm-hint">Set here — shown to the customer. Independent of any linked Jira issue.</p>
      </DropdownMenuContent>
    </DropdownMenuPortal>
  </DropdownMenuRoot>
</template>

<script setup>
import { DropdownMenuRoot, DropdownMenuTrigger, DropdownMenuPortal, DropdownMenuContent, DropdownMenuItem } from 'reka-ui'
import { statusLabel, statusTone, STATUS_KEYS } from '@/lib/ticketStatus'

defineProps({
  status: { type: String, required: true },
  disabled: { type: Boolean, default: false },
})
defineEmits(['change'])
</script>

<script>
export default { name: 'StatusMenu' }
</script>

<style scoped>
/* Trigger chip — mirrors the old .atd-status filled chip, now interactive. */
.sm-chip { display: inline-flex; align-items: center; gap: 6px; font-family: var(--font-ui); font-size: 0.76rem; font-weight: 650; white-space: nowrap; padding: 4px 10px; border-radius: 999px; border: 1px solid transparent; cursor: pointer; transition: filter 0.15s, border-color 0.15s; }
.sm-chip:hover:not(:disabled) { filter: brightness(0.97); }
.sm-chip:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
.sm-chip:disabled { opacity: 0.6; cursor: default; }
.sm-chip .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.sm-chip .car { width: 12px; height: 12px; opacity: 0.75; }
/* tone fills — same mapping as the admin status chip today */
.sm-chip.status--success { color: var(--success); background: color-mix(in srgb, var(--success) 13%, transparent); }
.sm-chip.status--warning { color: var(--warning); background: color-mix(in srgb, var(--warning) 15%, transparent); }
.sm-chip.status--info { color: var(--info); background: color-mix(in srgb, var(--info) 13%, transparent); }
.sm-chip.status--muted { color: var(--muted-foreground); background: color-mix(in srgb, var(--muted-foreground) 13%, transparent); }

/* Menu */
.sm-menu { min-width: 240px; background: var(--card); border: 1px solid var(--border); border-radius: var(--radius-md); box-shadow: 0 10px 30px color-mix(in srgb, var(--foreground) 14%, transparent); padding: 5px; z-index: 50; }
.sm-item { display: flex; align-items: center; gap: 9px; padding: 8px 9px; border-radius: var(--radius-sm); font-size: 0.85rem; color: var(--foreground); cursor: pointer; outline: none; }
.sm-item[data-highlighted], .sm-item:hover { background: var(--accent); }
.sm-item--on { background: color-mix(in srgb, var(--primary) 7%, transparent); }
.sm-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
.sm-dot.status--success { color: var(--success); }
.sm-dot.status--warning { color: var(--warning); }
.sm-dot.status--info { color: var(--info); }
.sm-dot.status--muted { color: var(--muted-foreground); }
.sm-label { flex: 1 1 auto; }
.sm-ck { width: 14px; height: 14px; color: var(--primary); flex-shrink: 0; }
.sm-hint { margin: 4px 4px 2px; padding: 8px 6px 4px; border-top: 1px solid var(--border); font-size: 0.72rem; line-height: 1.45; color: var(--muted-foreground); }
</style>
