import { describe, it, expect } from 'vitest'
import { signatureShortName } from '../signatureName'

describe('signatureShortName', () => {
  it('keeps the hash of a PKCS#1 or ECDSA name', () => {
    expect(signatureShortName('SHA256-RSA')).toBe('SHA256')
    expect(signatureShortName('ECDSA-SHA384')).toBe('ECDSA')
  })
  it('names a PSS signature whole', () => {
    expect(signatureShortName('RSASSA-PSS SHA-256 (salt 32)')).toBe('RSASSA-PSS')
  })
  it('shows a dash when unknown', () => {
    expect(signatureShortName(undefined)).toBe('—')
  })
  it('names a post-quantum signature whole', () => {
    expect(signatureShortName('ML-DSA-65')).toBe('ML-DSA-65')
    expect(signatureShortName('SLH-DSA-SHA2-128s')).toBe('SLH-DSA-SHA2-128s')
  })
})
