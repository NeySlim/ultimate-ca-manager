/**
 * A CA kept without its private key cannot sign: pickers leave it out and count it,
 * and its key import is offered whether its key was expected or not (#426).
 */
import { describe, it, expect } from 'vitest'
import { holdsNoKey, needsKeyImport, scepPickerCas, signingCas, unlistedPickerCas, unlistedScepPickerCas, unlistedSigningCas } from '../caSelection'

const keylessRoot = { id: 1, is_root: true, type: 'root', certificate_only: true, has_private_key: false }
const keylessIntermediate = { id: 2, is_root: false, type: 'intermediate', certificate_only: true, has_private_key: false }
const signer = { id: 3, has_private_key: true, certificate_only: false }

describe('CAs held without their key', () => {
  it('counts a root imported without its key as keyless, without the warning of a missing intermediate key', () => {
    expect(holdsNoKey(keylessRoot)).toBe(true)
    expect(needsKeyImport(keylessRoot)).toBe(false)
    expect(holdsNoKey(keylessIntermediate)).toBe(true)
    expect(needsKeyImport(keylessIntermediate)).toBe(true)
  })

  it('does not count a CA with its key, an offline one or a pending one', () => {
    expect(holdsNoKey(signer)).toBe(false)
    expect(holdsNoKey({ ...keylessRoot, offline: true })).toBe(false)
    expect(holdsNoKey({ ...keylessRoot, pending: true })).toBe(false)
  })

  it('tells how many CAs a signing picker leaves out', () => {
    const cas = [keylessRoot, keylessIntermediate, signer]
    expect(signingCas(cas)).toEqual([signer])
    expect(unlistedSigningCas(cas)).toBe(2)
    expect(unlistedSigningCas([signer])).toBe(0)
    expect(unlistedSigningCas(undefined)).toBe(0)
  })

  it('counts every CA that cannot sign now, not only those without a key', () => {
    const cas = [signer, { id: 5, has_private_key: true, revoked: true }, { id: 6, has_private_key: true, pending: true },
      { id: 7, has_private_key: true, offline: true }, { id: 8, has_private_key: true, revoked_in_chain: true }]
    expect(unlistedSigningCas(cas)).toBe(4)
  })

  it('does not count a selected CA that a picker keeps showing, by id or refid', () => {
    const cas = [signer, { ...keylessRoot, refid: 'abc' }, keylessIntermediate]
    expect(unlistedPickerCas(cas)).toBe(2)
    expect(unlistedPickerCas(cas, '2')).toBe(1)
    expect(unlistedPickerCas(cas, 'abc', 2)).toBe(0)
  })
})

describe('SCEP pickers', () => {
  const cas = [
    { id: 1, refid: 'r1', has_private_key: true },
    { id: 2, refid: 'r2', uses_hsm: true },
  ]

  it('leave out an HSM-backed CA and count it', () => {
    expect(scepPickerCas(cas).map(c => c.id)).toEqual([1])
    expect(unlistedScepPickerCas(cas)).toBe(1)
  })

  it('keep a saved HSM-backed CA visible, by id or refid', () => {
    expect(scepPickerCas(cas, 2).map(c => c.id)).toEqual([1, 2])
    expect(scepPickerCas(cas, 'r2').map(c => c.id)).toEqual([1, 2])
    expect(unlistedScepPickerCas(cas, 2)).toBe(0)
  })
})
