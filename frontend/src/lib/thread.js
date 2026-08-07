import { dayLabel, msgTime } from '@/lib/ticketStatus'

const GROUP_GAP_MS = 5 * 60 * 1000  // start a new visual group after a >5min gap

export function isMine(message, perspective) {
  return perspective === 'admin' ? !!message.is_staff : !message.is_staff
}

// Strip a single trailing "— CiteMed Support" signature line that duplicates the
// header badge. Conservative: only the exact staff sign-off, only at the very end.
export function stripSignature(body) {
  if (!body) return body
  return body.replace(/\s*\n?\s*—\s*CiteMed Support\s*$/, '').replace(/[ \t]+$/, '')
}

// Emailed replies arrive with stacked blank lines — mail clients pad before a
// signature, and stripping the quoted chain leaves more behind — which renders
// as a large gap mid-bubble. Collapse any run of 3+ newlines to one blank line;
// paragraph breaks (exactly two) are preserved. Runs at either end are dropped
// outright, since under white-space:pre-wrap they render as dead space against
// the bubble edge rather than as a gap between paragraphs.
//
// Matching \r\n as a single newline is load-bearing, not defensive: SMTP bodies
// are CRLF-delimited, so a plain /\n{3,}/ sees \r between each \n and never
// fires on exactly the emailed messages this exists to tidy.
const NL = /(?:\r\n|\r|\n)/.source

export function collapseBlankLines(body) {
  if (!body) return body
  return body
    .replace(new RegExp(`(?:${NL}){3,}`, 'g'), '\n\n')
    .replace(new RegExp(`^(?:${NL})+`), '')
    .replace(new RegExp(`(?:${NL})+$`), '')
}

function dayKey(iso) {
  const d = new Date(iso)
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
}

function badgeFor(m) {
  if (m.is_internal) return 'Internal'
  if (m.is_staff) return 'CiteMed'
  return null
}

// First staff reply the customer hasn't seen yet (customer perspective only).
function firstUnseenId(messages, perspective, lastReadAt) {
  if (perspective !== 'customer' || !lastReadAt) return null
  const lr = new Date(lastReadAt).getTime()
  for (const m of messages) {
    if (m.is_staff && !m.is_internal && new Date(m.created_at).getTime() > lr) return m.id
  }
  return null
}

export function groupMessages(messages, perspective, { lastReadAt = null } = {}) {
  const out = []
  const newId = firstUnseenId(messages, perspective, lastReadAt)
  let cur = null
  let lastDay = null
  let newDone = false

  for (const m of messages) {
    const dk = dayKey(m.created_at)
    if (dk !== lastDay) {
      out.push({ kind: 'day', key: `day-${dk}`, label: dayLabel(m.created_at) })
      lastDay = dk
      cur = null
    }
    if (newId != null && m.id === newId && !newDone) {
      out.push({ kind: 'new', key: 'new' })
      newDone = true
      cur = null
    }
    const mine = isMine(m, perspective)
    const internal = !!m.is_internal
    const gap = cur ? new Date(m.created_at).getTime() - new Date(cur._lastAt).getTime() : Infinity
    if (!cur || cur.mine !== mine || cur.isInternal !== internal || cur.name !== m.author_name || gap > GROUP_GAP_MS) {
      cur = {
        kind: 'group', key: `g-${m.id}`, mine, isInternal: internal,
        badge: badgeFor(m), viaEmail: m.origin === 'email', name: m.author_name,
        time: msgTime(m.created_at), messages: [], _lastAt: m.created_at,
      }
      out.push(cur)
    }
    cur.messages.push(m)
    cur._lastAt = m.created_at
  }
  return out
}
