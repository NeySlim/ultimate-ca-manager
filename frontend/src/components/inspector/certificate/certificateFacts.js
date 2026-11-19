import { hasExpiry } from '../../../lib/expiry'

const DAY = 86400000

/** Alternative names as the certificate lists them, falling back on the combined column. */
export function alternativeNames(cert) {
  const entries = cert?.extensions?.subject_alt_names?.entries
  if (entries?.length) return entries.map((e) => ({ type: e.type, value: e.value }))
  return String(cert?.san_combined || '').split(',').map((s) => s.trim()).filter(Boolean).map((value) => ({ type: null, value }))
}

/** Days left, share of the validity left (0 to 100) and tone, from the record. */
export function validityFacts(cert) {
  const days = hasExpiry(cert.days_remaining) ? cert.days_remaining : null
  const from = cert.valid_from ? new Date(cert.valid_from).getTime() : NaN
  const to = cert.valid_to ? new Date(cert.valid_to).getTime() : NaN
  const total = Number.isFinite(from) && Number.isFinite(to) && to > from ? (to - from) / DAY : null
  const share = days === null || !total ? null : Math.max(0, Math.min(100, (days / total) * 100))
  const state = cert.revoked ? 'revoked' : (days !== null && days <= 0) || cert.status === 'expired' ? 'expired' : cert.status === 'expiring' ? 'expiring' : 'valid'
  return { days, share, state, tone: { expired: 'bad', expiring: 'warn' }[state] || '' }
}
