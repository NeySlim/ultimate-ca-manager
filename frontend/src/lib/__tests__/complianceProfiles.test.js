import { describe, it, expect } from 'vitest'
import { limitsWithProfile } from '../complianceProfiles'

const BSI = {
  allowed_key_types: ['RSA-3072', 'RSA-4096', 'EC-P256'],
  allowed_digests: ['sha256', 'sha384'],
  allowed_signature_schemes: ['rsa_pss', 'ecdsa'],
  key_type_horizons: { 'RSA-3072': '2035-12-31' },
  require_hsm_ca_key: true,
}

describe('limitsWithProfile', () => {
  it('leaves the policy limits alone without a profile', () => {
    expect(limitsWithProfile({ allowedKeyTypes: ['RSA-2048'], allowedDigests: null }, undefined)).toEqual({
      allowedKeyTypes: ['RSA-2048'], allowedDigests: null, allowedSchemes: null, horizons: {}, requireHsm: false,
    })
  })

  it('takes the profile lists when the policies restrict nothing', () => {
    const limits = limitsWithProfile({ allowedKeyTypes: null, allowedDigests: null }, BSI)
    expect(limits.allowedKeyTypes).toEqual(BSI.allowed_key_types)
    expect(limits.allowedDigests).toEqual(BSI.allowed_digests)
    expect(limits.allowedSchemes).toEqual(['rsa_pss', 'ecdsa'])
    expect(limits.horizons).toEqual({ 'RSA-3072': '2035-12-31' })
    expect(limits.requireHsm).toBe(true)
  })

  it('intersects with the policies already in scope', () => {
    const limits = limitsWithProfile(
      { allowedKeyTypes: ['RSA-2048', 'RSA-3072', 'EC-P384'], allowedDigests: ['sha384', 'sha512'] }, BSI)
    expect(limits.allowedKeyTypes).toEqual(['RSA-3072'])
    expect(limits.allowedDigests).toEqual(['sha384'])
  })

  it('an empty intersection allows nothing instead of everything', () => {
    expect(limitsWithProfile({ allowedKeyTypes: ['EC-P521'], allowedDigests: null }, BSI).allowedKeyTypes).toEqual([])
  })
})
