// @vitest-environment happy-dom
//
// Regression tests for the magic-link scanner bug: corporate email security
// (Defender Safe Links, Proofpoint, …) opens every emailed URL in a headless
// browser BEFORE the recipient sees it. The old AuthVerify consumed the token
// in onMounted, so the scanner's page-load burned the single-use token and the
// human always landed on "already used". The page must therefore never spend
// the token on load — only on an explicit click.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  route: { query: {} },
  router: { push: vi.fn() },
  auth: { verifyToken: vi.fn() },
}))

vi.mock('vue-router', () => ({
  useRoute: () => mocks.route,
  useRouter: () => mocks.router,
  RouterLink: { template: '<a><slot /></a>' },
}))

vi.mock('@/stores/auth.js', () => ({
  useAuthStore: () => mocks.auth,
}))

import AuthVerify from './AuthVerify.vue'

function mountPage() {
  // RouterLink is normally registered app-wide by app.use(router); stub it in
  // since there's no router instance here.
  return mount(AuthVerify, {
    global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
}

beforeEach(() => {
  mocks.route.query = { token: 'tok-123' }
  mocks.router.push = vi.fn()
  mocks.auth.verifyToken = vi.fn().mockResolvedValue({ user: {} })
  localStorage.clear()
})

describe('AuthVerify', () => {
  it('does NOT consume the token on page load', async () => {
    mountPage()
    await flushPromises()
    expect(mocks.auth.verifyToken).not.toHaveBeenCalled()
  })

  it('shows a sign-in button when a token is present', async () => {
    const w = mountPage()
    await flushPromises()
    const btn = w.find('button')
    expect(btn.exists()).toBe(true)
    expect(btn.text().toLowerCase()).toContain('sign in')
  })

  it('consumes the token only when the button is clicked', async () => {
    const w = mountPage()
    await flushPromises()
    await w.find('button').trigger('click')
    await flushPromises()
    expect(mocks.auth.verifyToken).toHaveBeenCalledTimes(1)
    expect(mocks.auth.verifyToken).toHaveBeenCalledWith('tok-123')
    expect(mocks.router.push).toHaveBeenCalledWith('/docs')
  })

  it('strips the token from the address bar on load but still signs in', async () => {
    window.history.replaceState({}, '', '/auth/verify?token=tok-123')
    const w = mountPage()
    await flushPromises()
    expect(window.location.search).not.toContain('tok-123')
    await w.find('button').trigger('click')
    await flushPromises()
    expect(mocks.auth.verifyToken).toHaveBeenCalledWith('tok-123')
  })

  it('honours a stashed pendingRedirect after click-through', async () => {
    localStorage.setItem(
      'pendingRedirect',
      JSON.stringify({ p: '/support/42', t: Date.now() }),
    )
    const w = mountPage()
    await flushPromises()
    await w.find('button').trigger('click')
    await flushPromises()
    expect(mocks.router.push).toHaveBeenCalledWith('/support/42')
  })

  it('shows the error state when verification fails', async () => {
    mocks.auth.verifyToken = vi.fn().mockRejectedValue({
      response: { data: { error: 'Token expired or already used' } },
    })
    const w = mountPage()
    await flushPromises()
    await w.find('button').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Token expired or already used')
    expect(w.find('button').exists()).toBe(false)
  })

  it('shows an error when no token is in the URL', async () => {
    mocks.route.query = {}
    const w = mountPage()
    await flushPromises()
    expect(w.find('button').exists()).toBe(false)
    expect(w.text()).toContain('No token provided')
  })
})
