import { describe, expect, it } from 'vitest'
import { API_KEY_SCOPES, apiKeyScopePermissions } from '../apiKeyScopes'

describe('API key scope presets', () => {
  it('Certificates Only issues X.509 and SSH certificates, and manages no CA', () => {
    expect([...API_KEY_SCOPES.certificates].sort()).toEqual([
      'read:certificates', 'write:certificates', 'read:cas', 'read:crl',
      'read:ssh', 'write:ssh', 'read:ssh_cas',
    ].sort())
  })

  it('an unknown scope falls back to full access, as before', () => {
    expect(apiKeyScopePermissions('certificates')).toEqual(API_KEY_SCOPES.certificates)
    expect(apiKeyScopePermissions('nope')).toEqual(['*'])
  })

  it('Certificates Only keeps to what the account holds', () => {
    const held = ['read:certificates', 'write:certificates', 'read:cas', 'read:crl']
    expect(apiKeyScopePermissions('certificates', (p) => held.includes(p))).toEqual(held)
  })

  it('leaves the wildcard presets to the server', () => {
    expect(apiKeyScopePermissions('readwrite', () => false)).toEqual(['read:*', 'write:*'])
    expect(apiKeyScopePermissions('full', () => false)).toEqual(['*'])
  })
})
