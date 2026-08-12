import { describe, it, expect } from 'vitest'
import { LEVEL_RANK, orderNotices, noticeLevel, safeHref, historyStatus, noticeStaleness } from './notices'

const notice = (level, id, startsAt = '2026-08-01T00:00:00Z') => ({
  id, level, starts_at: startsAt, message: `${level} ${id}`,
})

describe('orderNotices', () => {
  // The banner stacks notices, so order IS the priority signal. An info
  // notice sitting above a critical one buries the thing that matters.
  it('puts the most severe notice first', () => {
    const ordered = orderNotices([notice('info', 1), notice('critical', 2), notice('warning', 3)])
    expect(ordered.map((n) => n.level)).toEqual(['critical', 'warning', 'info'])
  })

  it('shows the newest first within one level', () => {
    const ordered = orderNotices([
      notice('warning', 1, '2026-08-01T00:00:00Z'),
      notice('warning', 2, '2026-08-09T00:00:00Z'),
    ])
    expect(ordered.map((n) => n.id)).toEqual([2, 1])
  })

  it('does not mutate the array it was given', () => {
    // The store hands it `notices.value`; sorting in place would reorder
    // reactive state as a side effect of rendering.
    const input = [notice('info', 1), notice('critical', 2)]
    orderNotices(input)
    expect(input.map((n) => n.id)).toEqual([1, 2])
  })

  it('survives an empty list', () => {
    expect(orderNotices([])).toEqual([])
  })

  it('sorts an unknown level last rather than dropping it', () => {
    // The server owns the vocabulary. If a level is added there before the
    // frontend knows about it, the notice must still be SHOWN — losing an
    // incident notice is far worse than showing it in the wrong position.
    const ordered = orderNotices([notice('apocalyptic', 1), notice('info', 2)])
    expect(ordered.map((n) => n.id)).toEqual([2, 1])
    expect(ordered).toHaveLength(2)
  })
})

describe('noticeLevel', () => {
  it('describes each known level', () => {
    expect(noticeLevel('critical').label).toBe('Critical')
    expect(noticeLevel('warning').label).toBe('Warning')
    expect(noticeLevel('info').label).toBe('Notice')
  })

  it('marks critical as an assertive live region', () => {
    // A critical notice must interrupt a screen reader; the lower levels
    // must not, or every page change becomes an announcement.
    expect(noticeLevel('critical').role).toBe('alert')
    expect(noticeLevel('warning').role).toBe('status')
    expect(noticeLevel('info').role).toBe('status')
  })

  it('falls back to the info treatment for an unknown level', () => {
    const fallback = noticeLevel('apocalyptic')
    expect(fallback.label).toBe('Notice')
    expect(fallback.role).toBe('status')
    expect(fallback.className).toBe('notice--info')
  })

  it('gives every level a distinct class so the palette stays in CSS', () => {
    const classes = ['critical', 'warning', 'info'].map((l) => noticeLevel(l).className)
    expect(new Set(classes).size).toBe(3)
  })
})

describe('LEVEL_RANK', () => {
  it('ranks critical ahead of warning ahead of info', () => {
    expect(LEVEL_RANK.critical).toBeLessThan(LEVEL_RANK.warning)
    expect(LEVEL_RANK.warning).toBeLessThan(LEVEL_RANK.info)
  })
})

describe('safeHref', () => {
  // The server validates link_url on the way in, so this is the second layer.
  // It matters because the server is not the only writer: the Django admin and
  // a shell both reach the same column, and this is the sink that turns a
  // stored string into something the customer can click.
  it('passes an ordinary link through', () => {
    expect(safeHref('https://support.citemed.com/support')).toBe('https://support.citemed.com/support')
    expect(safeHref('http://example.com')).toBe('http://example.com')
  })

  it('refuses a javascript: URL', () => {
    expect(safeHref('javascript:alert(1)')).toBe('')
  })

  it('refuses regardless of case or leading whitespace', () => {
    // Browsers tolerate both when resolving a scheme, so a naive
    // startsWith('javascript:') check would miss these.
    expect(safeHref('JavaScript:alert(1)')).toBe('')
    expect(safeHref('  javascript:alert(1)')).toBe('')
    expect(safeHref('java\tscript:alert(1)')).toBe('')
  })

  it('refuses data: and vbscript:', () => {
    expect(safeHref('data:text/html,<script>alert(1)</script>')).toBe('')
    expect(safeHref('vbscript:msgbox(1)')).toBe('')
  })

  it('returns empty for nothing at all', () => {
    expect(safeHref('')).toBe('')
    expect(safeHref(null)).toBe('')
    expect(safeHref(undefined)).toBe('')
  })
})

describe('safeHref against scheme obfuscation', () => {
  it('refuses a NUL-obfuscated scheme', () => {
    // Browsers strip NUL while resolving a scheme; \\s in a regex does not match it.
    expect(safeHref('java\u0000script:alert(1)')).toBe('')
  })

  it('refuses a newline-obfuscated scheme', () => {
    expect(safeHref('java\nscript:alert(1)')).toBe('')
  })

  it('still allows a relative link', () => {
    expect(safeHref('/support')).toBe('/support')
  })
})

describe('safeHref against padding that pushes the scheme out of view', () => {
  // Regression: the guard used to slice to 32 characters BEFORE stripping the
  // characters browsers discard, so padding the front with enough NULs moved
  // `javascript:` past the inspected window. What was left looked schemeless,
  // was treated as a relative link, and the raw URL was handed back — while a
  // browser, which strips those bytes first, still executed it.
  const NUL = String.fromCharCode(0)

  it('refuses a hostile scheme padded past the inspection window', () => {
    expect(safeHref(NUL.repeat(35) + 'javascript:alert(1)')).toBe('')
  })

  it('refuses padding with other C0 control characters', () => {
    expect(safeHref(String.fromCharCode(1).repeat(40) + 'javascript:alert(1)')).toBe('')
    expect(safeHref('\t'.repeat(40) + 'javascript:alert(1)')).toBe('')
  })

  it('still passes a long legitimate URL', () => {
    const long = 'https://support.citemed.com/docs/' + 'a'.repeat(120)
    expect(safeHref(long)).toBe(long)
  })
})

describe('historyStatus', () => {
  const HOUR = 3600 * 1000
  const ago = (h) => new Date(Date.now() - h * HOUR).toISOString()

  it('reports a retired notice as resolved', () => {
    expect(historyStatus({ starts_at: ago(5), retired_at: ago(1) }).label).toBe('Resolved')
  })

  it('reports an open-ended live notice as ongoing', () => {
    expect(historyStatus({ starts_at: ago(2), ends_at: null }).label).toBe('Ongoing')
  })

  it('reports a window that has passed as ended, not ongoing', () => {
    // A maintenance window with an end date was reading "Ongoing" forever once
    // it lapsed, because only retired_at was consulted. Telling a customer that
    // finished maintenance is still in progress is worse than saying nothing.
    expect(historyStatus({ starts_at: ago(5), ends_at: ago(1) }).label).toBe('Ended')
  })

  it('treats a window that has not lapsed yet as ongoing', () => {
    const future = new Date(Date.now() + HOUR).toISOString()
    expect(historyStatus({ starts_at: ago(1), ends_at: future }).label).toBe('Ongoing')
  })

  it('prefers resolved over ended when both apply', () => {
    expect(historyStatus({ starts_at: ago(9), ends_at: ago(3), retired_at: ago(1) }).label)
      .toBe('Resolved')
  })
})

describe('noticeStaleness', () => {
  const HOUR = 3600 * 1000
  const live = (level, hoursAgo, extra = {}) => ({
    level,
    starts_at: new Date(Date.now() - hoursAgo * HOUR).toISOString(),
    ends_at: null,
    retired_at: null,
    ...extra,
  })

  it('reports how long a notice has been live', () => {
    expect(noticeStaleness(live('warning', 6)).label).toBe('6h')
    expect(noticeStaleness(live('warning', 0.5)).label).toBe('30m')
    expect(noticeStaleness(live('warning', 72)).label).toBe('3d')
  })

  it('flags a critical notice left up for hours', () => {
    // The failure mode this exists for: an agent forgets to retire it, and
    // customers keep seeing a red banner claiming an outage that is over.
    // A permanent critical banner is the in-portal version of a stale status
    // page — worse than none, because people stop believing it.
    expect(noticeStaleness(live('critical', 1)).isStale).toBe(false)
    expect(noticeStaleness(live('critical', 6)).isStale).toBe(true)
  })

  it('gives lower levels a longer leash', () => {
    // A warning about a slow sync can legitimately stand all day; a critical
    // cannot. Same threshold for both would train agents to ignore the flag.
    expect(noticeStaleness(live('warning', 6)).isStale).toBe(false)
    expect(noticeStaleness(live('warning', 30)).isStale).toBe(true)
    expect(noticeStaleness(live('info', 30)).isStale).toBe(false)
    expect(noticeStaleness(live('info', 100)).isStale).toBe(true)
  })

  it('says nothing about a retired notice', () => {
    // Already dealt with. Nagging about it is noise that devalues the flag.
    expect(noticeStaleness(live('critical', 99, { retired_at: new Date().toISOString() }))).toBeNull()
  })

  it('says nothing about a notice whose window has ended', () => {
    const ended = live('critical', 99, { ends_at: new Date(Date.now() - HOUR).toISOString() })
    expect(noticeStaleness(ended)).toBeNull()
  })

  it('says nothing about a notice that has not started yet', () => {
    const scheduled = { level: 'critical', starts_at: new Date(Date.now() + HOUR).toISOString() }
    expect(noticeStaleness(scheduled)).toBeNull()
  })

  it('treats an unknown level with the most cautious threshold', () => {
    // Unknown levels render as info, but for nagging purposes err toward
    // telling the agent rather than staying quiet.
    expect(noticeStaleness(live('apocalyptic', 6)).isStale).toBe(true)
  })
})
