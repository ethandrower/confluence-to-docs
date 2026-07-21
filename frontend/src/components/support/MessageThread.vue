<template>
  <div class="mt-scroll-wrap">
    <ol ref="containerRef" class="mt-thread" role="list" @scroll="checkAtBottom">
      <li v-for="item in items" :key="item.key" class="mt-item">
        <!-- Day divider -->
        <div v-if="item.kind === 'day'" class="mt-day"><span>{{ item.label }}</span></div>

        <!-- New divider (customer only) -->
        <div v-else-if="item.kind === 'new'" class="mt-new"><span>New</span></div>

        <!-- Message group -->
        <div v-else class="mt-group" :class="{ 'mt-group--mine': item.mine, 'mt-group--internal': item.isInternal }">
          <div class="mt-cap">
            <span v-if="item.badge === 'Internal'" class="mt-badge mt-badge--internal">Internal</span>
            <span v-else-if="item.badge === 'CiteMed'" class="mt-badge">CiteMed</span>
            <span v-if="item.viaEmail" class="mt-badge mt-badge--email">via email</span>
            <span class="mt-name">{{ item.name }}</span>
            <span class="mt-time">{{ item.time }}</span>
          </div>
          <div v-for="m in item.messages" :key="m.id" class="mt-bub" :class="{ 'mt-bub--pending': m.pending, 'mt-bub--fresh': isFresh(m) }" :title="fullDate(m.created_at)">
            <p class="mt-body"><template v-for="(seg, i) in linkify(clean(m.body))" :key="i"><a v-if="seg.type === 'link'" :href="seg.value" target="_blank" rel="noopener nofollow ugc" class="mt-link">{{ seg.value }}</a><template v-else>{{ seg.value }}</template></template></p>

            <!-- admin: delivery status + retry -->
            <div v-if="perspective === 'admin' && m.is_staff && (m.delivery_status === 'delivered' || m.delivery_status === 'sent')" class="mt-delivery mt-delivery--ok" aria-live="polite">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>
              {{ m.delivery_status === 'delivered' ? 'Delivered' : 'Sent' }}
            </div>
            <div v-else-if="perspective === 'admin' && m.is_staff && (m.delivery_status === 'failed' || m.delivery_status === 'bounced')" class="mt-delivery mt-delivery--fail" aria-live="polite">
              <span>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 9v4m0 4h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"/></svg>
                {{ m.delivery_status === 'bounced' ? 'Bounced' : 'Not delivered' }}<span v-if="m.delivery_detail" class="mt-delivery-detail"> · {{ m.delivery_detail }}</span>
              </span>
              <button class="mt-retry" :disabled="m.pending || props.resendingId === m.id" @click="$emit('resend', m)">{{ props.resendingId === m.id ? 'Retrying…' : 'Retry' }}</button>
            </div>
            <span v-if="m.pending" class="mt-pending">Sending…</span>
          </div>
        </div>
      </li>
      <li v-if="!messages.length" class="mt-empty">No messages yet.</li>
    </ol>
    <button v-if="showNewPill" type="button" class="mt-newpill" @click="scrollToBottom(true)">New messages ↓</button>
    <span class="sr-only" role="status" aria-live="polite">{{ showNewPill ? 'New messages below' : '' }}</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { linkify } from '@/lib/linkify'
import { groupMessages, stripSignature } from '@/lib/thread'
import { fullDate } from '@/lib/ticketStatus'
import { useThreadScroll } from '@/lib/useThreadScroll'

const props = defineProps({
  messages: { type: Array, required: true },
  perspective: { type: String, required: true },
  lastReadAt: { type: String, default: null },
  freshIds: { type: Object, default: null },
  resendingId: { type: [String, Number], default: null },
})
defineEmits(['resend'])

const items = computed(() => groupMessages(props.messages, props.perspective, { lastReadAt: props.lastReadAt }))
function clean(body) { return stripSignature(body) }
function isFresh(m) { return !!(props.freshIds && props.freshIds.has(m.id)) }

const { containerRef, showNewPill, checkAtBottom, scrollToBottom, resetToBottom } =
  useThreadScroll(() => props.messages.length)

defineExpose({ scrollToBottom, resetToBottom })
</script>

<script>
export default { name: 'MessageThread' }
</script>

<style scoped>
.mt-scroll-wrap { position: relative; flex: 1 1 auto; min-height: 0; display: flex; }
/* Bottom-anchored: justify-content flex-end keeps short threads resting above the composer. */
.mt-thread { list-style: none; margin: 0; padding: 20px 16px; display: flex; flex-direction: column; gap: 4px; flex: 1 1 auto; min-height: 0; overflow-y: auto; justify-content: flex-end; background: color-mix(in srgb, var(--muted) 45%, var(--background)); }
.mt-thread > .mt-item:first-child { margin-top: auto; } /* push content down when short */
.mt-item { display: contents; }

.mt-day, .mt-new { display: flex; align-items: center; gap: 10px; margin: 10px 2px 8px; font-size: 11px; font-weight: 600; }
.mt-day { color: var(--muted-foreground); }
.mt-day span { flex-shrink: 0; }
.mt-day::before, .mt-day::after { content: ""; height: 1px; flex: 1; background: var(--border); }
.mt-new { color: var(--brand-accent); font-weight: 700; }
.mt-new::before, .mt-new::after { content: ""; height: 1px; flex: 1; background: color-mix(in srgb, var(--brand-accent) 40%, transparent); }

.mt-group { max-width: min(82%, 560px); margin-bottom: 8px; }
.mt-group--mine { align-self: flex-end; }
.mt-group:not(.mt-group--mine) { align-self: flex-start; }

.mt-cap { display: flex; align-items: baseline; gap: 7px; margin: 0 4px 4px; flex-wrap: wrap; }
.mt-group--mine .mt-cap { justify-content: flex-end; }
.mt-badge { font-size: 0.62rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em; padding: 1px 6px; border-radius: 999px; color: var(--info); background: color-mix(in srgb, var(--info) 16%, transparent); }
.mt-badge--internal { color: var(--warning); background: color-mix(in srgb, var(--warning) 18%, transparent); }
.mt-badge--email { color: var(--muted-foreground); background: color-mix(in srgb, var(--muted-foreground) 14%, transparent); }
.mt-name { font-size: 0.8rem; font-weight: 600; color: var(--foreground); }
.mt-time { font-size: 0.72rem; color: var(--muted-foreground); }

/* Option B — true chat bubbles: no borders, tinted fills only. */
.mt-bub { border-radius: 16px; padding: 9px 13px; font-size: 0.9rem; line-height: 1.55; margin-bottom: 3px; background: var(--bubble-theirs); color: var(--bubble-theirs-foreground); border: none; border-bottom-left-radius: 5px; }
.mt-group--mine .mt-bub { background: var(--bubble-mine); color: var(--bubble-mine-foreground); border-bottom-left-radius: 16px; border-bottom-right-radius: 5px; margin-left: auto; }
/* Internal notes keep only a semantic left accent, not a full border. */
.mt-group--internal .mt-bub { background: color-mix(in srgb, var(--warning) 10%, var(--card)); color: var(--foreground); border-left: 3px solid var(--warning); }
.mt-bub--pending { opacity: 0.6; }
.mt-bub--fresh { animation: mt-flash 1.2s ease; }
@keyframes mt-flash { from { box-shadow: 0 0 0 3px color-mix(in srgb, var(--brand-accent) 35%, transparent); } to { box-shadow: 0 0 0 0 transparent; } }
@media (prefers-reduced-motion: reduce) { .mt-bub--fresh { animation: none; } }

.mt-body { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.mt-link { color: var(--brand-accent); text-decoration: underline; }
.mt-group--mine .mt-link { color: var(--bubble-mine-link); }
.mt-pending { display: block; font-size: 0.68rem; margin-top: 3px; opacity: 0.8; }

.mt-delivery { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 8px; padding-top: 7px; border-top: 1px solid var(--border); font-size: 0.7rem; font-weight: 600; }
.mt-delivery svg { width: 12px; height: 12px; flex-shrink: 0; vertical-align: -1px; margin-right: 3px; }
.mt-delivery--ok { color: var(--muted-foreground); }
.mt-delivery--fail { color: var(--destructive); }
.mt-delivery-detail { font-weight: 400; color: var(--muted-foreground); }
.mt-retry { flex-shrink: 0; font: inherit; font-size: 0.7rem; font-weight: 600; color: var(--destructive); background: none; border: 1px solid color-mix(in srgb, var(--destructive) 40%, transparent); border-radius: var(--radius-sm); padding: 2px 9px; cursor: pointer; }
.mt-retry:hover:not(:disabled) { background: color-mix(in srgb, var(--destructive) 10%, transparent); }
.mt-retry:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
.mt-retry:disabled { opacity: 0.6; cursor: default; }

.mt-empty { align-self: center; color: var(--muted-foreground); font-size: 0.88rem; padding: 24px 0; }

.mt-newpill { position: absolute; left: 50%; bottom: 12px; transform: translateX(-50%); display: inline-flex; align-items: center; gap: 6px; font: inherit; font-size: 0.78rem; font-weight: 600; color: var(--primary-foreground); background: var(--primary); border: none; border-radius: 999px; padding: 6px 14px; cursor: pointer; box-shadow: 0 2px 8px color-mix(in srgb, var(--foreground) 18%, transparent); }
.mt-newpill:hover { filter: brightness(0.95); }
.mt-newpill:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }

.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }

@media (max-width: 700px) {
  .mt-group { max-width: 82%; }
}
</style>
