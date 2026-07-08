import { ref, watch, nextTick, onMounted } from 'vue'

/**
 * At-bottom-aware scrolling for a chat-style thread.
 *
 * Bind `containerRef` to the scroll element and `checkAtBottom` to its @scroll.
 * When `getLength()` grows: auto-scroll to newest if the user is already at the
 * bottom, otherwise raise `showNewPill` so the caller can offer a "jump down"
 * affordance. Honors prefers-reduced-motion (no smooth scroll).
 *
 * @param {() => number} getLength reactive message-count getter
 * @returns {{
 *   containerRef: import('vue').Ref,
 *   atBottom: import('vue').Ref<boolean>,
 *   showNewPill: import('vue').Ref<boolean>,
 *   checkAtBottom: () => void,
 *   scrollToBottom: (smooth?: boolean) => void,
 *   resetToBottom: () => void,
 * }}
 */
export function useThreadScroll(getLength) {
  const containerRef = ref(null)
  const atBottom = ref(true)
  const showNewPill = ref(false)

  const prefersReducedMotion =
    typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

  function checkAtBottom() {
    const el = containerRef.value
    if (!el) return
    atBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 40
    if (atBottom.value) showNewPill.value = false
  }

  function scrollToBottom(smooth = true) {
    const el = containerRef.value
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: smooth && !prefersReducedMotion ? 'smooth' : 'auto' })
    showNewPill.value = false
  }

  function resetToBottom() {
    atBottom.value = true
    showNewPill.value = false
    nextTick(() => scrollToBottom(false))
  }

  // On growth: stick to bottom if already there, else offer the pill.
  watch(getLength, (next, prev) => {
    if (next <= prev) return
    nextTick(() => {
      if (atBottom.value) scrollToBottom(true)
      else showNewPill.value = true
    })
  })

  onMounted(() => nextTick(() => scrollToBottom(false)))

  return { containerRef, atBottom, showNewPill, checkAtBottom, scrollToBottom, resetToBottom }
}
