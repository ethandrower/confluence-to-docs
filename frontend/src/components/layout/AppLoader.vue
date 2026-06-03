<template>
  <Transition name="loader-fade" @after-leave="$emit('done')">
    <div v-if="visible" class="loader" role="status" aria-live="polite">
      <span class="sr-only">Loading CiteMed documentation…</span>

      <div class="loader-stage" aria-hidden="true">
        <div class="loader-mark" :class="{ settled }">
          <span class="lb lb-left">[</span><span class="lc">cite</span><span class="lb lb-right">]</span><span class="lm">med</span>
        </div>
        <div class="loader-rule"></div>
        <div class="loader-caption">Support Documentation</div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { ref, onMounted } from 'vue'

defineEmits(['done'])

const visible = ref(true)
const settled = ref(false)

onMounted(() => {
  // Plays on every full page load / refresh. (App.vue mounts once per page
  // load, so this never replays on in-app SPA navigation.)
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const hold = reduce ? 650 : 1450

  // Brief settle pulse just before exit.
  setTimeout(() => { settled.value = true }, reduce ? 300 : 1150)
  setTimeout(() => { visible.value = false }, hold)
})
</script>

<style scoped>
.loader {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--background);
}

.loader-stage {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.loader-mark {
  font-family: var(--font-ui);
  font-weight: 700;
  font-size: clamp(2.75rem, 9vw, 4.25rem);
  letter-spacing: -0.03em;
  line-height: 1;
  color: var(--primary);
  display: inline-flex;
  align-items: baseline;
  white-space: nowrap;
}
.loader-mark.settled { animation: settle 0.5s cubic-bezier(0.34, 1.56, 0.64, 1); }

/* Brackets sweep inward to "cite" a reference, [ cite ] */
.lb {
  display: inline-block;
  opacity: 0;
  font-weight: 500;
}
.lb-left  { animation: bracketIn-l 0.62s cubic-bezier(0.16, 1, 0.3, 1) 0.08s both; }
.lb-right { animation: bracketIn-r 0.62s cubic-bezier(0.16, 1, 0.3, 1) 0.08s both; }

.lc {
  display: inline-block;
  opacity: 0;
  animation: rise 0.55s cubic-bezier(0.22, 1, 0.36, 1) 0.26s both;
}
.lm {
  display: inline-block;
  opacity: 0;
  animation: rise 0.55s cubic-bezier(0.22, 1, 0.36, 1) 0.42s both;
}

/* Hairline accent rule draws outward from the centre */
.loader-rule {
  margin-top: 18px;
  width: clamp(140px, 22vw, 220px);
  height: 2px;
  border-radius: 2px;
  background: var(--brand-accent);
  transform: scaleX(0);
  transform-origin: center;
  animation: drawRule 0.7s cubic-bezier(0.65, 0, 0.35, 1) 0.6s both;
}

.loader-caption {
  margin-top: 14px;
  font-family: var(--font-ui);
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--muted-foreground);
  opacity: 0;
  animation: fadeCaption 0.6s ease 0.85s both;
}

@keyframes bracketIn-l {
  0%   { opacity: 0; transform: translateX(-30px) scaleY(0.7); }
  60%  { opacity: 1; }
  100% { opacity: 1; transform: translateX(0) scaleY(1); }
}
@keyframes bracketIn-r {
  0%   { opacity: 0; transform: translateX(30px) scaleY(0.7); }
  60%  { opacity: 1; }
  100% { opacity: 1; transform: translateX(0) scaleY(1); }
}
@keyframes rise {
  0%   { opacity: 0; transform: translateY(10px); filter: blur(3px); }
  100% { opacity: 1; transform: translateY(0); filter: blur(0); }
}
@keyframes drawRule {
  0%   { transform: scaleX(0); opacity: 0.6; }
  100% { transform: scaleX(1); opacity: 1; }
}
@keyframes fadeCaption {
  0%   { opacity: 0; transform: translateY(4px); }
  100% { opacity: 0.85; transform: translateY(0); }
}
@keyframes settle {
  0%   { transform: scale(1); }
  40%  { transform: scale(1.035); }
  100% { transform: scale(1); }
}

/* Exit */
.loader-fade-leave-active { transition: opacity 0.45s ease, transform 0.45s ease; }
.loader-fade-leave-to { opacity: 0; transform: scale(1.015); }

.sr-only {
  position: absolute;
  width: 1px; height: 1px;
  padding: 0; margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

@media (prefers-reduced-motion: reduce) {
  .lb, .lc, .lm, .loader-rule, .loader-caption { animation: none; opacity: 1; transform: none; }
  .loader-rule { transform: scaleX(1); }
  .loader-mark.settled { animation: none; }
}
</style>
