/** The rows of a comparison: the same lines for every certificate, those that differ marked. */
import { describe, it, expect } from 'vitest'
import { compareRows } from '../compareRows'

const t = (k) => k
const base = {
  id: 1, common_name: 'a.example', subject: 'CN=a.example', issuer: 'CN=Root', valid_from: '2026-01-01T00:00:00Z', valid_to: '2027-01-01T00:00:00Z',
  key_type: 'RSA 2048', serial_number: '255', thumbprint_sha1: 'AA', thumbprint_sha256: 'BB',
  extensions: {
    subject_alt_names: { entries: [{ type: 'DNS', value: 'a.example' }] },
    key_usage: { usages: ['digitalSignature'], critical: true },
    extended_key_usage: { usages: [{ name: 'serverAuth' }] },
    basic_constraints: { ca: false, critical: true },
  },
}

const row = (rows, key) => rows.find((r) => r.key === key)

describe('compareRows', () => {
  it('gives every certificate the same lines, in the brief order', () => {
    const rows = compareRows([base, { ...base, id: 2 }], t)
    expect(rows.slice(0, 9).map((r) => r.key)).toEqual(['subject', 'issuer', 'validity', 'key', 'san', 'usages', 'sha1', 'sha256', 'serial'])
    expect(row(rows, 'serial').values).toEqual(['FF', 'FF'])
    expect(row(rows, 'usages').values[0]).toBe('Digital Signature\nTLS Web Server Authentication')
    // The extensions shown above are not repeated; the others follow, one line each
    expect(rows.slice(9).map((r) => r.key)).toEqual(['basic_constraints'])
  })

  it('marks a line that differs on any certificate, and only those', () => {
    const other = { ...base, id: 2, key_type: 'EC P-256', thumbprint_sha256: 'CC' }
    const rows = compareRows([base, { ...base, id: 3 }, other], t)
    expect(row(rows, 'key').differs).toBe(true)
    expect(row(rows, 'sha256').differs).toBe(true)
    expect(row(rows, 'subject').differs).toBe(false)
    expect(row(rows, 'issuer').differs).toBe(false)
  })

  it('shows an extension one certificate lacks as absent, and as a difference', () => {
    const withPolicy = { ...base, id: 2, extensions: { ...base.extensions, crl_distribution_points: { urls: ['http://crl.example/r.crl'] } } }
    const rows = compareRows([base, withPolicy], t)
    const crl = row(rows, 'crl_distribution_points')
    expect(crl.values).toEqual(['—', 'http://crl.example/r.crl'])
    expect(crl.differs).toBe(true)
  })

  it('reads the names from san_combined when the extension is not parsed', () => {
    const a = { ...base, extensions: {}, san_combined: 'DNS:a, DNS:b' }
    expect(row(compareRows([a, a], t), 'san').values[0]).toBe('DNS:a\nDNS:b')
  })
})
