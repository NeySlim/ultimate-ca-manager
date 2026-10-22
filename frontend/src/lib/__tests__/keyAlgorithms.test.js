import { describe, it, expect } from 'vitest'
import {
  ACME_CLIENT_LABELS, KEY_ALGORITHMS, defaultDigestFor, findAlgorithm, groupedOptions,
  isBrainpool, listAlgorithms, signerKeyParams,
} from '../keyAlgorithms'

const t = (key) => key
const labels = (rows) => rows.map(r => r.label)

describe('key algorithm registry', () => {
  it('lists the nine generated keys and the two EdDSA keys it only reads', () => {
    expect(labels(listAlgorithms({ generate: true }))).toEqual([
      'RSA-2048', 'RSA-3072', 'RSA-4096', 'EC-P256', 'EC-P384', 'EC-P521',
      'EC-BP256', 'EC-BP384', 'EC-BP512',
    ])
    expect(labels(KEY_ALGORITHMS).slice(-2)).toEqual(['ED25519', 'ED448'])
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
})
