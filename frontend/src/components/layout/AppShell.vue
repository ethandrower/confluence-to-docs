<template>
  <div class="min-h-screen flex flex-col">
    <!-- Header -->
    <header class="sticky top-0 z-50 h-14 border-b bg-background/80 backdrop-blur-xl">
      <div class="flex items-center h-full px-4 gap-3">
        <!-- Mobile menu trigger -->
        <Sheet v-model:open="mobileOpen">
          <SheetTrigger as-child>
            <button class="lg:hidden p-1.5 -ml-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors" aria-label="Menu">
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

        <!-- Logo -->
        <RouterLink to="/" class="flex items-center gap-2.5 group">
          <div class="w-7 h-7 rounded-lg bg-primary flex items-center justify-center shadow-sm">
            <svg class="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.292m0-14.25v14.25" />
            </svg>
          </div>
          <span class="font-semibold text-[15px] text-foreground tracking-tight whitespace-nowrap">
            CiteMed Support
          </span>
        </RouterLink>

        <div class="flex-1" />

        <!-- Search — desktop -->
        <button
          @click="searchOpen = true"
          class="hidden sm:inline-flex items-center gap-2 h-8 w-60 px-3 rounded-lg border text-[13px] text-muted-foreground/60 bg-muted/30 hover:bg-muted/50 hover:text-muted-foreground transition-all"
        >
          <svg class="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
          </svg>
          <span class="flex-1 text-left truncate">Search...</span>
          <kbd class="hidden md:inline-flex h-5 items-center gap-0.5 rounded-md border bg-background px-1.5 font-mono text-[10px] text-muted-foreground/50">
            {{ isMac ? '⌘' : '⌃' }}K
          </kbd>
        </button>

        <!-- Search — mobile -->
        <button @click="searchOpen = true" class="sm:hidden p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors" aria-label="Search">
          <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
          </svg>
        </button>
      </div>
    </header>

    <div class="flex flex-1 overflow-hidden">
      <!-- Sidebar — desktop -->
      <aside class="hidden lg:block w-[260px] shrink-0 border-r bg-sidebar">
        <ScrollArea class="h-[calc(100vh-3.5rem)]">
          <div class="pt-3 pb-6">
            <slot name="sidebar" />
          </div>
        </ScrollArea>
      </aside>

      <main class="flex-1 min-w-0 overflow-y-auto h-[calc(100vh-3.5rem)]">
        <slot name="content" />
      </main>
    </div>

    <SearchCommand v-model:open="searchOpen" />
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { Sheet, SheetContent, SheetTrigger, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet'
import { ScrollArea } from '@/components/ui/scroll-area'
import SearchCommand from './SearchCommand.vue'

const mobileOpen = ref(false)
const searchOpen = ref(false)
const isMac = ref(false)

function onKey(e) {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault()
    searchOpen.value = !searchOpen.value
  }
}

onMounted(() => {
  isMac.value = /(Mac|iPhone|iPod|iPad)/i.test(navigator.platform)
  document.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
</script>
