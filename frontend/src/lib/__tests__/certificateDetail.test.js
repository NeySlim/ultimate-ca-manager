/** What the certificate inspector derives from the API detail. */
import { describe, it, expect } from 'vitest'
import { validityFacts, chainNodes, extensionRows, historyEntries, lastAcmeFailure, certificateKeyLabel, keyLabel, serialHex, certTypeLabel, originLabel, complianceReasonLabel } from '../certificateDetail'
import { signatureHashName } from '../signatureName'

const NOW = new Date('2026-11-20T12:00:00Z')
const DAY = 86400000
const at = (d) => new Date(NOW.getTime() + d * DAY).toISOString()
const t = (k) => k

describe('certificateKeyLabel', () => {
  it('names a key as people do', () => {
    expect(certificateKeyLabel({ key_type: 'RSA 2048', key_algorithm: 'RSA' }, t)).toBe('RSA 2048')
    expect(certificateKeyLabel({ key_type: 'EC secp256r1', key_algorithm: 'EC' }, t)).toBe('ECDSA P-256')
    expect(certificateKeyLabel({ key_type: 'EC secp384r1' }, t)).toBe('ECDSA P-384')
    expect(certificateKeyLabel({ key_type: 'EC brainpoolP256r1' }, t)).toBe('ECDSA brainpoolP256r1')
  })

  it('reads every spelling of a key the same: a decoded CSR, a registry label', () => {
    expect(certificateKeyLabel({ key_type: 'ECDSA secp256r1' }, t)).toBe('ECDSA P-256')
    expect(keyLabel('EC-P256', t)).toBe('ECDSA P-256')
    expect(keyLabel('EC-P384', t)).toBe('ECDSA P-384')
    expect(keyLabel('RSA-2048', t)).toBe('RSA 2048')
    expect(keyLabel('RSA 4096', t)).toBe('RSA 4096')
  })
})

describe('validityFacts', () => {
  it('gives the days left and the share of the validity left', () => {
    const f = validityFacts({ valid_from: at(-75), valid_to: at(25), status: 'valid' }, NOW)
    expect(f.days).toBe(25)
    expect(f.ratio).toBeCloseTo(25, 5)
    expect(f.short).toBe(true)
    expect(f.state).toBe('valid')
  })

  it('says revoked over the status, and an empty bar after the end', () => {
    expect(validityFacts({ valid_from: at(-10), valid_to: at(10), revoked: true, status: 'valid' }, NOW).state).toBe('revoked')
    const past = validityFacts({ valid_from: at(-100), valid_to: at(-4), status: 'expired' }, NOW)
    expect(past.ratio).toBe(0)
    expect(past.days).toBeLessThan(0)
    expect(past.short).toBe(false)
  })
})

describe('chainNodes', () => {
  it('lists the chain from its top down, the anchor of a complete chain as root', () => {
    const nodes = chainNodes({ chain_status: { status: 'complete', chain: [{ name: 'Issuing', type: 'managed_ca' }, { name: 'Root', type: 'managed_ca' }] } })
    expect(nodes.map((n) => [n.name, n.role, n.issuing])).toEqual([['Root', 'root', false], ['Issuing', 'intermediate', true]])
  })

  it('calls a trust-store top an anchor, and nothing root in an incomplete chain', () => {
    expect(chainNodes({ chain_status: { status: 'complete', chain: [{ name: 'X', type: 'trust_store' }] } })[0].role).toBe('anchor')
    expect(chainNodes({ chain_status: { status: 'incomplete', chain: [{ name: 'X', type: 'managed_ca' }] } })[0].role).toBe('intermediate')
    expect(chainNodes({})).toEqual([])
  })
})

describe('extensionRows', () => {
  it('gives each extension its OID, criticality and values', () => {
    const rows = extensionRows({
      subject_alt_names: { critical: false, entries: [{ type: 'DNS', value: 'a.example' }] },
      basic_constraints: { ca: false, critical: true, path_length: null },
      extended_key_usage: { usages: [{ name: 'serverAuth', oid: '1.3.6.1.5.5.7.3.1' }] },
      other_extensions: [{ oid: '1.2.3.4', value_hex: '0a0b', critical: false }],
    })
    expect(rows.map((r) => [r.oid, r.critical, r.values])).toEqual([
      ['2.5.29.17', false, ['DNS: a.example']],
      ['2.5.29.19', true, ['CA: FALSE']],
      ['2.5.29.37', false, ['TLS Web Server Authentication']],
      ['1.2.3.4', false, ['0a0b']],
    ])
  })

  it('writes the X.509 names and readable values, the same in every language', () => {
    const rows = extensionRows({
      key_usage: { critical: true, usages: ['digitalSignature', 'keyEncipherment', 'unknownBit'] },
      extended_key_usage: { usages: [{ name: 'serverAuth' }, { name: 'clientAuth' }, { oid: '1.2.3' }] },
    })
    expect(rows.map((r) => [r.label, r.values])).toEqual([
      ['Key Usage', ['Digital Signature, Key Encipherment, unknownBit']],
      ['Extended Key Usage', ['TLS Web Server Authentication', 'TLS Web Client Authentication', '1.2.3']],
    ])
    expect(rows.every((r) => !('labelKey' in r))).toBe(true)
  })

  it('falls back to the combined SAN text', () => {
    expect(extensionRows({}, 'DNS:a, DNS:b')[0].values).toEqual(['DNS:a', 'DNS:b'])
  })
})

describe('historyEntries', () => {
  const cert = { id: 7, created_at: at(-30), source: 'acme', revoked: true, revoked_at: at(-1), revoke_reason: 'keyCompromise' }

  it('lists the record dates and the audit entries of this certificate, newest first', () => {
    const logs = [
      { id: 1, resource_id: 7, resource_type: 'certificate', action: 'certificate_exported', timestamp: at(-5), username: 'ops' },
      { id: 2, resource_id: 8, resource_type: 'certificate', action: 'certificate_exported', timestamp: at(-4) },
    ]
    const out = historyEntries(cert, logs)
    expect(out.map((e) => e.kind)).toEqual(['revoked', 'audit', 'issued'])
    expect(out[1].actor).toBe('ops')
  })

  it('shows once a record date the audit log also holds', () => {
    const logs = [{ id: 3, resource_id: 7, action: 'certificate_revoked', timestamp: new Date(Date.parse(at(-1)) + 30000).toISOString() }]
    expect(historyEntries(cert, logs).filter((e) => e.kind === 'revoked' || /revok/.test(e.action || ''))).toHaveLength(1)
  })

  it('calls an uploaded certificate imported', () => {
    expect(historyEntries({ id: 1, created_at: at(-1), source: 'upload' })[0].kind).toBe('imported')
  })
})

describe('lastAcmeFailure', () => {
  it('returns the latest failed order of this certificate', () => {
    const orders = [
      { id: 1, certificate_id: 7, status: 'invalid', error_message: 'old', last_error_at: at(-9) },
      { id: 2, certificate_id: 7, status: 'invalid', error_message: 'dns', last_error_at: at(-2) },
      { id: 3, certificate_id: 8, status: 'invalid', error_message: 'other', last_error_at: at(-1) },
      { id: 4, certificate_id: 7, status: 'valid', error_message: '' },
    ]
    expect(lastAcmeFailure({ id: 7 }, orders).id).toBe(2)
  })

  it('forgets a failure settled by a later renewal, and returns null without one', () => {
    const orders = [{ id: 2, certificate_id: 7, status: 'invalid', error_message: 'dns', last_error_at: at(-5) }]
    expect(lastAcmeFailure({ id: 7, renewed_at: at(-1) }, orders)).toBeNull()
    expect(lastAcmeFailure({ id: 7 }, [])).toBeNull()
  })
})

describe('serialHex', () => {
  it('writes a serial as colon-separated octets, a decimal one converted', () => {
    expect(serialHex('19')).toBe('13')
    expect(serialHex('256')).toBe('01:00')
    expect(serialHex('4a8b01')).toBe('4A:8B:01')
    expect(serialHex('4A:8B:1')).toBe('04:A8:B1')
    expect(serialHex('')).toBe('')
    expect(serialHex(null)).toBe('')
  })
})

describe('signatureHashName', () => {
  it('names the hash as the Atelier detail does', () => {
    expect(signatureHashName('SHA256-RSA')).toBe('SHA-256')
    expect(signatureHashName('SHA384-ECDSA')).toBe('SHA-384')
    expect(signatureHashName('RSASSA-PSS-SHA256')).toBe('RSASSA-PSS')
    expect(signatureHashName('ML-DSA-65')).toBe('ML-DSA-65')
  })
})

describe('values of « Plus de détails » in words', () => {
  const t = (key, fallback) => ({
    'certificates.sourceTypes.server': 'Serveur',
    'certificates.sourceImport': 'Import',
    'compliance.reasons.critical': 'critique',
    'compliance.reasons.unknown': 'Inconnu',
  }[key] ?? (typeof fallback === 'string' ? fallback : key))
  const sources = { keys: { import: 'sourceImport' }, label: (v) => t(`certificates.${sources.keys[v]}`) }

  it('names a stored type, and humanizes one it does not know', () => {
    expect(certTypeLabel('server_cert', t)).toBe('Serveur')
    expect(certTypeLabel('odd_type', t)).toBe('Odd type')
    expect(certTypeLabel(null, t)).toBeNull()
  })

  it('names a source and a product, and keeps a user name as sent', () => {
    expect(originLabel('import', sources, t)).toBe('Import')
    expect(originLabel('opnsense', sources, t)).toBe('OPNsense')
    expect(originLabel('jane_doe', sources, t)).toBe('jane_doe')
  })

  it('translates the flag of a compliance reason and a known code', () => {
    expect(complianceReasonLabel('RSA 512 (critical)', t)).toBe('RSA 512 (critique)')
    expect(complianceReasonLabel('Unknown', t)).toBe('Inconnu')
    expect(complianceReasonLabel('ECDSA P-256', t)).toBe('ECDSA P-256')
  })
})
