import { describe, it, expect } from 'vitest'
import { linkify } from './linkify'

// Convenience: the URLs linkify decided to turn into <a>, and the text a reader
// actually sees once every segment is concatenated. The second matters as much
// as the first — a delimiter that survives into `rendered` is a visible defect
// even when the href is perfect.
const links = (s) => linkify(s).filter((x) => x.type === 'link').map((x) => x.value)
const rendered = (s) => linkify(s).map((x) => x.value).join('')

describe('linkify', () => {
  it('detects a bare url', () => {
    expect(links('see https://x.com/y here')).toEqual(['https://x.com/y'])
  })

  it('does not swallow a sentence-ending period', () => {
    expect(links('see https://x.com/y.')).toEqual(['https://x.com/y'])
    expect(rendered('see https://x.com/y.')).toBe('see https://x.com/y.')
  })

  // Mail clients wrap links in angle brackets, so every emailed reply hits this.
  it('consumes RFC-style angle brackets around a url', () => {
    const src = 'profile <https://www.linkedin.com/in/het1074/> end'
    expect(links(src)).toEqual(['https://www.linkedin.com/in/het1074/'])
    expect(rendered(src)).toBe('profile https://www.linkedin.com/in/het1074/ end')
  })

  it('handles a bracketed url as the entire body', () => {
    expect(rendered('<https://a.b/c>')).toBe('https://a.b/c')
  })

  it('handles bare and bracketed urls in one message', () => {
    const src = 'a https://one.com b <https://two.com/x> c'
    expect(links(src)).toEqual(['https://one.com', 'https://two.com/x'])
    expect(rendered(src)).toBe('a https://one.com b https://two.com/x c')
  })

  it('leaves surrounding parentheses as text', () => {
    const src = 'see (https://x.com/y) ok'
    expect(links(src)).toEqual(['https://x.com/y'])
    expect(rendered(src)).toBe(src)
  })

  // Degrades to the bare form rather than dropping the URL or eating the rest
  // of the message looking for a closing bracket.
  it('still links a url after an unclosed angle bracket', () => {
    expect(links('weird <https://x.com/y no close')).toEqual(['https://x.com/y'])
  })

  // A bare "<" near a url must not start a bracketed match: the alternation
  // requires the scheme immediately after the bracket.
  it('does not treat comparison operators as delimiters', () => {
    const src = '5 < 10 and https://x.com/y > 3'
    expect(links(src)).toEqual(['https://x.com/y'])
    expect(rendered(src)).toBe(src)
  })

  it('returns a single text segment when there is no url', () => {
    expect(linkify('plain text only')).toEqual([{ type: 'text', value: 'plain text only' }])
  })

  it('tolerates null and empty input', () => {
    expect(rendered(null)).toBe('')
    expect(rendered('')).toBe('')
  })

  // URL_RE is a module-level /g regex; without the lastIndex reset the second
  // call would resume mid-string and miss the match.
  it('is not affected by regex state across calls', () => {
    const src = 'go https://x.com/y now'
    expect(links(src)).toEqual(['https://x.com/y'])
    expect(links(src)).toEqual(['https://x.com/y'])
  })
})
