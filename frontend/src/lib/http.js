// Single HTTP entry point for API calls. Safe methods pass straight through;
// unsafe ones additionally carry the CSRF token.
//
// Django's CsrfViewMiddleware now guards every endpoint (the blanket
// @csrf_exempt is gone), so any unsafe request must carry the token from the
// `csrftoken` cookie in an `X-CSRFToken` header.
//
// The cookie is planted by GET /api/auth/me/, which is decorated with
// @ensure_csrf_cookie and fired by App.vue on mount. That mount is async
// though, so a fast submit could race it — `ensureCsrfToken` closes that
// deterministically by fetching /auth/me/ on demand when the cookie is absent,
// rather than relying on boot ordering.

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS', 'TRACE'])

export function getCookie(name) {
  const match = document.cookie.match(new RegExp(`(^|;\\s*)${name}=([^;]*)`))
  return match ? decodeURIComponent(match[2]) : ''
}

let inflight = null

export async function ensureCsrfToken() {
  const existing = getCookie('csrftoken')
  if (existing) return existing
  // Collapse concurrent callers onto one request so a burst of parallel
  // mutations doesn't fire N identical /auth/me/ calls.
  if (!inflight) {
    inflight = fetch('/api/auth/me/', { credentials: 'same-origin' })
      .catch(() => {})
      .finally(() => { inflight = null })
  }
  await inflight
  return getCookie('csrftoken')
}

/** fetch() with credentials, JSON headers and CSRF handled. */
export async function apiFetch(path, opts = {}) {
  const method = (opts.method || 'GET').toUpperCase()
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) }
  if (!SAFE_METHODS.has(method)) {
    headers['X-CSRFToken'] = await ensureCsrfToken()
  }
  return fetch(path, { credentials: 'same-origin', ...opts, headers })
}
