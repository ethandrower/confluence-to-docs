// Split plain text into {type:'text'|'link', value} segments, detecting bare
// http(s) URLs. This produces DATA, not markup: callers render link segments as
// <a> and text segments as interpolated text, so message bodies never go
// through v-html and the zero-XSS property of the ticket views is preserved.
//
// Two forms are matched. First an RFC-style bracketed URL (<https://x/y>):
// mail clients wrap links this way routinely, so an emailed reply arrives with
// delimiters that must be consumed rather than rendered as stray text. Second a
// bare URL, whose trailing char is excluded from common sentence punctuation so
// a URL ending a sentence ("see https://x.com/y.") doesn't swallow the period.
// Brackets already bound the first form, so it needs no such trimming.
const URL_RE = /<(https?:\/\/[^\s<>]+)>|(https?:\/\/[^\s<>()]+[^\s<>().,;:!?'"])/g

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
    // m[1] is the bracketed form's inner URL, m[2] the bare form. Either way
    // `last` advances past the whole match, so delimiters never reach output.
    segments.push({ type: 'link', value: m[1] || m[2] })
    last = m.index + m[0].length
  }
  if (last < src.length) {
    segments.push({ type: 'text', value: src.slice(last) })
  }
  if (!segments.length) segments.push({ type: 'text', value: src })
  return segments
}
