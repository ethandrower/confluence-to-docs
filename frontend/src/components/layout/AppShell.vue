<template>
  <div class="min-h-screen flex flex-col">
    <!-- Skip link — first focusable element, lets keyboard users jump past
         the nav straight to the document body (WCAG 2.4.1). -->
    <a href="#main-content" class="skip-link">Skip to content</a>

    <!-- Header -->
    <header class="sticky top-0 z-50 h-14 border-b bg-card shadow-[0_1px_3px_0_oklch(0_0_0/0.04)]">
      <div class="flex items-center h-full px-4 gap-3">
        <!-- Mobile menu trigger -->
        <Sheet v-model:open="mobileOpen">
          <SheetTrigger as-child>
            <button class="lg:hidden p-1.5 -ml-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors" aria-label="Menu">
              <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                <path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
              </svg>
            </button>
          </SheetTrigger>
          <SheetContent side="left" class="w-[280px] p-0">
            <SheetHeader class="sr-only"><SheetTitle>Navigation</SheetTitle><SheetDescription>Docs</SheetDescription></SheetHeader>
            <ScrollArea class="h-full pt-3 pb-6">
              <slot name="sidebar" />
            </ScrollArea>
          </SheetContent>
        </Sheet>

        <!-- Logo — reproduces the [cite]med wordmark, matching the brand logo
             and the email letterhead. "Support" reads as a lighter qualifier. -->
        <RouterLink to="/" class="flex items-center group" aria-label="CiteMed Support — home">
          <span class="wordmark text-[24px] whitespace-nowrap" aria-hidden="true">
            <span class="wm-bracket">[</span>cite<span class="wm-bracket">]</span>med<span class="wm-support">Support</span>
          </span>
        </RouterLink>

        <!-- Nav links — desktop -->
        <nav class="hidden sm:flex items-center gap-1 ml-2">
          <RouterLink
            to="/docs"
            class="px-2.5 py-1 rounded-md text-[13px] font-medium transition-colors"
            :class="isDocs ? 'text-primary bg-primary/10' : 'text-muted-foreground hover:text-foreground hover:bg-muted'"
          >Docs</RouterLink>
          <RouterLink
            to="/tickets"
            class="px-2.5 py-1 rounded-md text-[13px] font-medium transition-colors"
            :class="isContact ? 'text-primary bg-primary/10' : 'text-muted-foreground hover:text-foreground hover:bg-muted'"
          >Contact</RouterLink>
        </nav>

        <div class="flex-1" />

        <!-- Search — desktop -->
        <button
          @click="searchOpen = true"
          aria-label="Search documentation"
          class="hidden sm:inline-flex items-center gap-2 h-8 w-52 px-3 rounded-lg border border-border-subtle text-[13px] text-muted-foreground bg-background hover:bg-muted hover:text-muted-foreground hover:border-border transition-all"
        >
          <svg class="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
          </svg>
          <span class="flex-1 text-left truncate">Search...</span>
          <kbd class="hidden md:inline-flex h-5 items-center gap-0.5 rounded-md border bg-background px-1.5 font-mono text-[10px] text-muted-foreground">
            {{ isMac ? '⌘' : '⌃' }}K
          </kbd>
        </button>

        <!-- User / Login -->
        <div class="hidden sm:flex items-center gap-2 ml-1">
          <template v-if="auth.user">
            <!-- Admin badge — only renders when the logged-in portal user
                 matches an active Django superuser. Backend gates this
                 entirely so non-admins never see the badge or the URL. -->
            <a
              v-if="auth.user.is_admin && auth.user.admin_url"
              :href="auth.user.admin_url"
              target="_blank"
              rel="noopener"
              class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold uppercase tracking-wider text-primary border border-primary/30 bg-primary/5 hover:bg-primary/10 transition-colors"
              title="Open Django admin"
            >
              <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 15v2m-6 4h12a2 2 0 0 0 2-2v-6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2zm10-10V7a4 4 0 0 0-8 0v4h8z" />
              </svg>
              Admin
            </a>
            <span class="text-xs text-muted-foreground truncate max-w-[120px]" :title="auth.user.email">{{ auth.user.email }}</span>
            <button
              @click="signOut"
              class="text-[13px] font-medium text-muted-foreground hover:text-foreground transition-colors"
            >
              Sign out
            </button>
          </template>
          <RouterLink v-else to="/login" class="text-[13px] font-medium text-muted-foreground hover:text-foreground transition-colors">Log in</RouterLink>
        </div>

        <!-- Search — mobile -->
        <button @click="searchOpen = true" class="sm:hidden p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors" aria-label="Search">
          <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
          </svg>
        </button>
      </div>
    </header>

    <div class="flex flex-1 overflow-hidden">
      <!-- Sidebar — desktop -->
      <aside v-if="!hideSidebar" aria-label="Documentation navigation" class="hidden lg:block w-[var(--sidebar-width)] shrink-0 border-r bg-sidebar">
        <ScrollArea class="h-[calc(100vh-var(--nav-height))]">
          <div class="pt-3 pb-6">
            <slot name="sidebar" />
          </div>
        </ScrollArea>
      </aside>

      <main id="main-content" tabindex="-1" class="flex-1 min-w-0 overflow-y-auto h-[calc(100vh-var(--nav-height))]">
        <slot name="content" />
      </main>
    </div>

    <SearchCommand v-model:open="searchOpen" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth.js'
import { Sheet, SheetContent, SheetTrigger, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet'
import { ScrollArea } from '@/components/ui/scroll-area'
import SearchCommand from './SearchCommand.vue'

defineProps({ hideSidebar: Boolean })
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

async function signOut() {
  await auth.logout()
  router.push({ name: 'login' })
}
const mobileOpen = ref(false)
const searchOpen = ref(false)
const isMac = ref(false)

const isDocs = computed(() => route.path.startsWith('/docs'))
const isContact = computed(() => route.path === '/tickets')

function onKey(e) {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault()
    searchOpen.value = !searchOpen.value
  }
}

onMounted(() => {
  isMac.value = /Mac|iPhone|iPod|iPad/i.test(navigator.userAgentData?.platform || navigator.userAgent)
  document.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
</script>

<style scoped>
/* ── Brand wordmark ([cite]med Support) — matches the logo + email letterhead ── */
.wordmark {
  font-family: var(--font-ui);
  font-weight: 700;
  color: #2d5296; /* brand navy — same as the logo */
  letter-spacing: -0.02em;
  line-height: 1;
}
.wm-bracket {
  font-weight: 500;
  color: #8aa4cf; /* lighter navy tint for the brackets */
}
.wm-support {
  margin-left: 0.4em;
  font-weight: 500;
  font-size: 0.78em;
  color: var(--muted-foreground);
}

/* Visually hidden until focused, then pinned top-left over the header. */
.skip-link {
  position: fixed;
  top: 8px;
  left: 8px;
  z-index: 100;
  transform: translateY(-150%);
  padding: 8px 14px;
  border-radius: 8px;
  background: var(--primary);
  color: #fff;
  font-family: var(--font-ui);
  font-size: 13px;
  font-weight: 600;
  box-shadow: 0 4px 12px oklch(0 0 0 / 0.18);
  transition: transform 0.15s ease;
}
.skip-link:focus-visible,
.skip-link:focus {
  transform: translateY(0);
  outline: 2px solid #fff;
  outline-offset: 2px;
}
main:focus-visible { outline: none; }
</style>
