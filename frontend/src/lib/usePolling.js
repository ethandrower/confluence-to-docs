import { onBeforeUnmount } from 'vue'

/**
 * Visibility-gated interval polling.
 *
 * Runs `fn` every `intervalMs` while the tab is visible AND `enabled()` is true.
 * Fires once immediately when the tab regains visibility or the network returns,
 * so refocusing feels instant. Never starts a new run while the previous is still
 * in flight. Cleans up its timer and listeners on component unmount.
 *
 * @param {() => (void|Promise<void>)} fn
 * @param {{ intervalMs: number, enabled?: () => boolean }} opts
 * @returns {{ pause: () => void, resume: () => void }}
 */
export function usePolling(fn, { intervalMs, enabled = () => true }) {
  let timer = null
  let inFlight = false
  let paused = false

  const canRun = () =>
    !paused && document.visibilityState === 'visible' && enabled()

  async function tick() {
    if (!canRun() || inFlight) return
    inFlight = true
    try {
      await fn()
    } catch {
      // Transient failure — swallow; the next tick retries.
    } finally {
      inFlight = false
    }
  }

  function start() {
    if (timer != null) return
    timer = setInterval(tick, intervalMs)
  }
  function stop() {
    if (timer != null) {
      clearInterval(timer)
      timer = null
    }
  }

  function onVisibility() {
    if (document.visibilityState === 'visible') {
      start()
      tick() // immediate refresh on refocus
    } else {
      stop()
    }
  }
  function onOnline() {
    tick()
    if (document.visibilityState === 'visible') start()
  }
  function onOffline() {
    stop()
  }

  function pause() {
    paused = true
    stop()
  }
  function resume() {
    paused = false
    if (document.visibilityState === 'visible') {
      start()
      tick()
    }
  }

  document.addEventListener('visibilitychange', onVisibility)
  window.addEventListener('online', onOnline)
  window.addEventListener('offline', onOffline)

  // Kick off if we mount while visible.
  if (document.visibilityState === 'visible') start()

  onBeforeUnmount(() => {
    stop()
    document.removeEventListener('visibilitychange', onVisibility)
    window.removeEventListener('online', onOnline)
    window.removeEventListener('offline', onOffline)
  })

  return { pause, resume }
}
