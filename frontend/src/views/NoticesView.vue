<template>
  <AppShell hide-sidebar>
    <template #content>
      <div class="wrap">
        <header class="head">
          <h1 class="title">Service notices</h1>
          <p class="lede">
            Incidents and scheduled maintenance affecting the CiteMed platform,
            most recent first. Notices you have dismissed still appear here.
          </p>
        </header>

        <p v-if="loading" class="state">Loading…</p>

        <p v-else-if="error" class="state state--error">
          {{ error }}
          <button type="button" class="retry" @click="load">Try again</button>
        </p>

        <!-- An empty log is good news, and worth saying so rather than
             leaving a blank panel that reads as a failure to load. -->
        <p v-else-if="!store.history.length" class="state">
          No service notices have been raised.
        </p>

        <ol v-else class="list">
          <li v-for="notice in store.history" :key="notice.id" class="row" :class="levelOf(notice).className">
            <div class="row-head">
              <span class="tag">{{ levelOf(notice).label }}</span>
              <span class="when">{{ formatted(notice.starts_at) }}</span>
              <span v-if="notice.retired_at" class="resolved">Resolved</span>
              <span v-else-if="isFuture(notice.starts_at)" class="upcoming">Scheduled</span>
              <span v-else class="ongoing">Ongoing</span>
            </div>

            <p class="message">{{ notice.message }}</p>

            <a v-if="safeHref(notice.link_url)" :href="safeHref(notice.link_url)" class="link" rel="noopener">
              {{ notice.link_label || 'More detail' }}
            </a>

            <p v-if="notice.retired_at" class="closed">
              Resolved {{ formatted(notice.retired_at) }}
            </p>
          </li>
        </ol>
      </div>
    </template>
  </AppShell>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import AppShell from '@/components/layout/AppShell.vue'
import { useNoticesStore } from '@/stores/notices.js'
import { noticeLevel, safeHref } from '@/lib/notices.js'

const store = useNoticesStore()
const loading = ref(true)
const error = ref('')

// Takes the notice, not the level string — see the note in SiteNoticeBanner.
const levelOf = (notice) => noticeLevel(notice.level)

function formatted(value) {
  if (!value) return ''
  return new Date(value).toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function isFuture(value) {
  return new Date(value) > new Date()
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    await store.loadHistory()
  } catch {
    // Surfaced, unlike the banner's silent failure: someone who navigated here
    // deliberately is owed an explanation and a way to retry.
    error.value = 'Could not load service notices.'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.wrap {
  max-width: 760px;
  margin: 0 auto;
  padding: 32px 20px 64px;
}

.head {
  margin-bottom: 28px;
}

.title {
  font-size: 24px;
  font-weight: 650;
  letter-spacing: -0.01em;
  color: var(--foreground);
}

.lede {
  margin-top: 8px;
  font-family: var(--font-reading, inherit);
  font-size: 14.5px;
  line-height: 1.6;
  color: var(--muted-foreground);
}

.state {
  padding: 20px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--card);
  font-size: 14px;
  color: var(--muted-foreground);
}

.state--error {
  color: var(--foreground);
}

.retry {
  margin-left: 8px;
  font-weight: 550;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  list-style: none;
}

.row {
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-left: 3px solid var(--notice-accent);
  border-radius: var(--radius-lg);
  background: var(--card);
}

/* Same token mapping as the banner, so a level looks like itself everywhere. */
.notice--info { --notice-accent: var(--info); }
.notice--warning { --notice-accent: var(--warning); }
.notice--critical { --notice-accent: var(--destructive); }

.row-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}

.tag {
  font-size: 11px;
  font-weight: 650;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--notice-accent);
}

.when {
  font-size: 12.5px;
  color: var(--muted-foreground);
  font-variant-numeric: tabular-nums;
}

.resolved,
.ongoing,
.upcoming {
  font-size: 11px;
  font-weight: 600;
  padding: 1px 8px;
  border-radius: var(--radius-sm);
  background: var(--muted);
  color: var(--muted-foreground);
}

.ongoing {
  background: color-mix(in srgb, var(--notice-accent) 14%, var(--card));
  color: var(--notice-accent);
}

.message {
  font-family: var(--font-reading, inherit);
  font-size: 14.5px;
  line-height: 1.6;
  color: var(--foreground);
  white-space: pre-line;
  overflow-wrap: anywhere;
}

.link {
  display: inline-block;
  margin-top: 8px;
  font-size: 13.5px;
  font-weight: 550;
  color: var(--notice-accent);
  text-decoration: underline;
  text-underline-offset: 2px;
}

.closed {
  margin-top: 8px;
  font-size: 12.5px;
  color: var(--muted-foreground);
}
</style>
