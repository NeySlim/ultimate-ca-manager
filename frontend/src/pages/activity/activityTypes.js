/**
 * Operation types of the journal, as the mockup's eventTypes: a label, an icon. The server stores
 * an action code per entry; each code falls into the first type whose pattern it matches, so the
 * type filter asks the server for the actions of that type (action=…), from the server's own list.
 */
export const TYPES = [
  { key: 'issued', icon: 'cert', test: /^(cert_created|certificate\.issued|certificate_created|csr_signed|csrs_bulk_signed|ssh_cert_issued|ssh_cert_generated|msca\.sign|acme\.order\.finalize|acme_finalize|tsa\.timestamp_issued)$/ },
  { key: 'renewed', icon: 'refresh', test: /renew/ },
  { key: 'revoked', icon: 'block', test: /revok|unheld/ },
  { key: 'exported', icon: 'download', test: /export|download/ },
  { key: 'certificates', icon: 'cert', test: /^(cert_|certificate|csr|ssh_cert)/ },
  { key: 'approval', icon: 'approve', test: /^key_recovery\.|approve|deny_request/ },
  { key: 'crl', icon: 'crl', test: /crl|ocsp/ },
  { key: 'acme', icon: 'refresh', test: /^acme|^dns_provider/ },
  { key: 'scep', icon: 'globe', test: /^scep|^intune/ },
  { key: 'auth', icon: 'lock', test: /^(login|logout|mfa_|password_change|webauthn_)/ },
  { key: 'users', icon: 'users', test: /^(user_|users_|group_|role_change|apikey_|mtls_cert_|admin_mtls_)/ },
  { key: 'backups', icon: 'archive', test: /backup|^system_restore/ },
  { key: 'settings', icon: 'settings', test: /settings|config|^sso_provider|^smtp_oauth|^https_apply|toggle/ },
  { key: 'setup', icon: 'settings', test: /^(ca_|cas_|template|truststore|hsm_|ssh_ca_|msca\.|deploy_|discovery_|webhook)/ },
  { key: 'system', icon: 'server', test: /./ },
]

const BY_KEY = Object.fromEntries(TYPES.map((t) => [t.key, t]))
// Matching order (the select keeps the order above): a narrower family before a broader word
const MATCH = ['issued', 'renewed', 'approval', 'auth', 'users', 'acme', 'scep', 'crl', 'backups', 'settings',
  'revoked', 'exported', 'certificates', 'setup', 'system'].map((k) => BY_KEY[k])

/** The type of an action code; an empty or unknown code is a system entry. */
export function typeOf(action) {
  const code = String(action || '')
  return (MATCH.find((t) => t.test.test(code)) || BY_KEY.system).key
}

export const typeIcon = (key) => BY_KEY[key]?.icon || 'cert'

/** The actions of the server's list that fall into `type`. */
export const actionsOfType = (actions, type) => (actions || []).filter((a) => typeOf(a) === type)

/** The types present in the server's list, in the order above. */
export const presentTypes = (actions) => {
  const seen = new Set((actions || []).map(typeOf))
  return TYPES.filter((t) => seen.has(t.key)).map((t) => t.key)
}

/**
 * The action list sent to the server: the type's actions, narrowed by the chosen actions.
 * null = no action filter; [] = nothing can match (the page then reads nothing).
 */
export function effectiveActions(actions, type, chosen) {
  const picked = Array.isArray(chosen) ? chosen.filter(Boolean) : []
  if (!type) return picked.length ? picked : null
  const ofType = actionsOfType(actions, type)
  if (!picked.length) return ofType
  const allowed = new Set(ofType)
  return picked.filter((a) => allowed.has(a))
}

// Acronyms and product names inside an action code, written as the interface writes them
const WORDS = {
  acme: 'ACME', scep: 'SCEP', est: 'EST', crl: 'CRL', ocsp: 'OCSP', csr: 'CSR', csrs: 'CSRs', ca: 'CA', cas: 'CAs',
  hsm: 'HSM', ssh: 'SSH', sso: 'SSO', mfa: 'MFA', '2fa': '2FA', totp: 'TOTP', api: 'API', apikey: 'API key', ldap: 'LDAP',
  mtls: 'mTLS', tsa: 'TSA', wstep: 'WSTEP', xcep: 'XCEP', eab: 'EAB', smtp: 'SMTP', oauth: 'OAuth', https: 'HTTPS',
  ct: 'CT', dns: 'DNS', msca: 'Microsoft CA', webauthn: 'WebAuthn', intune: 'Intune',
}

/**
 * The operation an action code names: its label in the language when there is one (audit.actions, the code's dots
 * as underscores), else the code made readable, "cert_revoked" → "Cert revoked", "scep_challenge_read" → "SCEP challenge read".
 */
export function actionLabel(action, t) {
  const code = String(action || '')
  const key = `audit.actions.${code.replace(/\./g, '_')}`
  const named = t && code ? t(key, { defaultValue: '' }) : ''
  if (named && !named.startsWith(key)) return named
  const [first = '', ...rest] = code.split(/[._]+/).filter(Boolean)
  const head = WORDS[first.toLowerCase()] || (first && first[0].toUpperCase() + first.slice(1))
  return [head, ...rest.map((w) => WORDS[w.toLowerCase()] || w)].join(' ')
}
