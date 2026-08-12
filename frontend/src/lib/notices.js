// Presentation rules for incident/maintenance notices (#49).
//
// Kept out of the component so the ordering, the accessibility mapping and the
// href guard are unit-testable — the project has no component-test harness, and
// these are the parts with real logic in them.

/** Lower sorts first. Mirrors SiteNotice.LEVEL_CHOICES on the server. */
export const LEVEL_RANK = { critical: 0, warning: 1, info: 2 }

// Unknown levels sort after everything known, but are never dropped: the
// server owns this vocabulary, and if it gains a level before the frontend
// knows about it, showing an incident notice out of order beats losing it.
const UNKNOWN_RANK = 99

const LEVELS = {
  critical: {
    label: 'Critical',
    className: 'notice--critical',
    // Interrupts a screen reader. Reserved for critical: if every level were
    // assertive, routine notices would talk over whatever the user is doing.
    role: 'alert',
    ariaLive: 'assertive',
  },
  warning: {
    label: 'Warning',
    className: 'notice--warning',
    role: 'status',
    ariaLive: 'polite',
  },
  info: {
    label: 'Notice',
    className: 'notice--info',
    role: 'status',
    ariaLive: 'polite',
  },
}

/**
 * An href safe to bind, or '' if the URL isn't one we will link to.
 *
 * Vue escapes text but does NOT sanitize a bound href, so `javascript:` in
 * link_url would run script in the reader's session. The admin API rejects
 * those on the way in; this is the second layer, because the API is not the
 * only writer — the Django admin and a shell reach the same column.
 *
 * Allowlist, not blocklist, and the scheme is normalised first: browsers ignore
 * case and strip whitespace and control characters (including NUL) while
 * resolving a scheme, so `JavaScript:`, `java\tscript:` and a NUL-obfuscated
 * variant all execute where a naive startsWith('javascript:') sees nothing.
 */
export function safeHref(url) {
  if (!url) return ''
  // Keep only characters that may legally appear in a scheme, so anything the
  // browser would discard is discarded here first.
  const head = String(url)
    .trim()
    .slice(0, 32)
    .toLowerCase()
    .replace(/[^a-z0-9+.:-]/g, '')
  // No scheme at all means a relative link, which is safe.
  if (!/^[a-z][a-z0-9+.-]*:/.test(head)) return url
  return /^https?:/.test(head) ? url : ''
}

/** Level metadata, falling back to the info treatment for anything unknown. */
export function noticeLevel(level) {
  return LEVELS[level] || LEVELS.info
}

/**
 * Most severe first, newest first within a level.
 *
 * Returns a new array — the caller passes reactive state, and sorting in place
 * would reorder the store as a side effect of rendering.
 */
export function orderNotices(notices) {
  return [...notices].sort((a, b) => {
    const rank =
      (LEVEL_RANK[a.level] ?? UNKNOWN_RANK) - (LEVEL_RANK[b.level] ?? UNKNOWN_RANK)
    if (rank !== 0) return rank
    return new Date(b.starts_at) - new Date(a.starts_at)
  })
}
