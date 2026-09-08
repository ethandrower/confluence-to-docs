/**
 * Roster form logic (REV-45).
 *
 * The view renders; this decides. Kept separate for the same reason
 * `folders.js` is: the awkward cases in a roster form are all data questions —
 * is this row complete, which modules is this person licensed for, who is
 * already set up — and they are far cheaper to test here than through a
 * mounted component.
 */

/** A blank row for the "add a person" form. */
export function blankRow() {
  return {
    first_name: '',
    last_name: '',
    email: '',
    modules: [],
    role_type: 'viewer',
    note: '',
  }
}

/**
 * Immutable toggle for a module checkbox.
 *
 * Returns a NEW array so Vue's reactivity sees the change — mutating in place
 * and relying on deep reactivity is the kind of thing that works until the row
 * is copied somewhere.
 */
export function toggleModule(modules, key) {
  const current = modules || []
  return current.includes(key)
    ? current.filter((m) => m !== key)
    : [...current, key]
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/**
 * Per-field problems with one row, as {field: message}.
 *
 * Only the email is required. A person with no modules is a real thing to want
 * to record — somebody who needs portal access to raise tickets but no product
 * seats — so it is a warning the form can show, not an error that blocks.
 */
export function rowErrors(row, { existingEmails = [] } = {}) {
  const errors = {}
  const email = (row?.email || '').trim().toLowerCase()

  if (!email) {
    errors.email = 'An email address is required.'
  } else if (!EMAIL_RE.test(email)) {
    errors.email = 'That does not look like an email address.'
  } else if (existingEmails.map((e) => e.toLowerCase()).includes(email)) {
    errors.email = 'That person is already on the list.'
  }

  return errors
}

export function isRowValid(row, options) {
  return Object.keys(rowErrors(row, options)).length === 0
}

/** True when a row has anything typed into it — used to warn before discarding. */
export function isRowDirty(row) {
  if (!row) return false
  return Boolean(
    (row.first_name || '').trim() ||
    (row.last_name || '').trim() ||
    (row.email || '').trim() ||
    (row.note || '').trim() ||
    (row.modules || []).length,
  )
}

/** "Anna Lee", or the email when we have no name — never an empty cell. */
export function displayName(user) {
  const name = [user?.first_name, user?.last_name].filter(Boolean).join(' ').trim()
  return name || user?.email || ''
}

/**
 * Counts for the header strip.
 *
 * `added` and `invited` are read from the timestamps rather than from any
 * boolean, because those timestamps are the only honest source — the form has
 * no way to set them and must not imply that it does.
 */
export function summarise(users) {
  const list = users || []
  return {
    total: list.length,
    added: list.filter((u) => u.added_at).length,
    invited: list.filter((u) => u.activation_email_sent_at).length,
    unassigned: list.filter((u) => !(u.modules || []).length).length,
  }
}

/**
 * One group per module, in the order the options were given.
 *
 * A person appears under every module they have, which is why this cannot be
 * the primary editing surface — editing "Anna" under Literature and again
 * under Pathways would be editing one row from two places. The expanders are a
 * read view over the roster; the table is where rows are edited.
 *
 * Modules with nobody in them are kept, because "nobody has Vigilance yet" is
 * exactly the thing the customer needs to notice before submitting.
 */
export function groupByModule(users, moduleOptions) {
  return (moduleOptions || []).map((option) => ({
    key: option.key,
    label: option.label,
    users: (users || []).filter((u) => (u.modules || []).includes(option.key)),
  }))
}

/** People with no module at all — surfaced separately so they are not lost. */
export function withoutModules(users) {
  return (users || []).filter((u) => !(u.modules || []).length)
}

/**
 * What the status columns should read as.
 *
 * Three states, not two: a person can be set up but not yet told, and that gap
 * is the interesting one for a CS person chasing an activation. Returning a
 * key rather than a string keeps the wording in the template.
 */
export function statusOf(user) {
  if (user?.activation_email_sent_at) return 'invited'
  if (user?.added_at) return 'added'
  return 'pending'
}

/**
 * Can this roster be submitted?
 *
 * Deliberately permissive: an empty roster is the only hard block. Warnings
 * (somebody with no modules) are shown but do not prevent submitting, because
 * the customer knows their own organisation better than this form does.
 */
export function submitBlockers(users, { importRunning = false } = {}) {
  const blockers = []
  if (!(users || []).length) blockers.push('Add at least one person.')
  if (importRunning) blockers.push('An import is still being processed.')
  return blockers
}
