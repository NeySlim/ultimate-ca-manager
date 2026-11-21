import { describe, expect, it } from 'vitest'
import { sanitizeDownloadName, sanitizeFilename } from '../filename'

describe('invisible characters are removed before normalisation (idempotent)', () => {
  it('a joiner between a base and a mark leaves a stable name', () => {
    const once = sanitizeFilename('e͏́x')
    expect(sanitizeFilename(once)).toBe(once)
    expect(once).toBe('éx')
  })

  it.each(['\u17b4', '\u17b5', '\u180f'])('drops a filler character (%#)', (ch) => {
    expect(sanitizeFilename(`a${ch}b`)).toBe('ab')
  })
})

describe('sanitizeDownloadName keeps the suffix a page adds', () => {
  const longId = 'k'.repeat(200)

  it('keeps <label>.pub and <label>-cert.pub distinct for a very long label', () => {
    const pub = sanitizeDownloadName(longId, '.pub')
    const cert = sanitizeDownloadName(longId, '-cert.pub')
    expect(pub.endsWith('.pub')).toBe(true)
    expect(cert.endsWith('-cert.pub')).toBe(true)
    expect(pub).not.toBe(cert)
  })

  it('is idempotent: a second pass over the result changes nothing', () => {
    for (const [label, suffix] of [[longId, '-cert.pub'], [longId, '.pub'], ['漢'.repeat(300), '-cross-12.pem'],
      ['\u{20000}'.repeat(100), '-cert.pub'], ['CON', '.pub'], ['example.com', '-cross-3.pem']]) {
      const name = sanitizeDownloadName(label, suffix)
      expect(sanitizeDownloadName(name)).toBe(name)
      expect(name.endsWith(suffix)).toBe(true)
      expect(new TextEncoder().encode(name).length).toBeLessThanOrEqual(255)
    }
  })

  it('without a suffix it behaves as before', () => {
    expect(sanitizeDownloadName('example.com.pem')).toBe('example.com.pem')
    expect(sanitizeDownloadName('a/b.crt')).toBe('a_b.crt')
  })
})
