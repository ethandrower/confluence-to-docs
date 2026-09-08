// @vitest-environment happy-dom
//
// Needs a DOM: apiFetch reads the CSRF token off document.cookie.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { apiFetch, getCookie } from './http.js'

/**
 * The FormData case is the one worth pinning down.
 *
 * Setting Content-Type by hand on a multipart request omits the boundary the
 * browser would have generated, so the server receives a body it cannot split
 * and reports "no file was uploaded" — a silent failure that looks like an
 * empty upload rather than a bad header. This caught the roster import in
 * staging; the test is here so it cannot come back.
 */
describe('apiFetch', () => {
  let calls

  beforeEach(() => {
    calls = []
    document.cookie = 'csrftoken=test-token'
    global.fetch = vi.fn((path, opts) => {
      calls.push({ path, opts })
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
  })

  it('does not set Content-Type for a FormData body', async () => {
    const form = new FormData()
    form.append('file', new Blob(['a,b\n1,2'], { type: 'text/csv' }), 'r.csv')
    await apiFetch('/api/roster/imports/', { method: 'POST', body: form })
    expect(calls[0].opts.headers['Content-Type']).toBeUndefined()
  })

  it('still sends the CSRF token with a FormData body', async () => {
    // Dropping Content-Type must not drop the token with it — Django rejects
    // the request outright without it.
    await apiFetch('/api/roster/imports/', {
      method: 'POST', body: new FormData(),
    })
    expect(calls[0].opts.headers['X-CSRFToken']).toBe('test-token')
  })

  it('sets JSON Content-Type for an ordinary body', async () => {
    await apiFetch('/api/roster/users/', {
      method: 'POST', body: JSON.stringify({ email: 'a@x.com' }),
    })
    expect(calls[0].opts.headers['Content-Type']).toBe('application/json')
  })

  it('lets an explicit Content-Type win', async () => {
    await apiFetch('/api/x/', {
      method: 'POST', body: 'raw', headers: { 'Content-Type': 'text/plain' },
    })
    expect(calls[0].opts.headers['Content-Type']).toBe('text/plain')
  })

  it('does not ask for a CSRF token on a safe method', async () => {
    await apiFetch('/api/roster/')
    expect(calls[0].opts.headers['X-CSRFToken']).toBeUndefined()
  })

  it('sends credentials so the session cookie travels', async () => {
    await apiFetch('/api/roster/')
    expect(calls[0].opts.credentials).toBe('same-origin')
  })
})

describe('getCookie', () => {
  it('reads a cookie by name', () => {
    document.cookie = 'csrftoken=abc123'
    expect(getCookie('csrftoken')).toBe('abc123')
  })

  it('returns empty string when absent', () => {
    expect(getCookie('nope-not-here')).toBe('')
  })
})
