/** downloadBlob is the one place a download name is made safe (#448). */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { downloadBlob } from '../utils'
import { sanitizeDownloadName, sanitizeFilename } from '../filename'
import { exportFileName } from '../exportDownload'

let saved
beforeEach(() => {
  saved = []
  URL.createObjectURL = vi.fn(() => 'blob:x')
  URL.revokeObjectURL = vi.fn()
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () { saved.push(this.download) })
})
afterEach(() => vi.restoreAllMocks())

const savedAs = (name) => { downloadBlob(new Blob(['x']), name); return saved.at(-1) }

describe('downloadBlob filename', () => {
  it('leaves names the code already produces untouched', () => {
    for (const n of ['audit-logs.csv', 'ucm-backup-2026-11-19.ucmbkp', 'example.com.pem', 'ca.tar.gz',
      'ucm-report-expiry.pdf', 'discovered_certificates.json', 'ucm-logs-20261119101010.zip',
      exportFileName('テスト用', 'pem'), exportFileName('Café crème', 'p12')]) {
      expect(savedAs(n)).toBe(n)
      expect(sanitizeDownloadName(sanitizeDownloadName(n))).toBe(n)
    }
  })

  it('removes separators, controls and dot tricks but keeps non-ASCII', () => {
    expect(savedAs('テスト/用:CA.pem')).toBe('テスト_用_CA.pem')
    expect(savedAs('../../etc/passwd.crt')).toBe('_.._etc_passwd.crt')
  })

  it('never saves a separator, control, leading dot or empty name', () => {
    for (const n of ['a/b\\c:d.pem', '..', '../x.key', '.hidden.pem', 'a\nb.csr', '', null, undefined, '.pem', 'x/.']) {
      const out = savedAs(n)
      expect(out).not.toMatch(/[/\\:\u0000-\u001f]/)
      expect(out.startsWith('.')).toBe(false)
      expect(out).not.toBe('')
    }
  })

  it('keeps the extension when the label is clipped', () => {
    const out = savedAs(`${'あ'.repeat(500)}.pem`)
    expect(out.endsWith('.pem')).toBe(true)
    expect(new TextEncoder().encode(out).length).toBeLessThanOrEqual(255)
    expect(savedAs(`${'a'.repeat(500)}.p12`).endsWith('.p12')).toBe(true)
  })

  it('splits only the last short ASCII suffix, so multi-dot names keep their dots', () => {
    expect(sanitizeDownloadName('example.com.pem')).toBe('example.com.pem')
    expect(sanitizeDownloadName('a/b.c/d')).toBe('a_b.c_d')
    expect(sanitizeDownloadName('con.pem')).toBe('con_.pem')
  })
})

describe('sanitizeFilename joiners', () => {
  it('drops ZWNJ and ZWJ instead of turning them into underscores', () => {
    expect(sanitizeFilename('می‌خواهم')).toBe('میخواهم')
    expect(sanitizeFilename('a‍b')).toBe('ab')
  })
})

describe('a device name before the extension', () => {
  it('is suffixed whatever the extensions are', () => {
    expect(sanitizeDownloadName('con.tar.gz')).toBe('con_.tar.gz')
    expect(sanitizeDownloadName('aux.pem')).toBe('aux_.pem')
    expect(sanitizeDownloadName('con_.tar.gz')).toBe('con_.tar.gz')
  })
})
