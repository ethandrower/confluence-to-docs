import { describe, it, expect } from 'vitest'
import { collapseBlankLines, stripSignature } from './thread'

describe('collapseBlankLines', () => {
  // The reason this function matches \r\n rather than \n. SMTP bodies are
  // CRLF-delimited, so a plain /\n{3,}/ never sees three consecutive \n and
  // does nothing to the emailed replies this exists to tidy. If someone
  // "simplifies" the regex back, this is the test that fails.
  it('collapses a CRLF gap, not just LF', () => {
    expect(collapseBlankLines('a\r\n\r\n\r\n\r\nb')).toBe('a\n\nb')
  })

  it('collapses an LF gap too', () => {
    expect(collapseBlankLines('a\n\n\n\nb')).toBe('a\n\nb')
  })

  it('preserves a paragraph break', () => {
    expect(collapseBlankLines('a\n\nb')).toBe('a\n\nb')
    expect(collapseBlankLines('a\r\n\r\nb')).toBe('a\n\nb')
  })

  it('preserves a single line break', () => {
    expect(collapseBlankLines('a\r\nb')).toBe('a\r\nb')
    expect(collapseBlankLines('a\nb')).toBe('a\nb')
  })

  // Under white-space:pre-wrap these render as dead space against the bubble
  // edge, so they are dropped rather than collapsed to a paragraph break.
  it('drops leading and trailing newline runs', () => {
    expect(collapseBlankLines('Working on it.\r\n\r\n\r\n\r\n')).toBe('Working on it.')
    expect(collapseBlankLines('\r\n\r\n\r\nHello')).toBe('Hello')
    expect(collapseBlankLines('\n\nHi\n\n')).toBe('Hi')
  })

  it('leaves a body with no blank runs untouched', () => {
    expect(collapseBlankLines('just one line')).toBe('just one line')
  })

  it('tolerates null and empty input', () => {
    expect(collapseBlankLines(null)).toBe(null)
    expect(collapseBlankLines('')).toBe('')
  })
})

describe('stripSignature', () => {
  it('strips the trailing staff sign-off', () => {
    expect(stripSignature('Thanks for reaching out.\n\n— CiteMed Support')).toBe(
      'Thanks for reaching out.')
  })

  // Conservative by design: only at the very end, so a mid-body mention stays.
  it('leaves a mid-body mention alone', () => {
    const src = '— CiteMed Support will follow up shortly.'
    expect(stripSignature(src)).toBe(src)
  })

  it('tolerates null and empty input', () => {
    expect(stripSignature(null)).toBe(null)
    expect(stripSignature('')).toBe('')
  })
})
