// Presentation rules for incident/maintenance notices (#49).
//
// Kept out of the component so the ordering and the accessibility mapping are
// unit-testable — the project has no component-test harness, and these are the
// two parts with real logic in them.

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
