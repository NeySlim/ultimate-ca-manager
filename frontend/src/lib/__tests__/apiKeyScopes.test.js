import { describe, expect, it } from 'vitest'
import { API_KEY_SCOPES, apiKeyScopePermissions, apiKeyScopeLabel } from '../apiKeyScopes'

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

  it('Instance management holds what a fleet console needs, and no admin:system', () => {
    expect([...API_KEY_SCOPES.instance].sort()).toEqual(
      ['read:instance', 'read:settings', 'write:backups', 'write:updates'])
  })

  it('leaves the wildcard presets to the server', () => {
    expect(apiKeyScopePermissions('readwrite', () => false)).toEqual(['read:*', 'write:*'])
    expect(apiKeyScopePermissions('full', () => false)).toEqual(['*'])
  })
})

describe('a key\'s scope in words', () => {
  const t = (key, o) => (o ? `${key} ${JSON.stringify(o)}` : key)

  it('names a preset, else the permissions by resource and action, never a raw scope', () => {
    expect(apiKeyScopeLabel(t, ['read:*'])).toBe('account.scopeReadOnly')
    expect(apiKeyScopeLabel(t, ['write:updates', 'read:instance', 'write:backups', 'read:settings'])).toBe('account.scopeInstance')
    expect(apiKeyScopeLabel(t, ['write:backups'])).toBe(
      'rbac.permissionOf {"resource":"rbac.categories.backups","actions":"groups.actions.write"}')
    expect(apiKeyScopeLabel(t, ['read:cas', 'delete:cas'])).toBe(
      'rbac.permissionOf {"resource":"rbac.categories.certificateAuthorities","actions":"groups.actions.read, groups.actions.delete"}')
  })
})
