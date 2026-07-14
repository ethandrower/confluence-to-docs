import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth.js'

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(to, from, savedPosition) {
    if (to.hash) return { el: to.hash, behavior: 'smooth' }
    if (savedPosition) return savedPosition
    return { top: 0 }
  },
  routes: [
    {
      path: '/',
      redirect: '/docs'
    },
    {
      path: '/docs',
      component: () => import('@/views/DocsView.vue'),
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          component: () => import('@/components/docs/DocSearch.vue'),
          name: 'docs-home'
        },
        {
          path: ':slug',
          component: () => import('@/components/docs/DocPage.vue'),
          name: 'doc-page',
          props: true
        }
      ]
    },
    {
      path: '/login',
      component: () => import('@/views/LoginView.vue'),
      name: 'login'
    },
    {
      path: '/auth/verify',
      component: () => import('@/components/auth/AuthVerify.vue'),
      name: 'auth-verify'
    },
    {
      path: '/tickets',
      component: () => import('@/views/TicketView.vue'),
      name: 'contact',
    },
    {
      path: '/files',
      component: () => import('@/views/FilesView.vue'),
      name: 'files',
      meta: { requiresAuth: true },
    },
    {
      path: '/support',
      component: () => import('@/views/SupportView.vue'),
      name: 'support',
      meta: { requiresAuth: true },
    },
    {
      path: '/support/:number',
      component: () => import('@/views/SupportView.vue'),
      name: 'support-ticket',
      props: true,
      meta: { requiresAuth: true },
    },
    {
      path: '/manage',
      component: () => import('@/views/AdminView.vue'),
      name: 'admin',
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/manage/tickets',
      component: () => import('@/views/ManageTicketsView.vue'),
      name: 'manage-tickets',
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      // Deep-linkable admin ticket — lets staff open a specific ticket from a
      // shared URL, and gives the /support customer-link admin fallback a
      // destination (see SupportView).
      path: '/manage/tickets/:number',
      component: () => import('@/views/ManageTicketsView.vue'),
      name: 'manage-ticket',
      props: true,
      meta: { requiresAuth: true, requiresAdmin: true },
    }
  ]
})

router.beforeEach(async (to, from, next) => {
  if (to.meta.requiresAuth) {
    const auth = useAuthStore()
    if (!auth.user) {
      await auth.fetchMe()
    }
    if (!auth.user) {
      // Also stash the target: the magic-link email carries only the token
      // (no ?redirect), so AuthVerify falls back to this to land the user on
      // their intended page — e.g. a /support/:n deep link from a ticket email.
      // Timestamped so a stale stash can't hijack an unrelated later login.
      try {
        localStorage.setItem('pendingRedirect', JSON.stringify({ p: to.fullPath, t: Date.now() }))
      } catch { /* private mode */ }
      return next({ name: 'login', query: { redirect: to.fullPath } })
    }
    if (to.meta.requiresAdmin && !auth.user.is_admin) {
      return next({ name: 'docs-home' })
    }
  }
  next()
})

export default router
