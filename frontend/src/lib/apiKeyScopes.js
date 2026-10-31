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

/** Permissions of a preset; an unknown one means full access. */
export function apiKeyScopePermissions(scope) {
  return API_KEY_SCOPES[scope] || ['*']
}
