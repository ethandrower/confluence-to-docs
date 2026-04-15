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
      return next({ name: 'login', query: { redirect: to.fullPath } })
    }
  }
  next()
})

export default router
