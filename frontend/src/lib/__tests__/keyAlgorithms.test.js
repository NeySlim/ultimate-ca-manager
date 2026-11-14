import { describe, it, expect } from 'vitest'
import {
  ACME_CLIENT_LABELS, CA_DEFAULT_LABELS, GROUP_PQ, ISSUE_DEFAULT_LABELS, KEY_ALGORITHMS,
  algorithmForKeyType, algorithmName, caKeyParts, defaultDigestFor, defaultKeyChoice, keyFamilyOptions,
  exportExcludedFor, findAlgorithm, isExportFormatAllowed, groupedOptions, isBrainpool, isPostQuantum, keyAlgorithmLabel,
  isUsable, listAlgorithms,
} from '../keyAlgorithms'
import { CA_KEY_CHOICES, caKeyLabel } from '../policyAlgorithms'

const t = (key) => key
const labels = (rows) => rows.map(r => r.label)

describe('key algorithm registry', () => {
  it('lists the twelve generated keys, then the EdDSA keys it only reads', () => {
    expect(labels(listAlgorithms({ generate: true }))).toEqual([
      'RSA-2048', 'RSA-3072', 'RSA-4096', 'EC-P256', 'EC-P384', 'EC-P521',
      'EC-BP256', 'EC-BP384', 'EC-BP512', 'ML-DSA-44', 'ML-DSA-65', 'ML-DSA-87',
    ])
    expect(labels(KEY_ALGORITHMS).slice(-5)).toEqual(['ED25519', 'ED448', 'ML-DSA-44', 'ML-DSA-65', 'ML-DSA-87'])
  })

  it('names ML-DSA by security category, without a digest, outside FIPS, generated in software and on HSMs', () => {
    expect(KEY_ALGORITHMS.filter(a => a.group === GROUP_PQ).map(a => [a.label, a.securityLevel]))
      .toEqual([['ML-DSA-44', 2], ['ML-DSA-65', 3], ['ML-DSA-87', 5]])
    expect(findAlgorithm('ML-DSA-65')).toMatchObject({
      family: 'ML-DSA', bits: null, digest: null, fips: null, generate: true,
      issue: ['ml-dsa', '65'], ca: ['ML-DSA', '65'], csr: 'ML-DSA-65',
    })
    // Held by the HSM types whose provider signs ML-DSA, none on Azure Key Vault
    for (const provider of ['pkcs11', 'openbao', 'google-kms']) {
      expect(listAlgorithms({ generate: true, provider }).filter(a => a.group === GROUP_PQ).map(a => a.label))
        .toEqual(['ML-DSA-44', 'ML-DSA-65', 'ML-DSA-87'])
    }
    for (const provider of ['azure-keyvault', 'aws-cloudhsm', '']) {
      expect(listAlgorithms({ generate: true, provider }).some(a => a.group === GROUP_PQ)).toBe(false)
    }
    expect(listAlgorithms({ fips: true }).some(a => a.group === GROUP_PQ)).toBe(false)
    expect(groupedOptions(listAlgorithms({ labels: ['EC-P256', 'ML-DSA-65'] }), t).map(o => o.group))
      .toEqual(['common.keyGroups.nist', 'common.keyGroups.pq'])
  })

  it('hides what FIPS mode does not approve', () => {
    expect(labels(listAlgorithms({ generate: true, fips: true }))).toEqual([
      'RSA-2048', 'RSA-3072', 'RSA-4096', 'EC-P256', 'EC-P384', 'EC-P521',
    ])
  })

  it('offers in FIPS mode what the server says its module approves, and only that', () => {
    const approving = ['RSA-2048', 'EC-P256', 'ED25519', 'ED448', 'ML-DSA-44', 'ML-DSA-65', 'ML-DSA-87']
    expect(labels(listAlgorithms({ generate: true, fips: true, fipsKeys: approving }))).toEqual([
      'RSA-2048', 'EC-P256', 'ML-DSA-44', 'ML-DSA-65', 'ML-DSA-87',
    ])
    expect(isUsable(findAlgorithm('ED25519'), { fips: true, fipsKeys: approving })).toBe(true)
    expect(isUsable(findAlgorithm('ED448'), { fips: true, fipsKeys: ['RSA-2048'] })).toBe(false)
    expect(isUsable(findAlgorithm('EC-BP256'), { fips: true, fipsKeys: approving })).toBe(false)
    // Outside FIPS mode the list changes nothing
    expect(isUsable(findAlgorithm('EC-BP256'), { fips: false, fipsKeys: ['RSA-2048'] })).toBe(true)
    // No list from the server: no module-decided row is offered
    for (const row of KEY_ALGORITHMS.filter(a => a.fips === null)) {
      expect(isUsable(row, { fips: true })).toBe(false)
    }
  })

  it('hides ML-DSA, and only ML-DSA, on a build without it', () => {
    expect(labels(listAlgorithms({ generate: true, mldsa: false }))).toEqual(
      labels(listAlgorithms({ generate: true })).filter(l => !l.startsWith('ML-DSA-')))
    expect(labels(listAlgorithms({ generate: true })).filter(l => l.startsWith('ML-DSA-'))).toHaveLength(3)
  })

  it('holds Brainpool on a PKCS#11 provider only', () => {
    const bp = (provider) => labels(listAlgorithms({ generate: true, provider })).filter(isBrainpool)
    expect(bp('pkcs11')).toEqual(['EC-BP256', 'EC-BP384', 'EC-BP512'])
    for (const other of ['azure', 'google', 'openbao', '']) expect(bp(other)).toEqual([])
  })

  it('restricts and orders by the labels a surface passes', () => {
    expect(labels(listAlgorithms({ labels: ACME_CLIENT_LABELS }))).toEqual(
      ['RSA-2048', 'RSA-4096', 'EC-P256', 'EC-P384', 'EC-BP256', 'EC-BP384', 'ML-DSA-44', 'ML-DSA-65', 'ML-DSA-87'])
    expect(labels(listAlgorithms({ labels: ['EC-P384', 'RSA-2048'] }))).toEqual(['EC-P384', 'RSA-2048'])
  })

  it('picks the digest of matching strength for a CA key', () => {
    expect(defaultDigestFor('ECDSA', 'secp384r1')).toBe('sha384')
    expect(defaultDigestFor('ECDSA', 'brainpoolP384r1')).toBe('sha384')
    expect(defaultDigestFor('ECDSA', 'brainpoolP512r1')).toBe('sha512')
    expect(defaultDigestFor('RSA', '4096')).toBe('sha256')
  })

  it('names each Brainpool curve with the backend spelling', () => {
    expect(findAlgorithm('EC-BP384')).toMatchObject({
      ca: ['ECDSA', 'brainpoolP384r1'], issue: ['ecdsa', 'brainpoolP384r1'], csr: 'EC-BP384',
      curveParam: 'brainpoolP384r1', fips: false,
    })
  })

  it('adds a heading per group only when the list spans several', () => {
    const mixed = groupedOptions(listAlgorithms({ labels: ['EC-P256', 'EC-BP256'] }), t)
    expect(mixed.map(o => o.group)).toEqual(['common.keyGroups.nist', 'common.keyGroups.brainpool'])
    const single = groupedOptions(listAlgorithms({ labels: ['EC-P256', 'EC-P384'] }), t)
    expect(single.every(o => !('group' in o))).toBe(true)
  })
})

const PQ_ROWS = KEY_ALGORITHMS.filter(a => a.group === GROUP_PQ)
const CLASSIC_ROWS = KEY_ALGORITHMS.filter(a => a.group !== GROUP_PQ)
// What the API reports for keys outside the registry (certificate key_algorithm, CA key_type)
const API_CLASSIC_NAMES = ['RSA', 'EC', 'ECDSA', 'Ed25519', 'RSA 2048', 'EC secp384r1']

describe('post-quantum keys', () => {
  it('flags every ML-DSA row and SLH-DSA, nothing else', () => {
    expect(PQ_ROWS.length).toBeGreaterThan(0)
    for (const a of PQ_ROWS) expect(isPostQuantum(a.label)).toBe(true)
    expect(isPostQuantum('SLH-DSA-SHA2-128s')).toBe(true)
    for (const a of CLASSIC_ROWS) expect(isPostQuantum(a.label)).toBe(false)
    for (const name of [...API_CLASSIC_NAMES, '', null, undefined]) expect(isPostQuantum(name)).toBe(false)
  })

  it('leaves PKCS#12 and JKS out of the export formats of a post-quantum key', () => {
    for (const name of [...PQ_ROWS.map(a => a.label), 'SLH-DSA-SHA2-128s']) {
      expect(exportExcludedFor(name)).toEqual(['pkcs12', 'jks'])
      for (const f of ['pkcs12', 'jks']) expect(isExportFormatAllowed(name, f)).toBe(false)
      for (const f of ['pem', 'der', 'pkcs7', 'key']) expect(isExportFormatAllowed(name, f)).toBe(true)
    }
  })

  it('keeps every export format for a classical or unknown key', () => {
    for (const name of [...CLASSIC_ROWS.map(a => a.label), ...API_CLASSIC_NAMES, null, undefined]) {
      expect(exportExcludedFor(name)).toEqual([])
      // A format the registry has never heard of stays open too
      expect(isExportFormatAllowed(name, 'some-future-format')).toBe(true)
    }
  })

  it('names an ML-DSA key with its security level, a classical one as is', () => {
    const t = (key, vars) => `${key}:${JSON.stringify(vars)}`
    for (const a of PQ_ROWS) {
      expect(keyAlgorithmLabel(a.label, t))
        .toBe(`common.keyAlgorithmLevel:${JSON.stringify({ name: a.label, level: a.securityLevel })}`)
    }
    expect(keyAlgorithmLabel('ML-DSA-65', t, 3)).toContain('"level":3')
    expect(keyAlgorithmLabel('SLH-DSA-SHA2-128s', t)).toBe('SLH-DSA-SHA2-128s')
    expect(keyAlgorithmLabel('SLH-DSA-SHA2-128s', t, 1)).toContain('"level":1')
    expect(keyAlgorithmLabel('RSA', t)).toBe('RSA')
    expect(keyAlgorithmLabel(null, t)).toBeNull()
  })

  it('splits a CA key type into family and size, a post-quantum label whole', () => {
    expect(caKeyParts('RSA 2048')).toEqual({ family: 'RSA', spec: '2048' })
    expect(caKeyParts('EC secp384r1')).toEqual({ family: 'EC', spec: 'secp384r1' })
    for (const a of PQ_ROWS) expect(caKeyParts(a.label)).toEqual({ family: a.label, spec: null })
    expect(caKeyParts('')).toEqual({ family: null, spec: null })
  })

  it('offers RSA, ECDSA, EdDSA and ML-DSA to the CA form, EdDSA not to the issue form', () => {
    expect(keyFamilyOptions('ca')).toEqual([
      { value: 'RSA', label: 'RSA' }, { value: 'ECDSA', label: 'ECDSA' }, { value: 'EdDSA', label: 'EdDSA' },
      { value: 'ML-DSA', label: 'ML-DSA' },
    ])
    expect(keyFamilyOptions('issue')).toEqual([
      { value: 'rsa', label: 'RSA' }, { value: 'ecdsa', label: 'ECDSA' }, { value: 'ml-dsa', label: 'ML-DSA' },
    ])
  })

  it('declares Ed25519 and Ed448 as CA keys only: no leaf, template or HSM generation', () => {
    expect(caKeyLabel('EdDSA', 'Ed25519')).toBe('ED25519')
    expect(caKeyLabel('EdDSA', 'Ed448')).toBe('ED448')
    expect(CA_KEY_CHOICES).toEqual(expect.arrayContaining([['EdDSA', 'Ed25519'], ['EdDSA', 'Ed448']]))
    expect(defaultKeyChoice('ca', 'EdDSA', CA_DEFAULT_LABELS)).toEqual(['EdDSA', 'Ed25519'])
    expect(defaultDigestFor('EdDSA', 'Ed25519')).toBe('sha256')
    expect(findAlgorithm('ED25519').digest).toBeNull()
    for (const provider of [undefined, 'pkcs11', 'openbao']) {
      expect(labels(listAlgorithms({ generate: true, provider })).filter(l => l.startsWith('ED'))).toEqual([])
    }
    expect(isUsable(findAlgorithm('ED25519'), { fips: true })).toBe(false)
  })

  it('starts each family on its default key, ML-DSA on level 65', () => {
    expect(defaultKeyChoice('ca', 'ML-DSA', CA_DEFAULT_LABELS)).toEqual(['ML-DSA', '65'])
    expect(defaultKeyChoice('issue', 'ml-dsa', ISSUE_DEFAULT_LABELS)).toEqual(['ml-dsa', '65'])
    expect(defaultKeyChoice('ca', 'RSA', CA_DEFAULT_LABELS)).toEqual(['RSA', '3072'])
    expect(defaultKeyChoice('issue', 'nope', ISSUE_DEFAULT_LABELS)).toBeNull()
  })

  it('finds the row of a stored key spelling, ML-DSA included', () => {
    for (const a of PQ_ROWS) expect(algorithmForKeyType(a.label)).toBe(a)
    expect(algorithmForKeyType('RSA 3072')?.label).toBe('RSA-3072')
    expect(algorithmForKeyType('Ed25519')?.digest).toBeNull()
    expect(algorithmForKeyType('Ed448')?.label).toBe('ED448')
    expect(algorithmForKeyType('EC secp256r1')?.label).toBe('EC-P256')
    expect(algorithmForKeyType('EC secp384r1')?.label).toBe('EC-P384')
    expect(algorithmForKeyType('EC brainpoolP256r1')?.label).toBe('EC-BP256')
    expect(algorithmForKeyType('ED25519')?.label).toBe('ED25519')
    expect(algorithmForKeyType('DSA 1024')).toBeNull()
    expect(algorithmForKeyType(null)).toBeNull()
  })

  it('names a post-quantum row with its level in a form', () => {
    const tl = (key, opts) => (opts ? `${key}:${opts.name}:${opts.level}` : key)
    expect(algorithmName(findAlgorithm('ML-DSA-87'), tl, 'sizeKey')).toBe('common.keyAlgorithmLevel:ML-DSA-87:5')
    expect(algorithmName(findAlgorithm('RSA-2048'), tl, 'sizeKey')).toBe('certificates.keySizeRsa2048')
    expect(algorithmName(findAlgorithm('EC-BP256'), tl, 'sizeKey')).toBe('Brainpool P256r1')
  })
})
