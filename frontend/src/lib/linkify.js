// Split plain text into {type:'text'|'link', value} segments, detecting bare
// http(s) URLs. This produces DATA, not markup: callers render link segments as
// <a> and text segments as interpolated text, so message bodies never go
// through v-html and the zero-XSS property of the ticket views is preserved.
//
// The trailing char is excluded from common sentence punctuation so a URL at
// the end of a sentence ("see https://x.com/y.") doesn't swallow the period.
const URL_RE = /(https?:\/\/[^\s<>()]+[^\s<>().,;:!?'"])/g

export function linkify(text) {
  const src = text == null ? '' : String(text)
  const segments = []
  let last = 0
  let m
  URL_RE.lastIndex = 0
  while ((m = URL_RE.exec(src)) !== null) {
    if (m.index > last) {
      segments.push({ type: 'text', value: src.slice(last, m.index) })
    }
    segments.push({ type: 'link', value: m[0] })
    last = m.index + m[0].length
  }
  if (last < src.length) {
    segments.push({ type: 'text', value: src.slice(last) })
  }
  if (!segments.length) segments.push({ type: 'text', value: src })
  return segments
}
