/**
 * Scope presets offered when creating an API key. "Certificates Only" issues
 * X.509 and SSH certificates and reads the CAs, but creates or edits no CA.
 */
export const API_KEY_SCOPES = {
  full: ['*'],
  read: ['read:*'],
  readwrite: ['read:*', 'write:*'],
  certificates: [
    'read:certificates', 'write:certificates', 'read:cas', 'read:crl',
    'read:ssh', 'write:ssh', 'read:ssh_cas',
  ],
}

/**
 * Permissions of a preset (an unknown one means full access), cut down to those
 * `holds(permission)` grants; wildcard entries are left to the server.
 */
export function apiKeyScopePermissions(scope, holds = () => true) {
  return (API_KEY_SCOPES[scope] || ['*']).filter(p => p.includes('*') || holds(p))
}

const SCOPE_LABELS = { full: 'account.scopeFull', read: 'account.scopeReadOnly', readwrite: 'account.scopeReadWrite', certificates: 'account.scopeCertificates' }

/** A key's scope in words when it is one of the presets, else the permissions it holds. */
export function apiKeyScopeLabel(t, permissions) {
  const list = Array.isArray(permissions) ? permissions : [permissions].filter(Boolean)
  const same = (a) => a.length === list.length && a.every((p) => list.includes(p))
  const preset = Object.keys(API_KEY_SCOPES).find((k) => same(API_KEY_SCOPES[k]))
  return preset ? t(SCOPE_LABELS[preset]) : list.join(', ')
}
