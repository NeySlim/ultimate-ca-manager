import { describe, expect, it } from 'vitest'
import { editablePermissions, groupPermissions, normalizePermission } from '../rbacPermissions'

// Shape of GET /api/v2/rbac/permissions
const GRANTABLE = ['read:cas', 'write:cas', 'read:certificates', 'write:certificates',
  'read:private_keys', 'delete:csrs', 'read:csrs', 'read:est']

describe('custom role matrix follows the server list', () => {
  it('groups by resource, known resources first, read before write', () => {
    const groups = groupPermissions(GRANTABLE)
    expect(groups.map(g => g.key)).toEqual(['certificates', 'private_keys', 'cas', 'csrs', 'est'])
    expect(groups.find(g => g.key === 'csrs').permissions).toEqual(['read:csrs', 'delete:csrs'])
    expect(groups.find(g => g.key === 'cas').labelKey).toBe('rbac.categories.certificateAuthorities')
  })

  it('labels an unknown resource by its name rather than dropping it', () => {
    const [group] = groupPermissions(['read:widgets'])
    expect(group).toMatchObject({ key: 'widgets', labelKey: null, label: 'widgets' })
  })

  it('reads the legacy certs name as certificates', () => {
    expect(normalizePermission('write:certs')).toBe('write:certificates')
    expect(normalizePermission('read:cas')).toBe('read:cas')
  })

  it('saves only what the server grants, legacy names normalised', () => {
    const stored = ['read:certs', 'read:certificates', '*', 'admin:users', 'read:dashboard', 'read:cas']
    expect(editablePermissions(stored, GRANTABLE)).toEqual(['read:certificates', 'read:cas'])
  })
})
