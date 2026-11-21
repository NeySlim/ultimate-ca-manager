/** Pure helpers of the protocol pages, apart so the pages export components only. */

const DAY = 24 * 3600 * 1000

/** The state of a CRL from its real dates: none, past its nextUpdate, due within 24 h, up to date (M12). */
export function crlState(row, now = Date.now()) {
  if (!row.has_crl) return 'none'
  const next = row.crl_next_update ? Date.parse(row.crl_next_update) : NaN
  if (Number.isFinite(next) && next < now) return 'expired'
  if (Number.isFinite(next) && next - now < DAY) return 'soon'
  return 'current'
}

/** Ids of the rows whose non-empty key an earlier row already holds. */
export function repeatedRows(rows) {
  const seen = new Set()
  const repeated = new Set()
  for (const r of rows) {
    if (r.key && seen.has(r.key)) repeated.add(r.id)
    seen.add(r.key)
  }
  return repeated
}

/** The CN of a DN like "CN=device,OU=MDM,O=UCM,C=FR", and its other parts. */
export function parseDN(dn) {
  const parts = {}
  const regex = /([A-Z]+)=([^,]+)/g
  let match
  while (dn && (match = regex.exec(dn)) !== null) parts[match[1]] = match[2]
  return { cn: parts.CN || null, parts }
}

/** ACME accounts: the tone of a state, the short name (the start of the ACME identifier, as the client orders show it), the contact. */
export const ACCOUNT_TONES = { valid: 'good', deactivated: 'muted', revoked: 'bad' }
export const accountLabel = (a) => `acct/${(a.account_id || String(a.id)).slice(0, 12)}`
export const accountContact = (a) => a.contact?.[0]?.replace('mailto:', '') || a.email || ''

/** RFC 8555 §8.3: the CA fetches the key authorization over plain HTTP, port 80; ':' marks an IPv6 literal. */
export function http01Url(domain, data) {
  const host = domain.includes(':') ? `[${domain}]` : domain
  return `http://${host}/.well-known/acme-challenge/${data.token}`
}
