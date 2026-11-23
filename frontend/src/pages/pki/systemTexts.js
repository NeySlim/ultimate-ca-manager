/**
 * Texts the server writes in English for the objects it creates itself (the system trust bundle, the
 * built-in templates), shown in the user's language when known; any other text is the user's, shown as written.
 */

const SYSTEM_BUNDLE_DESCRIPTION = 'Imported from system CA bundle'
const SYSTEM_BUNDLE_NOTE = /^Auto-imported from (\S+)$/

/** A trust anchor's description or notes, translated when the server wrote it for the system bundle. */
export function trustStoreText(t, value) {
  if (value === SYSTEM_BUNDLE_DESCRIPTION) return t('trustStore.systemBundleDescription')
  const note = typeof value === 'string' && value.match(SYSTEM_BUNDLE_NOTE)
  return note ? t('trustStore.systemBundleNote', { path: note[1] }) : value
}

// The built-in templates by their server name: the key of their name and description
// (the names of an older seed included)
export const SYSTEM_TEMPLATES = {
  'Web Server (TLS/SSL)': 'webServer',
  'Email (S/MIME)': 'email',
  'Email Certificate (S/MIME)': 'email',
  'VPN Server': 'vpnServer',
  'VPN Client': 'vpnClient',
  'Code Signing': 'codeSigning',
  'Client Certificate': 'clientCert',
  'Client Authentication': 'clientAuth',
  'OCSP Signing': 'ocspSigning',
  'Smartcard Logon': 'smartcardLogon',
}

/** A system template's name or description in the user's language; a custom template keeps its own. */
export function templateText(t, tpl, field) {
  const key = tpl?.is_system ? SYSTEM_TEMPLATES[tpl.name] : null
  const value = tpl?.[field]
  if (!key) return value
  const path = `templates.builtIn.${key}.${field}`
  const text = t(path, { defaultValue: value })
  return text && text !== path ? text : value
}
