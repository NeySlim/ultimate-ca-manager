/**
 * Custom role permission matrix, built from GET /api/v2/rbac/permissions:
 * the server says what a custom role may grant, this file only labels it.
 */

// Resource -> i18n key of its label, in display order
const CATEGORY_LABELS = [
  ['certificates', 'rbac.categories.certificates'],
  ['private_keys', 'common.privateKey'],
  ['cas', 'rbac.categories.certificateAuthorities'],
  ['csrs', 'rbac.categories.csrs'],
  ['user_certificates', 'userCertificates.title'],
  ['templates', 'rbac.categories.templates'],
  ['crl', 'common.crlOcsp'],
  ['truststore', 'rbac.categories.trustStore'],
  ['acme', 'rbac.categories.acme'],
  ['scep', 'rbac.categories.scep'],
  ['est', 'common.est'],
  ['xcep', 'xcepWstep.xcepTitle'],
  ['wstep', 'xcepWstep.wstepTitle'],
  ['kerberos', 'xcepWstep.kerberosTitle'],
  ['ad_connector', 'adConnector.title'],
  ['hsm', 'rbac.categories.hsmManagement'],
  ['ssh', 'rbac.categories.ssh'],
  ['policies', 'policies.title'],
  ['approvals', 'common.approvals'],
  ['key_recovery', 'common.keyRecovery'],
  ['audit', 'rbac.categories.auditLogs'],
  ['users', 'rbac.categories.userManagement'],
  ['groups', 'rbac.categories.groups'],
  ['settings', 'rbac.categories.settings'],
]
const ORDER = new Map(CATEGORY_LABELS.map(([resource], i) => [resource, i]))
const LABELS = new Map(CATEGORY_LABELS)
const ACTION_ORDER = ['read', 'write', 'delete']

/** Group `action:resource` scopes by resource, known resources first. */
export function groupPermissions(permissions = []) {
  const byResource = new Map()
  for (const perm of permissions) {
    const [action, resource] = String(perm).split(':')
    if (!resource) continue
    if (!byResource.has(resource)) byResource.set(resource, [])
    byResource.get(resource).push({ perm, action })
  }
  return [...byResource.entries()]
    .sort(([a], [b]) => (ORDER.get(a) ?? 999) - (ORDER.get(b) ?? 999) || a.localeCompare(b))
    .map(([resource, entries]) => ({
      key: resource,
      labelKey: LABELS.get(resource) || null,
      label: resource,
      permissions: entries
        .sort((x, y) => (ACTION_ORDER.indexOf(x.action) + 1 || 9) - (ACTION_ORDER.indexOf(y.action) + 1 || 9))
        .map(e => e.perm),
    }))
}

/** `read:certs` -> `read:certificates`, as the server reads legacy names. */
export function normalizePermission(perm) {
  const [action, resource] = String(perm).split(':')
  return resource === 'certs' ? `${action}:certificates` : perm
}

/** Stored permissions, legacy names normalised; none is ever dropped. */
export function normalizePermissions(stored = []) {
  return [...new Set((stored || []).map(normalizePermission))]
}

/** Stored permissions the server keeps but does not apply (reserved or unknown). */
export function ignoredPermissions(stored = [], grantable = []) {
  const allowed = new Set(grantable)
  return normalizePermissions(stored).filter(p => !allowed.has(p))
}

/** Stored permissions the role actually grants. */
export function appliedPermissions(stored = [], grantable = []) {
  const allowed = new Set(grantable)
  return normalizePermissions(stored).filter(p => allowed.has(p))
}
