/** Shared fixtures for the shell tests: roles as permission lists and the `can` they give. */
export const ROLES = {
  admin: ['*'],
  operator: ['read:acme', 'read:scep', 'read:est', 'read:crl', 'read:truststore', 'read:ssh', 'read:ssh_cas',
    'read:certificates', 'read:approvals', 'write:certificates'],
  auditor: ['read:audit', 'read:policies', 'read:approvals', 'read:certificates'],
  viewer: [],
}

export function canFor(permissions) {
  const has = (p) => permissions.includes('*') || permissions.includes(p)
  return { isAdmin: () => permissions.includes('*'), hasPermission: has }
}

/** `t` that keeps the key and the interpolated name, so labels stay distinguishable. */
export const tStub = (key, opts) => (opts && opts.name ? `${key}|${opts.name}` : key)
