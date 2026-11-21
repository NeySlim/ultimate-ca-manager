import { describe, expect, it } from 'vitest'
import {
  appliedPermissions, groupPermissions, ignoredPermissions, normalizePermission, normalizePermissions,
  describePermissions, permissionActions,
} from '../rbacPermissions'

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

  it('labels the users category', () => {
    const [group] = groupPermissions(['read:users'])
    expect(group.labelKey).toBe('rbac.categories.userManagement')
  })

  it('labels SSH CAs apart from SSH certificates, right after them', () => {
    const groups = groupPermissions(['read:ssh_cas', 'write:ssh', 'read:ssh'])
    expect(groups.map(g => [g.key, g.labelKey])).toEqual([
      ['ssh', 'rbac.categories.ssh'], ['ssh_cas', 'rbac.categories.sshCas'],
    ])
  })

  it('labels the overview as the bar names it, first', () => {
    expect(groupPermissions(['read:certificates', 'read:dashboard']).map(g => [g.key, g.labelKey])).toEqual([
      ['dashboard', 'shell.bar.dashboard'], ['certificates', 'rbac.categories.certificates'],
    ])
  })

  it('labels an unknown resource by its name rather than dropping it', () => {
    const [group] = groupPermissions(['read:widgets'])
    expect(group).toMatchObject({ key: 'widgets', labelKey: null, label: 'widgets' })
  })

  it('reads the legacy certs name as certificates', () => {
    expect(normalizePermission('write:certs')).toBe('write:certificates')
    expect(normalizePermission('read:cas')).toBe('read:cas')
  })

  it('never drops a stored permission, and tells applied from ignored', () => {
    const stored = ['read:certs', 'read:certificates', '*', 'admin:users', 'read:dashboard', 'read:cas']
    expect(normalizePermissions(stored)).toEqual(['read:certificates', '*', 'admin:users', 'read:dashboard', 'read:cas'])
    expect(appliedPermissions(stored, GRANTABLE)).toEqual(['read:certificates', 'read:cas'])
    expect(ignoredPermissions(stored, GRANTABLE)).toEqual(['*', 'admin:users', 'read:dashboard'])
  })
})

describe('permissions in words', () => {
  const t = (key, o) => (o ? `${key} ${JSON.stringify(o)}` : key)

  it('names each resource with its actions, read before write, never the raw scope', () => {
    expect(describePermissions(t, ['write:certificates', 'read:cas', 'read:certificates'])).toBe([
      'rbac.permissionOf {"resource":"rbac.categories.certificates","actions":"groups.actions.read, groups.actions.write"}',
      'rbac.permissionOf {"resource":"rbac.categories.certificateAuthorities","actions":"groups.actions.read"}',
    ].join(' · '))
  })

  it('says what a wildcard covers', () => {
    expect(describePermissions(t, ['*'])).toBe('rbac.permissionOf {"resource":"rbac.anyResource","actions":"rbac.anyAction"}')
    expect(describePermissions(t, ['read:*', 'write:*'])).toBe('rbac.permissionOf {"resource":"rbac.anyResource","actions":"groups.actions.read, groups.actions.write"}')
  })

  it('names the export and administration actions the server grants beyond read, write and delete', () => {
    expect(describePermissions(t, ['export:audit', 'admin:users'])).toBe([
      'rbac.permissionOf {"resource":"rbac.categories.auditLogs","actions":"groups.actions.export"}',
      'rbac.permissionOf {"resource":"rbac.categories.userManagement","actions":"groups.actions.admin"}',
    ].join(' · '))
  })

  it('keeps an unknown resource or action by its name', () => {
    expect(describePermissions(t, ['purge:widgets'])).toBe('rbac.permissionOf {"resource":"widgets","actions":"purge"}')
  })

  it('lists the actions of a grid: read, write, delete, then any other', () => {
    expect(permissionActions(['read:cas', 'approve:approvals', 'delete:csrs'])).toEqual(['read', 'write', 'delete', 'approve'])
  })
})
