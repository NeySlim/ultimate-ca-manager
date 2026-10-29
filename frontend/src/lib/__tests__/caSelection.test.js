/**
 * A CA kept without its private key cannot sign: pickers leave it out and count it,
 * and its key import is offered whether its key was expected or not (#426).
 */
import { describe, it, expect } from 'vitest'
import { holdsNoKey, needsKeyImport, signingCas, unlistedSigningCas } from '../caSelection'

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
})
