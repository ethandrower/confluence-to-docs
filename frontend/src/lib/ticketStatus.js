// Single source of truth for ticket status vocabulary + thread time formatting.
// Status labels/tones are AUDIENCE-SPECIFIC by design: the customer and admin
// UIs intentionally describe the same underlying status differently. Do not
// collapse the two — pick with `perspective` ('customer' | 'staff').

export const TICKET_STATUS = {
  open:                { customerLabel: 'Open',           staffLabel: 'Open',                customerTone: 'info',    staffTone: 'info'    },
  waiting_on_support:  { customerLabel: 'Awaiting reply', staffLabel: 'Needs reply',         customerTone: 'info',    staffTone: 'warning' },
  waiting_on_customer: { customerLabel: 'Action needed',  staffLabel: 'Waiting on customer', customerTone: 'warning', staffTone: 'info'    },
  resolved:            { customerLabel: 'Resolved',       staffLabel: 'Resolved',            customerTone: 'success', staffTone: 'success' },
  closed:              { customerLabel: 'Closed',         staffLabel: 'Closed',              customerTone: 'muted',   staffTone: 'muted'   },
}

export const STATUS_KEYS = ['open', 'waiting_on_support', 'waiting_on_customer', 'resolved', 'closed']

export function statusLabel(key, perspective = 'customer') {
  const s = TICKET_STATUS[key]
  if (!s) return key
  return perspective === 'staff' ? s.staffLabel : s.customerLabel
}

export function statusTone(key, perspective = 'customer') {
  const s = TICKET_STATUS[key]
  if (!s) return 'muted'
  return perspective === 'staff' ? s.staffTone : s.customerTone
}

export function msgTime(iso) {
  return new Date(iso).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

export function dayLabel(iso) {
  const d = new Date(iso)
  const now = new Date()
  const startOf = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const days = Math.round((startOf(now) - startOf(d)) / 86400000)
  if (days === 0) return 'Today'
  if (days === 1) return 'Yesterday'
  const opts = { weekday: 'long', month: 'long', day: 'numeric' }
  if (d.getFullYear() !== now.getFullYear()) opts.year = 'numeric'
  return d.toLocaleDateString(undefined, opts)
}

export function relDate(iso, { short = false } = {}) {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000)
  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 7) return short ? `${days}d ago` : `${days} days ago`
  return new Date(iso).toLocaleDateString(undefined,
    short ? { month: 'short', day: 'numeric' } : { month: 'short', day: 'numeric', year: 'numeric' })
}

export function fullDate(iso) {
  return new Date(iso).toLocaleString(undefined,
    { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' })
}
