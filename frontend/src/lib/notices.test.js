import { describe, it, expect } from 'vitest'
import { LEVEL_RANK, orderNotices, noticeLevel } from './notices'

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
