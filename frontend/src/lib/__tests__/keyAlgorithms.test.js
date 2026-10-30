import { describe, it, expect } from 'vitest'
import {
  ACME_CLIENT_LABELS, GROUP_PQ, KEY_ALGORITHMS, caKeyParts, defaultDigestFor,
  exportExcludedFor, findAlgorithm, isExportFormatAllowed, groupedOptions, isBrainpool, isPostQuantum, keyAlgorithmLabel,
  listAlgorithms, signerKeyParams,
} from '../keyAlgorithms'

const t = (key) => key
const labels = (rows) => rows.map(r => r.label)

describe('key algorithm registry', () => {
  it('lists the nine generated keys, then the EdDSA and ML-DSA keys it only reads', () => {
    expect(labels(listAlgorithms({ generate: true }))).toEqual([
      'RSA-2048', 'RSA-3072', 'RSA-4096', 'EC-P256', 'EC-P384', 'EC-P521',
      'EC-BP256', 'EC-BP384', 'EC-BP512',
    ])
    expect(labels(KEY_ALGORITHMS).slice(-5)).toEqual(['ED25519', 'ED448', 'ML-DSA-44', 'ML-DSA-65', 'ML-DSA-87'])
  })

  it('names ML-DSA by security category, without a digest, outside FIPS', () => {
    expect(KEY_ALGORITHMS.filter(a => a.group === GROUP_PQ).map(a => [a.label, a.securityLevel]))
      .toEqual([['ML-DSA-44', 2], ['ML-DSA-65', 3], ['ML-DSA-87', 5]])
    expect(findAlgorithm('ML-DSA-65')).toMatchObject({
      family: 'ML-DSA', bits: null, digest: null, fips: false, generate: false, issue: null, ca: null, csr: null,
    })
    expect(listAlgorithms({ fips: true }).some(a => a.group === GROUP_PQ)).toBe(false)
    expect(groupedOptions(listAlgorithms({ labels: ['EC-P256', 'ML-DSA-65'] }), t).map(o => o.group))
      .toEqual(['common.keyGroups.nist', 'common.keyGroups.pq'])
  })

  it('hides what FIPS mode does not approve', () => {
    expect(labels(listAlgorithms({ generate: true, fips: true }))).toEqual([
      'RSA-2048', 'RSA-3072', 'RSA-4096', 'EC-P256', 'EC-P384', 'EC-P521',
    ])
  })

  it('holds Brainpool on a PKCS#11 provider only', () => {
    const bp = (provider) => labels(listAlgorithms({ generate: true, provider })).filter(isBrainpool)
    expect(bp('pkcs11')).toEqual(['EC-BP256', 'EC-BP384', 'EC-BP512'])
    for (const other of ['azure', 'google', 'openbao', '']) expect(bp(other)).toEqual([])
  })

  it('restricts and orders by the labels a surface passes', () => {
    expect(labels(listAlgorithms({ labels: ACME_CLIENT_LABELS }))).toEqual(
      ['RSA-2048', 'RSA-4096', 'EC-P256', 'EC-P384', 'EC-BP256', 'EC-BP384'])
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

  it('maps a TSA signer key to the API parameters', () => {
    expect(signerKeyParams('RSA-3072')).toEqual({ key_type: 'RSA', key_size: '3072', curve: undefined })
    expect(signerKeyParams('EC-P384')).toEqual({ key_type: 'EC', key_size: undefined, curve: 'P-384' })
    expect(signerKeyParams('EC-BP256')).toEqual({ key_type: 'EC', key_size: undefined, curve: 'brainpoolP256r1' })
  })

  it('does not hand an ML-DSA key to the TSA as an EC curve', () => {
    for (const a of KEY_ALGORITHMS.filter(r => r.group === GROUP_PQ)) {
      expect(signerKeyParams(a.label).key_type).not.toBe('EC')
    }
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
})
