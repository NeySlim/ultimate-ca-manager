/** How the History panel reads the audit log: the window of entries read, and the words of an action. */
export const AUDIT_WINDOW = 100
// What an audit action did, as a sentence of the history; the first match wins
const AUDIT_WORDS = [
  [/renewal_failed/, 'renewFailed'], [/creat|issu/, 'issued'], [/import/, 'imported'], [/renew/, 'renewed'],
  [/unhold|unheld/, 'unheld'], [/hold/, 'held'], [/revok/, 'revokedPlain'], [/delet/, 'deleted'], [/renam/, 'renamed'],
  [/key_upload/, 'keyUploaded'], [/export|\.(pem|der|jks|p12|pfx)$/, 'exported'], [/updat/, 'updated'],
]
/** The i18n key under inspector.history that words an audit action, or null for an action it does not know. */
export function auditWords(action) {
  const a = String(action || '').toLowerCase()
  return AUDIT_WORDS.find(([re]) => re.test(a))?.[1] || null
}
