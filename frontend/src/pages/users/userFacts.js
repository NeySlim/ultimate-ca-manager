/** Facts of an account the users page and its dock read: role words, sign-on source, name, granted permissions. */
export const ROLE_KEYS = { admin: 'users.admin', operator: 'common.operator', auditor: 'common.auditor', viewer: 'common.viewer' }
export const ssoRowsOf = (u) => (u && u.sso_identities) || []
export const isSso = (u) => ssoRowsOf(u).length > 0
export const userName = (u) => u.full_name || u.username

const PROVIDER_TYPES = { ldap: 'users.authSource.ldap', oauth2: 'users.authSource.oauth2', saml: 'users.authSource.saml' }

/** Every provider that opens the account, by type and name, after « SSO »; « Local » when none. */
export function sourceText(t, u) {
  const rows = ssoRowsOf(u)
  if (!rows.length) return t('users.authSource.local')
  const names = rows.map((r) => [PROVIDER_TYPES[r.provider_type] ? t(PROVIDER_TYPES[r.provider_type]) : r.provider_type,
    r.provider_name || t('users.sso.deletedProvider')].filter(Boolean).join(' '))
  return t('users.sourceSso', { providers: names.join(', ') })
}

/** Granted when the effective list holds the permission, `*`, or a wildcard on its action or resource. */
export function grants(effective, perm) {
  if (effective.includes('*') || effective.includes(perm)) return true
  const [action, resource] = perm.split(':')
  return effective.includes(`${action}:*`) || effective.includes(`*:${resource}`)
}

