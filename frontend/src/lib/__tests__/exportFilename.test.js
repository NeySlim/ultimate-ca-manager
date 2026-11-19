/**
 * Export filenames are built from attacker-reachable data (DUP-FE-010).
 *
 * `name` is a certificate CN, an ACME domain or a CA description — all of which
 * can arrive from outside the operator's trust boundary (an externally
 * submitted CSR, an ACME order, a SCEP/EST enrolment, a discovery scan). RFC
 * 5280 puts no filesystem constraints on a CN: `/`, `\`, `:`, `..` and control
 * characters including newlines are all legal there.
 *
 * `exportFileName` interpolated it verbatim, and two of the five downloadExport
 * callers write a file that contains a PRIVATE KEY.
 */
import { describe, expect, it, vi } from 'vitest'

const downloadBlob = vi.hoisted(() => vi.fn())
vi.mock('../utils', () => ({ downloadBlob }))

import { exportFileName, sanitizeFilename } from '../exportDownload'

describe('sanitizeFilename', () => {
  it('collapses anything that is not a letter, a digit or ._- to a single underscore', () => {
    expect(sanitizeFilename('a/b\\c:d')).toBe('a_b_c_d')
    expect(sanitizeFilename('spaces   and %%% signs')).toBe('spaces_and_signs')
  })

  it('keeps a name written in another script (#448)', () => {
    expect(sanitizeFilename('テスト用')).toBe('テスト用')
    expect(sanitizeFilename('Сервер №1')).toBe('Сервер_1')
    expect(sanitizeFilename('Café crème')).toBe('Café_crème')
    expect(sanitizeFilename('हिन्दी')).toBe('हिन्दी')
  })

  it('drops bidi marks, fullwidth separators and symbols', () => {
    expect(sanitizeFilename('n\u202eb')).toBe('n_b')
    expect(sanitizeFilename('a\uff0fb\uff3cc')).toBe('a_b_c')
    expect(sanitizeFilename('a\u2028b\u200ec')).toBe('a_b_c')
    expect(sanitizeFilename('🔐🔐')).toBe('_')
  })

  it('strips control characters, newlines included', () => {
    expect(sanitizeFilename('web\r\nContent-Type: evil')).toBe('web_Content-Type_evil')
    expect(sanitizeFilename('tab\there')).toBe('tab_here')
  })

  it('never returns a traversal segment', () => {
    expect(sanitizeFilename('..')).not.toBe('..')
    expect(sanitizeFilename('.')).not.toBe('.')
    expect(sanitizeFilename('../../etc/passwd')).not.toMatch(/(^|[\\/])\.\.([\\/]|$)/)
    expect(sanitizeFilename('../../etc/passwd')).not.toMatch(/[\\/]/)
  })

  it('never returns an empty name', () => {
    expect(sanitizeFilename('')).toBeTruthy()
    expect(sanitizeFilename(null)).toBeTruthy()
    expect(sanitizeFilename(undefined)).toBeTruthy()
    expect(sanitizeFilename('///')).toBeTruthy()
  })

  it('does not hand back a hidden file', () => {
    expect(sanitizeFilename('.bashrc').startsWith('.')).toBe(false)
    expect(sanitizeFilename('...hidden').startsWith('.')).toBe(false)
  })

  it('caps the length so the name survives the filesystem', () => {
    const long = 'a'.repeat(4000)
    expect(sanitizeFilename(long).length).toBeLessThanOrEqual(128)
    expect(sanitizeFilename(long).length).toBeGreaterThan(0)
  })

  it('leaves an ordinary CN untouched', () => {
    expect(sanitizeFilename('web.example.com')).toBe('web.example.com')
    expect(sanitizeFilename('Corp-Issuing_CA.01')).toBe('Corp-Issuing_CA.01')
  })
})

describe('exportFileName applies it', () => {
  it('keeps a hostile CN inside a single path segment', () => {
    expect(exportFileName('../../root/.ssh/authorized_keys', 'key')).not.toMatch(/[\\/]/)
    expect(exportFileName('evil/../../etc/cron.d/x', 'pem')).not.toMatch(/[\\/]/)
  })

  it('still appends the real extension after sanitising', () => {
    expect(exportFileName('a/b', 'pkcs12')).toBe('a_b.p12')
    expect(exportFileName('web space', 'pem')).toBe('web_space.pem')
    // The extension itself must not be swallowed by the sanitiser.
    expect(exportFileName('..', 'pkcs7').endsWith('.p7b')).toBe(true)
  })

  it('does not change the name of a well-behaved export', () => {
    expect(exportFileName('web.example.com', 'pkcs7')).toBe('web.example.com.p7b')
    expect(exportFileName('web.example.com', 'p7c')).toBe('web.example.com.p7c')
  })
})
