import { describe, it, expect } from 'vitest'
import {
  blankRow, toggleModule, rowErrors, isRowValid, isRowDirty, displayName,
  summarise, groupByModule, withoutModules, statusOf, submitBlockers,
} from './roster.js'

const MODULES = [
  { key: 'literature', label: 'Literature' },
  { key: 'citesource', label: 'CiteSource' },
  { key: 'pathways', label: 'Pathways' },
]

const user = (over = {}) => ({
  id: 1, first_name: 'Anna', last_name: 'Lee', email: 'anna@x.com',
  modules: ['literature'], role_type: 'viewer',
  added_at: null, activation_email_sent_at: null, ...over,
})

describe('toggleModule', () => {
  it('adds and removes', () => {
    expect(toggleModule([], 'literature')).toEqual(['literature'])
    expect(toggleModule(['literature'], 'literature')).toEqual([])
  })

  it('returns a new array rather than mutating', () => {
    // Mutating in place works until the row is copied somewhere, and then
    // silently stops updating the screen.
    const before = ['literature']
    const after = toggleModule(before, 'pathways')
    expect(before).toEqual(['literature'])
    expect(after).not.toBe(before)
  })

  it('survives a missing modules array', () => {
    expect(toggleModule(undefined, 'literature')).toEqual(['literature'])
  })
})

describe('rowErrors', () => {
  it('requires an email and nothing else', () => {
    expect(rowErrors(blankRow()).email).toBeTruthy()
    expect(rowErrors({ ...blankRow(), email: 'a@x.com' })).toEqual({})
  })

  it('does not object to a person with no modules', () => {
    // Somebody who needs the portal to raise tickets but no product seats is
    // a real thing to record, not an error.
    const errors = rowErrors({ ...blankRow(), email: 'a@x.com', modules: [] })
    expect(errors.modules).toBeUndefined()
  })

  it('rejects something that is not an address', () => {
    expect(rowErrors({ email: 'anna' }).email).toBeTruthy()
    expect(rowErrors({ email: 'anna@local' }).email).toBeTruthy()
  })

  it('catches a duplicate against the people already listed', () => {
    const errors = rowErrors({ email: 'ANNA@x.com' },
                             { existingEmails: ['anna@x.com'] })
    expect(errors.email).toMatch(/already/)
  })

  it('compares addresses case-insensitively both ways', () => {
    expect(rowErrors({ email: 'anna@x.com' },
                     { existingEmails: ['Anna@X.com'] }).email).toBeTruthy()
  })
})

describe('isRowValid', () => {
  it('agrees with rowErrors', () => {
    expect(isRowValid({ email: 'a@x.com' })).toBe(true)
    expect(isRowValid({ email: '' })).toBe(false)
  })
})

describe('isRowDirty', () => {
  it('is false for an untouched row', () => {
    expect(isRowDirty(blankRow())).toBe(false)
  })

  it('is true once anything is typed', () => {
    expect(isRowDirty({ ...blankRow(), first_name: 'A' })).toBe(true)
    expect(isRowDirty({ ...blankRow(), modules: ['literature'] })).toBe(true)
  })

  it('ignores the role, which always has a value', () => {
    expect(isRowDirty({ ...blankRow(), role_type: 'admin' })).toBe(false)
  })
})

describe('displayName', () => {
  it('prefers the name', () => {
    expect(displayName(user())).toBe('Anna Lee')
  })

  it('falls back to the email rather than showing an empty cell', () => {
    expect(displayName(user({ first_name: '', last_name: '' }))).toBe('anna@x.com')
  })

  it('copes with only one of the two names', () => {
    expect(displayName(user({ last_name: '' }))).toBe('Anna')
  })
})

describe('summarise', () => {
  it('counts from the timestamps, not from any flag', () => {
    const rows = [
      user({ id: 1 }),
      user({ id: 2, added_at: '2026-09-01T00:00:00Z' }),
      user({ id: 3, added_at: '2026-09-01T00:00:00Z',
             activation_email_sent_at: '2026-09-02T00:00:00Z' }),
    ]
    expect(summarise(rows)).toEqual({ total: 3, added: 2, invited: 1, unassigned: 0 })
  })

  it('counts people with no module so they can be chased', () => {
    expect(summarise([user({ modules: [] })]).unassigned).toBe(1)
  })

  it('handles an empty roster', () => {
    expect(summarise([])).toEqual({ total: 0, added: 0, invited: 0, unassigned: 0 })
  })
})

describe('groupByModule', () => {
  it('puts a person under every module they hold', () => {
    const rows = [user({ modules: ['literature', 'pathways'] })]
    const groups = groupByModule(rows, MODULES)
    expect(groups.find((g) => g.key === 'literature').users).toHaveLength(1)
    expect(groups.find((g) => g.key === 'pathways').users).toHaveLength(1)
    expect(groups.find((g) => g.key === 'citesource').users).toHaveLength(0)
  })

  it('keeps empty modules, which is the point', () => {
    // "Nobody has Vigilance yet" is exactly what the customer needs to notice
    // before they submit.
    const groups = groupByModule([], MODULES)
    expect(groups).toHaveLength(3)
    expect(groups.every((g) => g.users.length === 0)).toBe(true)
  })

  it('follows the order the options were given', () => {
    expect(groupByModule([], MODULES).map((g) => g.key))
      .toEqual(['literature', 'citesource', 'pathways'])
  })
})

describe('withoutModules', () => {
  it('finds people who would otherwise be invisible in the expanders', () => {
    const rows = [user({ id: 1, modules: [] }), user({ id: 2 })]
    expect(withoutModules(rows).map((u) => u.id)).toEqual([1])
  })
})

describe('statusOf', () => {
  it('distinguishes set-up-but-not-told from told', () => {
    expect(statusOf(user())).toBe('pending')
    expect(statusOf(user({ added_at: 'x' }))).toBe('added')
    expect(statusOf(user({ added_at: 'x', activation_email_sent_at: 'y' })))
      .toBe('invited')
  })
})

describe('submitBlockers', () => {
  it('blocks an empty roster', () => {
    expect(submitBlockers([])).toHaveLength(1)
  })

  it('blocks while an import is still running', () => {
    expect(submitBlockers([user()], { importRunning: true })).toHaveLength(1)
  })

  it('does not block on a person with no modules', () => {
    // The customer knows their own organisation better than this form does.
    expect(submitBlockers([user({ modules: [] })])).toEqual([])
  })
})
