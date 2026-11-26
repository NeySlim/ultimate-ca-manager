/**
 * Scope presets offered when creating an API key. "Certificates Only" issues
 * X.509 and SSH certificates and reads the CAs, but creates or edits no CA.
 */
import { describePermissions } from './rbacPermissions'

export const API_KEY_SCOPES = {
  full: ['*'],
  read: ['read:*'],
  readwrite: ['read:*', 'write:*'],
  certificates: [
    'read:certificates', 'write:certificates', 'read:cas', 'read:crl',
    'read:ssh', 'write:ssh', 'read:ssh_cas',
  ],
  // A fleet console: reads the instance state and settings, starts a backup or an update
  instance: ['read:instance', 'read:settings', 'write:backups', 'write:updates'],
}

/**
 * Permissions of a preset (an unknown one means full access), cut down to those
 * `holds(permission)` grants; wildcard entries are left to the server.
 */
export function apiKeyScopePermissions(scope, holds = () => true) {
  return (API_KEY_SCOPES[scope] || ['*']).filter(p => p.includes('*') || holds(p))
}

const SCOPE_LABELS = { full: 'account.scopeFull', read: 'account.scopeReadOnly', readwrite: 'account.scopeReadWrite', certificates: 'account.scopeCertificates', instance: 'account.scopeInstance' }

/** A key's scope in words: its preset's name, else the permissions it holds by resource and action. */
export function apiKeyScopeLabel(t, permissions) {
  const list = Array.isArray(permissions) ? permissions : [permissions].filter(Boolean)
  const same = (a) => a.length === list.length && a.every((p) => list.includes(p))
  const preset = Object.keys(API_KEY_SCOPES).find((k) => same(API_KEY_SCOPES[k]))
  return preset ? t(SCOPE_LABELS[preset]) : describePermissions(t, list)
}
