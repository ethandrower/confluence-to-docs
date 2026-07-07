<template>
  <div class="flex min-h-screen bg-background overflow-x-hidden">
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
      <header class="topbar h-14 shrink-0 flex items-center gap-2 px-4 lg:px-6 border-b border-border">
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
              <!-- Primary nav — the top-bar actions are hidden on mobile, so
                   these links are the only way to move between sections (and
                   sign out) on a phone, especially on ticket/file pages that
                   render no sidebar. -->
              <nav class="mobile-nav" aria-label="Main navigation">
                <RouterLink to="/docs" class="mobile-nav-link" @click="mobileOpen = false">Documentation</RouterLink>
                <RouterLink to="/tickets" class="mobile-nav-link" @click="mobileOpen = false">Contact</RouterLink>
                <RouterLink v-if="auth.user && !auth.user.is_admin" to="/files" class="mobile-nav-link" @click="mobileOpen = false">Share Files</RouterLink>
                <RouterLink v-if="auth.user && !auth.user.is_admin" to="/support" class="mobile-nav-link" @click="mobileOpen = false">Support</RouterLink>
                <RouterLink v-if="auth.user?.is_admin" to="/manage" class="mobile-nav-link" @click="mobileOpen = false">Manage</RouterLink>
                <button v-if="auth.user" type="button" class="mobile-nav-link mobile-nav-link--action" @click="signOut">Sign out</button>
                <RouterLink v-else to="/login" class="mobile-nav-link mobile-nav-link--action" @click="mobileOpen = false">Log in</RouterLink>
              </nav>
              <div v-if="!hideSidebar" class="mobile-nav-sep" aria-hidden="true"></div>
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
        <RouterLink v-if="auth.user && !auth.user.is_admin" to="/files" class="topbar-btn hidden sm:inline-flex" title="Share files with the CiteMed team">
          <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 16.5V9.75m0 0 3 3m-3-3-3 3M6.75 19.5a4.5 4.5 0 0 1-1.41-8.775 5.25 5.25 0 0 1 10.233-2.33 3 3 0 0 1 3.758 3.848A3.752 3.752 0 0 1 18 19.5H6.75Z" />
          </svg>
          Share Files
        </RouterLink>
        <RouterLink v-if="auth.user && !auth.user.is_admin" to="/support" class="topbar-btn hidden sm:inline-flex" title="View and reply to your support tickets">
          <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M8.625 12a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H8.25m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H12m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 0 1-2.555-.337A5.972 5.972 0 0 1 5.41 20.97a5.969 5.969 0 0 1-.474-.065 4.48 4.48 0 0 0 .978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25Z" />
          </svg>
          Support
        </RouterLink>
        <RouterLink v-if="auth.user?.is_admin" to="/manage" class="topbar-btn hidden sm:inline-flex" title="Manage users & companies">
          <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 19.128a9.38 9.38 0 0 0 2.625.372 9.337 9.337 0 0 0 4.121-.952 4.125 4.125 0 0 0-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 0 1 8.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0 1 11.964-3.07M12 6.375a3.375 3.375 0 1 1-6.75 0 3.375 3.375 0 0 1 6.75 0Zm8.25 2.25a2.625 2.625 0 1 1-5.25 0 2.625 2.625 0 0 1 5.25 0Z" />
          </svg>
          Manage
        </RouterLink>

        <span class="topbar-divider hidden sm:block" aria-hidden="true"></span>

        <ThemeToggle />

        <button v-if="auth.user" @click="signOut" class="topbar-btn-ghost hidden sm:inline-flex" :title="auth.user.email">Sign out</button>
        <RouterLink v-else to="/login" class="topbar-btn-ghost hidden sm:inline-flex">Log in</RouterLink>
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
  mobileOpen.value = false
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

/* Ghost button (Sign out / Log in) — same height as the action buttons */
.topbar-btn-ghost {
  display: inline-flex;
  align-items: center;
  height: 34px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid transparent;
  font-size: 13px;
  font-weight: 500;
  color: var(--muted-foreground);
  transition: color 0.15s, background 0.15s;
}
.topbar-btn-ghost:hover { color: var(--foreground); background: var(--muted); }

/* Vertical divider between action groups and utility controls */
.topbar-divider {
  width: 1px;
  height: 20px;
  background: var(--border);
  margin: 0 2px;
}

/* Mobile Sheet navigation */
.mobile-nav { display: flex; flex-direction: column; padding: 8px; }
.mobile-nav-link {
  display: block;
  width: 100%;
  padding: 10px 12px;
  border-radius: 8px;
  border: none;
  background: none;
  text-align: left;
  font-family: var(--font-ui);
  font-size: 15px;
  font-weight: 500;
  color: var(--foreground);
  cursor: pointer;
}
.mobile-nav-link:hover { background: var(--muted); }
.mobile-nav-link:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
.mobile-nav-link.router-link-active { color: var(--primary); font-weight: 600; }
.mobile-nav-link--action { color: var(--muted-foreground); }
.mobile-nav-sep { height: 1px; background: var(--sidebar-border); margin: 8px 12px; }

/* Top-bar search field (opens the ⌘K palette) */
.topbar-search {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  flex: 1 1 0;
  min-width: 0;           /* allow it to shrink instead of forcing overflow */
  max-width: 760px;
  padding: 0 10px 0 12px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--muted-foreground);
  transition: border-color 0.15s, background 0.15s;
}
.topbar-search:hover { border-color: var(--accent-hover); background: var(--muted); }
.topbar-search-text {
  flex: 1;
  min-width: 0;
  text-align: left;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
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

/* Below sm, the top-bar actions are hidden and navigation moves into the
   mobile Sheet. The Tailwind `hidden sm:inline-flex` classes are overridden by
   the scoped `display:inline-flex` rules above (scoped selectors out-specific
   Tailwind's `.hidden`), so the hide MUST live here — and at the END of the
   block, so equal-specificity source order lets it win over every base rule
   (including `.topbar-search`, defined later above). Otherwise actions
   overflow the bar on mobile. */
@media (max-width: 639px) {
  .topbar-btn,
  .topbar-btn-ghost,
  .topbar-search,
  .topbar-divider {
    display: none;
  }
}
</style>
