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
  // Strip BEFORE slicing, and never the other way round. Slicing first lets a
  // long enough run of padding push the scheme past the inspected window: what
  // remains looks schemeless, gets treated as a relative link, and is returned
  // unchanged — while the browser, which discards those bytes first, still sees
  // javascript: and runs it. `trim()` is no help; it does not remove NUL.
  const head = String(url)
    .toLowerCase()
    .replace(/[^a-z0-9+.:-]/g, '')
    .slice(0, 32)
  // No scheme at all means a relative link, which is safe.
  if (!/^[a-z][a-z0-9+.-]*:/.test(head)) return url
  return /^https?:/.test(head) ? url : ''
}

/**
 * How a notice reads in the history list.
 *
 * `ends_at` is consulted, not just `retired_at`: a maintenance window that has
 * simply lapsed is over, and labelling finished maintenance "Ongoing" tells the
 * customer something untrue. There is no "Scheduled" state here because the
 * history endpoint excludes notices whose window hasn't opened.
 */
export function historyStatus(notice) {
  if (notice.retired_at) return { label: 'Resolved', tone: 'resolved' }
  if (notice.ends_at && new Date(notice.ends_at) <= new Date()) {
    return { label: 'Ended', tone: 'ended' }
  }
  return { label: 'Ongoing', tone: 'ongoing' }
}

// How long a notice of each level may reasonably stand before an agent should
// be reminded about it. A critical banner nobody retires is the in-portal
// version of a stale status page: it keeps claiming an outage that is over, and
// people stop believing the banner at all. A warning about a slow sync can
// legitimately stand all day, so the thresholds differ — one threshold for
// everything would train agents to ignore the flag.
const STALE_AFTER_HOURS = { critical: 4, warning: 24, info: 72 }
// Unknown levels render as info but nag like a critical: erring toward telling
// someone is the safer direction for a thing whose whole job is being noticed.
const UNKNOWN_STALE_AFTER_HOURS = 4

/**
 * Agent-facing staleness for a LIVE notice: how long it has been up, and
 * whether that is long enough to be worth a nudge.
 *
 * Returns null when there is nothing to nag about — retired, ended, or not yet
 * started. Nagging about those is noise, and noise devalues the flag.
 */
export function noticeStaleness(notice, now = new Date()) {
  if (notice.retired_at) return null
  const started = new Date(notice.starts_at)
  if (started > now) return null
  if (notice.ends_at && new Date(notice.ends_at) <= now) return null

  const hours = (now - started) / 3_600_000
  const threshold = STALE_AFTER_HOURS[notice.level] ?? UNKNOWN_STALE_AFTER_HOURS
  return { hours, label: humanizeHours(hours), isStale: hours >= threshold }
}

function humanizeHours(hours) {
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))}m`
  if (hours < 48) return `${Math.round(hours)}h`
  return `${Math.round(hours / 24)}d`
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
