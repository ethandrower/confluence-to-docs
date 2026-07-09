import { ref, watch, onBeforeUnmount } from 'vue'

/**
 * WebSocket client for ticket nudges, with reconnect/backoff and a reactive
 * `connected` flag callers use to gate their polling fallback. Pauses while the
 * tab is hidden; reconnects on visible. Carries no ticket data — `onNudge` fires
 * and the caller refetches via the store.
 *
 * @param {string | (() => (string|null))} path WS path, or a reactive getter
 *        returning it (return null to keep the socket closed, e.g. off-route).
 * @param {(payload: any) => void} onNudge
 * @returns {{ connected: import('vue').Ref<boolean> }}
 */
export function useTicketChannel(path, onNudge) {
  const connected = ref(false)
  const pathOf = typeof path === 'function' ? path : () => path
  let ws = null
  let retry = 0
  let reconnectTimer = null
  let stopped = false

  const wsUrl = (p) => {
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws'
    return `${scheme}://${location.host}${p}`
  }

  function clearReconnect() {
    if (reconnectTimer != null) { clearTimeout(reconnectTimer); reconnectTimer = null }
  }

  function open() {
    const path = pathOf()
    if (stopped || !path || document.visibilityState !== 'visible') return
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
    try {
      ws = new WebSocket(wsUrl(path))
    } catch {
      scheduleReconnect(); return
    }
    ws.onopen = () => { connected.value = true; retry = 0; onNudge({ type: 'reconnect' }) }
    ws.onmessage = (e) => {
      let payload = null
      try { payload = JSON.parse(e.data) } catch { return }
      onNudge(payload)
    }
    ws.onclose = () => { connected.value = false; ws = null; scheduleReconnect() }
    ws.onerror = () => { try { ws && ws.close() } catch {} }
  }

  function scheduleReconnect() {
    if (stopped || document.visibilityState !== 'visible') return
    clearReconnect()
    const delay = Math.min(1000 * 2 ** retry, 30000)  // 1s,2s,4s,…,cap 30s
    retry += 1
    reconnectTimer = setTimeout(open, delay)
  }

  function close() {
    clearReconnect()
    if (ws) { try { ws.onclose = null; ws.close() } catch {} ; ws = null }
    connected.value = false
  }

  function onVisibility() {
    if (document.visibilityState === 'visible') { retry = 0; open() }
    else { close() }
  }

  document.addEventListener('visibilitychange', onVisibility)
  open()

  // If `path` is a reactive getter, follow it: when the resolved path changes
  // while a socket is live (e.g. the ticket number changes on a reused route
  // component), tear down the old socket and reconnect to the new group. Stay
  // closed if the new value is null.
  if (typeof path === 'function') {
    watch(pathOf, (next, prev) => {
      if (next === prev) return
      retry = 0
      close()
      if (next) open()
    })
  }

  onBeforeUnmount(() => {
    stopped = true
    document.removeEventListener('visibilitychange', onVisibility)
    close()
  })

  return { connected }
}
