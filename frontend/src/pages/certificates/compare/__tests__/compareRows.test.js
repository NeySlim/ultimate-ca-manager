/**
 * The rows of a comparison: the same lines for every certificate, those that differ marked, and in a
 * list (names, usages, extensions) each element marked common to all of them or not.
 */
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
const withNames = (id, ...names) => ({ ...base, id, extensions: { ...base.extensions, subject_alt_names: { entries: names.map((value) => ({ type: 'DNS', value })) } } })

const row = (rows, key) => rows.find((r) => r.key === key)
const marks = (r, i) => r.items[i].map((e) => `${e.common ? '=' : '+'}${e.value}`)

describe('compareRows', () => {
  it('gives every certificate the same lines, in the brief order', () => {
    const rows = compareRows([base, { ...base, id: 2 }], t)
    expect(rows.slice(0, 9).map((r) => r.key)).toEqual(['subject', 'issuer', 'validity', 'key', 'san', 'usages', 'sha1', 'sha256', 'serial'])
    expect(row(rows, 'serial').values).toEqual(['FF', 'FF'])
    expect(row(rows, 'usages').values[0]).toEqual(['Digital Signature', 'TLS Web Server Authentication'])
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

  it('shows an extension one certificate lacks as an empty list, its elements as a difference', () => {
    const withPolicy = { ...base, id: 2, extensions: { ...base.extensions, crl_distribution_points: { urls: ['http://crl.example/r.crl'] } } }
    const rows = compareRows([base, withPolicy], t)
    const crl = row(rows, 'crl_distribution_points')
    expect(crl.values).toEqual([[], ['http://crl.example/r.crl']])
    expect(crl.differs).toBe(true)
    expect(marks(crl, 1)).toEqual(['+http://crl.example/r.crl'])
    // One value at most on each side: it differs as a whole, no element to point at
    expect(crl.byElement).toBe(false)
  })

  it('reads the names from san_combined when the extension is not parsed', () => {
    const a = { ...base, extensions: {}, san_combined: 'DNS:a, DNS:b' }
    expect(row(compareRows([a, a], t), 'san').values[0]).toEqual(['DNS:a', 'DNS:b'])
  })

  it('compares a list element by element: the common ones and the one each has alone', () => {
    const san = row(compareRows([withNames(1, 'a.example', 'b.example'), withNames(2, 'b.example', 'c.example')], t), 'san')
    expect(san.differs).toBe(true)
    expect(marks(san, 0)).toEqual(['+DNS: a.example', '=DNS: b.example'])
    expect(marks(san, 1)).toEqual(['=DNS: b.example', '+DNS: c.example'])
    expect(san.byElement).toBe(true)
  })

  it('marks the usage one certificate has more, the others it shares staying common', () => {
    const client = { ...base, id: 2, extensions: { ...base.extensions, extended_key_usage: { usages: [{ name: 'serverAuth' }, { name: 'clientAuth' }] } } }
    const usages = row(compareRows([base, client], t), 'usages')
    expect(usages.differs).toBe(true)
    expect(marks(usages, 0)).toEqual(['=Digital Signature', '=TLS Web Server Authentication'])
    expect(marks(usages, 1)).toEqual(['=Digital Signature', '=TLS Web Server Authentication', '+TLS Web Client Authentication'])
  })

  it('reads the key usages one by one: the one a certificate adds is the element marked', () => {
    const more = { ...base, id: 2, extensions: { ...base.extensions, key_usage: { usages: ['digitalSignature', 'keyEncipherment'] } } }
    const usages = row(compareRows([base, more], t), 'usages')
    expect(marks(usages, 1)).toEqual(['=Digital Signature', '+Key Encipherment', '=TLS Web Server Authentication'])
  })

  it('holds the same elements in another order as identical', () => {
    const san = row(compareRows([withNames(1, 'a.example', 'b.example'), withNames(2, 'b.example', 'a.example')], t), 'san')
    expect(san.differs).toBe(false)
    expect(marks(san, 1)).toEqual(['=DNS: b.example', '=DNS: a.example'])
  })

  it('holds an element common only when every certificate carries it', () => {
    const rows = compareRows([withNames(1, 'a.example', 'b.example'), withNames(2, 'a.example', 'b.example'), withNames(3, 'a.example')], t)
    expect(marks(row(rows, 'san'), 0)).toEqual(['=DNS: a.example', '+DNS: b.example'])
    expect(marks(row(rows, 'san'), 2)).toEqual(['=DNS: a.example'])
  })

  it('reads a critical flag as an element of its own: same values, one critical, the flag is the difference', () => {
    const loose = { ...base, id: 2, extensions: { ...base.extensions, basic_constraints: { ca: false, critical: false } } }
    const bc = row(compareRows([base, loose], t), 'basic_constraints')
    expect(bc.differs).toBe(true)
    expect(marks(bc, 0)).toEqual(['=CA: FALSE', '+(inspector.cert.critical)'])
    expect(marks(bc, 1)).toEqual(['=CA: FALSE'])
  })

  it('gives a single value no elements: its line differs or not as a whole', () => {
    const rows = compareRows([base, { ...base, id: 2, issuer: 'CN=Other' }], t)
    expect(row(rows, 'issuer').values).toEqual(['CN=Root', 'CN=Other'])
    expect(row(rows, 'issuer').items).toBeUndefined()
    expect(row(rows, 'san').items).toHaveLength(2)
  })
})
