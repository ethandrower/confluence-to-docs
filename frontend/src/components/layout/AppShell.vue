<template>
  <div class="flex min-h-screen bg-background">
    <!-- Skip link — first focusable element (WCAG 2.4.1) -->
    <a href="#main-content" class="skip-link">Skip to content</a>

    <!-- ── Desktop sidebar (full height) ───────────────────────────────── -->
    <aside
      v-if="!hideSidebar"
      aria-label="Documentation navigation"
      class="hidden lg:flex flex-col w-[var(--sidebar-width)] shrink-0 border-r border-sidebar-border bg-sidebar h-screen sticky top-0"
    >
      <div class="h-14 flex items-center px-5 shrink-0">
        <RouterLink to="/" class="flex items-center group" aria-label="CiteMed Support — home">
          <span class="wordmark text-[21px] whitespace-nowrap" aria-hidden="true">
            <span class="wm-bracket">[</span>cite<span class="wm-bracket">]</span>med<span class="wm-support">Support</span>
          </span>
        </RouterLink>
      </div>
      <ScrollArea class="flex-1 min-h-0">
        <div class="pb-6">
          <slot name="sidebar" />
        </div>
      </ScrollArea>
      <div class="sidebar-foot">
        <span>© {{ year }} CiteMed</span>
        <span class="sidebar-foot-dot" aria-hidden="true">·</span>
        <span>Controlled documentation</span>
      </div>
    </aside>

    <!-- ── Main column ─────────────────────────────────────────────────── -->
    <div class="flex-1 min-w-0 flex flex-col h-screen">
      <!-- Top bar -->
      <header class="topbar h-14 shrink-0 flex items-center gap-3 px-4 lg:px-6 border-b border-border">
        <!-- Mobile: menu + wordmark -->
        <Sheet v-model:open="mobileOpen">
          <SheetTrigger as-child>
            <button class="lg:hidden p-1.5 -ml-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors" aria-label="Menu">
              <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                <path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
              </svg>
            </button>
          </SheetTrigger>
          <SheetContent side="left" class="w-[280px] p-0 bg-sidebar">
            <SheetHeader class="sr-only"><SheetTitle>Navigation</SheetTitle><SheetDescription>Documentation navigation</SheetDescription></SheetHeader>
            <div class="h-14 flex items-center px-5 border-b border-sidebar-border">
              <span class="wordmark text-[20px]" aria-hidden="true">
                <span class="wm-bracket">[</span>cite<span class="wm-bracket">]</span>med<span class="wm-support">Support</span>
              </span>
            </div>
            <ScrollArea class="h-[calc(100vh-3.5rem)] pb-6">
              <slot name="sidebar" />
            </ScrollArea>
          </SheetContent>
        </Sheet>

        <RouterLink to="/" class="lg:hidden flex items-center" aria-label="CiteMed Support — home">
          <span class="wordmark text-[18px]" aria-hidden="true">
            <span class="wm-bracket">[</span>cite<span class="wm-bracket">]</span>med<span class="wm-support">Support</span>
          </span>
        </RouterLink>

        <!-- Search (opens ⌘K palette) -->
        <button @click="searchOpen = true" aria-label="Search documentation" class="topbar-search hidden sm:inline-flex">
          <svg class="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
          </svg>
          <span class="topbar-search-text">Search the documentation…</span>
          <kbd class="topbar-search-kbd">{{ isMac ? '⌘' : 'Ctrl' }} K</kbd>
        </button>

        <div class="flex-1" />

        <!-- Actions -->
        <RouterLink to="/docs" class="topbar-btn topbar-btn--primary hidden sm:inline-flex">
          <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.292m0-14.25v14.25" />
          </svg>
          View all docs
        </RouterLink>
        <RouterLink to="/tickets" class="topbar-btn hidden sm:inline-flex">
          <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 0 1-2.25 2.25h-15a2.25 2.25 0 0 1-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25m19.5 0v.243a2.25 2.25 0 0 1-1.07 1.916l-7.5 4.615a2.25 2.25 0 0 1-2.36 0L3.32 8.91a2.25 2.25 0 0 1-1.07-1.916V6.75" />
          </svg>
          Contact
        </RouterLink>

        <ThemeToggle />

        <div class="hidden sm:flex items-center gap-2 pl-1 ml-1 border-l border-border">
          <template v-if="auth.user">
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
            <button
              @click="signOut"
              class="text-[13px] font-medium text-muted-foreground hover:text-foreground transition-colors"
              :title="auth.user.email"
            >
              Sign out
            </button>
          </template>
          <RouterLink v-else to="/login" class="text-[13px] font-medium text-muted-foreground hover:text-foreground transition-colors">Log in</RouterLink>
        </div>
      </header>

      <main id="main-content" tabindex="-1" class="flex-1 min-w-0 overflow-y-auto">
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
import { useDocsStore } from '@/stores/docs.js'
import { Sheet, SheetContent, SheetTrigger, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet'
import { ScrollArea } from '@/components/ui/scroll-area'
import SearchCommand from './SearchCommand.vue'
import ThemeToggle from './ThemeToggle.vue'

defineProps({ hideSidebar: Boolean })
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const store = useDocsStore()

async function signOut() {
  await auth.logout()
  router.push({ name: 'login' })
}
const mobileOpen = ref(false)
const searchOpen = ref(false)
const isMac = ref(false)
const year = new Date().getFullYear()

function onKey(e) {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault()
    searchOpen.value = !searchOpen.value
  }
}
function onOpenSearch() {
  searchOpen.value = true
}

onMounted(() => {
  isMac.value = /Mac|iPhone|iPod|iPad/i.test(navigator.userAgentData?.platform || navigator.userAgent)
  document.addEventListener('keydown', onKey)
  window.addEventListener('citemed:open-search', onOpenSearch)
})
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKey)
  window.removeEventListener('citemed:open-search', onOpenSearch)
})
</script>

<style scoped>
.topbar {
  background: color-mix(in srgb, var(--background) 88%, transparent);
  backdrop-filter: saturate(180%) blur(8px);
  position: sticky;
  top: 0;
  z-index: 30;
}

/* Top-bar action buttons (View all docs / Contact) */
.topbar-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--card);
  font-size: 13px;
  font-weight: 500;
  color: var(--foreground);
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}
.topbar-btn:hover {
  background: var(--accent);
  border-color: var(--accent-hover);
  color: var(--accent-foreground);
}
/* Primary (brand navy) call-to-action */
.topbar-btn--primary {
  background: var(--primary);
  border-color: var(--primary);
  color: var(--primary-foreground);
}
.topbar-btn--primary:hover {
  background: color-mix(in srgb, var(--primary) 88%, #000);
  border-color: color-mix(in srgb, var(--primary) 88%, #000);
  color: var(--primary-foreground);
}
.dark .topbar-btn--primary:hover {
  background: color-mix(in srgb, var(--primary) 85%, #fff);
  border-color: color-mix(in srgb, var(--primary) 85%, #fff);
}
.topbar-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  color: var(--muted-foreground);
}
.topbar-icon:hover { color: var(--foreground); background: var(--muted); }

/* Top-bar search field (opens the ⌘K palette) */
.topbar-search {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  flex: 1;
  max-width: 760px;
  padding: 0 10px 0 12px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--muted-foreground);
  transition: border-color 0.15s, background 0.15s;
}
.topbar-search:hover { border-color: var(--accent-hover); background: var(--muted); }
.topbar-search-text { flex: 1; text-align: left; font-size: 13px; }
.topbar-search-kbd {
  font-family: var(--font-ui);
  font-size: 10.5px;
  font-weight: 500;
  padding: 2px 6px;
  border-radius: 5px;
  border: 1px solid var(--border);
  background: var(--background);
  color: var(--muted-foreground);
}

/* Sidebar footer — quiet governance signal */
.sidebar-foot {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px 16px;
  border-top: 1px solid var(--sidebar-border);
  font-family: var(--font-ui);
  font-size: 11px;
  color: var(--muted-foreground);
  letter-spacing: 0.005em;
}
.sidebar-foot-dot { opacity: 0.5; }

/* ── Brand wordmark ([cite]med Support) ── */
.wordmark {
  font-family: var(--font-ui);
  font-weight: 700;
  color: var(--primary);
  letter-spacing: -0.02em;
  line-height: 1;
}
.wm-bracket { font-weight: 500; color: inherit; }
.wm-support {
  margin-left: 0.4em;
  font-weight: 500;
  font-size: 0.78em;
  color: var(--muted-foreground);
}

/* Skip link: hidden until focused */
.skip-link {
  position: fixed;
  top: 8px;
  left: 8px;
  z-index: 100;
  transform: translateY(-150%);
  padding: 8px 14px;
  border-radius: 8px;
  background: var(--primary);
  color: var(--primary-foreground);
  font-family: var(--font-ui);
  font-size: 13px;
  font-weight: 600;
  box-shadow: 0 4px 12px oklch(0 0 0 / 0.18);
  transition: transform 0.15s ease;
}
.skip-link:focus-visible,
.skip-link:focus {
  transform: translateY(0);
  outline: 2px solid var(--ring);
  outline-offset: 2px;
}
main:focus-visible { outline: none; }
</style>
