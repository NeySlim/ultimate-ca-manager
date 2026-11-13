/**
 * Rules the Windows enrollment profile screens apply before the server does. The server
 * stays the judge: it upper-cases nothing it is given in this form and refuses the rest.
 */

export const PROFILE_STATES = ['complete', 'keytab_missing', 'connector_failing', 'disabled']

/** An i18n key saying why *realm* cannot be a profile's, or null. A KDC compares realms exactly (RFC 4120 6.1). */
export function realmProblem(realm) {
  const value = (realm || '').trim()
  if (!value) return 'xcepWstep.realmRequired'
  if (value !== value.toUpperCase()) return 'xcepWstep.realmCapitals'
  if (/\s/.test(value)) return 'xcepWstep.realmSpaces'
  return null
}

/** The realm a connector's base DN names (DC=corp,DC=example is CORP.EXAMPLE), or null. */
export function realmOfBaseDn(baseDn) {
  const parts = (baseDn || '').split(',').map(p => p.trim()).filter(p => /^dc=/i.test(p))
  return parts.length ? parts.map(p => p.slice(3)).join('.').toUpperCase() : null
}

/** Entries of a keytab grouped by realm: [{ realm, entries }], realms sorted. */
export function groupEntriesByRealm(entries) {
  const byRealm = new Map()
  for (const entry of entries || []) {
    if (!byRealm.has(entry.realm)) byRealm.set(entry.realm, [])
    byRealm.get(entry.realm).push(entry)
  }
  return [...byRealm.keys()].sort().map(realm => ({ realm, entries: byRealm.get(realm) }))
}

/** Realms of *entries* other than the profile's. */
export function foreignRealms(entries, profileRealm) {
  return groupEntriesByRealm(entries).map(g => g.realm).filter(r => r !== profileRealm)
}

/**
 * What a profile still lacks for a Windows client to enrol through it. `ok` is false for what
 * is missing; `action` names where it is fixed.
 */
export function profileChecklist(profile, { autoenrollTemplates = 0 } = {}) {
  const connectorDown = profile.connector_health === 'down'
  return [
    { key: 'realm', ok: Boolean(profile.realm) },
    { key: 'issuingCa', ok: Boolean(profile.issuing_ca_refid) },
    { key: 'keytab', ok: Boolean(profile.keytab_set) },
    {
      key: 'connector',
      ok: !profile.connector_id || (profile.connector_enabled !== false && !connectorDown),
      absent: !profile.connector_id,
    },
    { key: 'templates', ok: autoenrollTemplates > 0, count: autoenrollTemplates },
    { key: 'enabled', ok: Boolean(profile.enabled) },
  ]
}
