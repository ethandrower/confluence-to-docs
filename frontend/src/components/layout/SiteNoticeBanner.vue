<template>
  <!-- Above <main> rather than inside it: the banner applies to the whole
       portal, and every view renders its own content into that slot. -->
  <div v-if="store.banner.length" class="notices" data-testid="site-notices">
    <div
      v-for="notice in store.banner"
      :key="notice.id"
      class="notice"
      :class="levelOf(notice).className"
      :role="levelOf(notice).role"
      :aria-live="levelOf(notice).ariaLive"
    >
      <span class="notice-tag">{{ levelOf(notice).label }}</span>

      <p class="notice-message">{{ notice.message }}</p>

      <a
        v-if="notice.link_url"
        :href="notice.link_url"
        class="notice-link"
        rel="noopener"
      >{{ notice.link_label || 'More detail' }}</a>

      <!-- Once for the stack, not once per notice: repeated on every row it
           reads as part of each message rather than as navigation. -->
      <RouterLink v-if="notice.id === store.banner[0].id" to="/notices" class="notice-history-link">
        Past notices
      </RouterLink>

      <!-- Critical notices have no dismiss control, and the server refuses to
           dismiss them even if one is fabricated. -->
      <button
        v-if="notice.dismissible"
        type="button"
        class="notice-dismiss"
        :aria-label="`Dismiss this ${levelOf(notice).label.toLowerCase()}`"
        @click="store.dismiss(notice.id)"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup>
import { onMounted, watch } from 'vue'
import { useNoticesStore } from '@/stores/notices.js'
import { useAuthStore } from '@/stores/auth.js'
import { useTicketChannel } from '@/lib/useTicketChannel'
import { noticeLevel } from '@/lib/notices.js'

const store = useNoticesStore()
const auth = useAuthStore()

// Takes the notice, not the level string. noticeLevel() falls back to the info
// treatment for anything it doesn't recognise — deliberate, so a level added
// server-side still shows — but that also means handing it a notice OBJECT
// silently renders every notice as info. That shipped once and only turned up in
// the browser, where a critical notice appeared as role="status" "Notice".
const levelOf = (notice) => noticeLevel(notice.level)

// Signed-in only: /api/notices/ is session-gated, so calling it anonymously
// just 401s. auth.user resolves asynchronously on boot, hence the watch as
// well as the mounted call.
function loadIfSignedIn() {
  if (auth.user) store.load()
}

onMounted(loadIfSignedIn)
watch(() => auth.user?.email, loadIfSignedIn)

// Live updates over the existing nudge channel — during an incident nobody
// reloads, and a resolved incident should stop warning people by itself.
// Returning null keeps the socket closed while nobody is signed in.
useTicketChannel(
  () => (auth.user ? '/ws/notices/' : null),
  () => loadIfSignedIn(),
)
</script>

<style scoped>
.notices {
  display: flex;
  flex-direction: column;
  border-bottom: 1px solid var(--border);
}

.notice {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  font-size: 13.5px;
  line-height: 1.45;
  border-left: 3px solid var(--notice-accent);
  background: var(--notice-bg);
  color: var(--foreground);
}

.notice + .notice {
  border-top: 1px solid var(--border);
}

/* Levels map onto the tokens already in main.css, in both themes — no new
   palette, and nothing decorative. */
.notice--info {
  --notice-accent: var(--info);
  --notice-bg: color-mix(in srgb, var(--info) 8%, var(--card));
}

.notice--warning {
  --notice-accent: var(--warning);
  --notice-bg: color-mix(in srgb, var(--warning) 10%, var(--card));
}

.notice--critical {
  --notice-accent: var(--destructive);
  --notice-bg: color-mix(in srgb, var(--destructive) 10%, var(--card));
}

.notice-tag {
  flex-shrink: 0;
  font-family: var(--font-ui, inherit);
  font-size: 11px;
  font-weight: 650;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--notice-accent);
}

.notice-message {
  margin: 0;
  min-width: 0;
  /* Wrap rather than truncate: a clipped incident message is a broken one. */
  overflow-wrap: anywhere;
}

.notice-link,
.notice-history-link {
  flex-shrink: 0;
  font-weight: 550;
  text-decoration: underline;
  text-underline-offset: 2px;
  color: var(--notice-accent);
}

.notice-history-link {
  margin-left: auto;
  color: var(--muted-foreground);
}

.notice-link:hover,
.notice-history-link:hover {
  color: var(--foreground);
}

.notice-dismiss {
  flex-shrink: 0;
  display: inline-flex;
  padding: 4px;
  border-radius: var(--radius-sm);
  color: var(--muted-foreground);
}

.notice-dismiss:hover {
  color: var(--foreground);
  background: var(--muted);
}

.notice-dismiss svg {
  width: 14px;
  height: 14px;
}

/* Keyboard focus must be visible on a coloured ground (WCAG 2.4.7). */
.notice-dismiss:focus-visible,
.notice-link:focus-visible,
.notice-history-link:focus-visible {
  outline: 2px solid var(--notice-accent, var(--ring));
  outline-offset: 2px;
}

@media (max-width: 640px) {
  .notice {
    /* Stacked, so a long message doesn't squeeze the tag and controls to
       nothing on a phone. */
    flex-wrap: wrap;
    gap: 8px;
  }

  .notice-history-link {
    margin-left: 0;
  }
}
</style>
