/** The four states of a certificate as the mockup's statuses: tone, icon and label key. */
// The mockup's badge(): the state's tone and icon
export const STATES = {
  valid: { tone: 'good', icon: 'check', key: 'common.valid' },
  expiring: { tone: 'warn', icon: 'clock', key: 'certificates.views.expiring' },
  expired: { tone: 'bad', icon: 'warning', key: 'common.expired' },
  revoked: { tone: 'muted', icon: 'block', key: 'common.revoked' },
}
export const GRADE_TONES = { 'A+': 'good', A: 'good', B: 'good', C: 'warn', D: 'warn', F: 'bad' }
// The mockup's icon per source; anything else is a certificate
export const SOURCE_ICONS = { acme: 'refresh', acme_client: 'refresh', 'acme-renewal': 'refresh', letsencrypt: 'refresh', scep: 'globe', est: 'globe', import: 'upload', imported: 'upload', upload: 'upload' }

export const stateOf = (row) => (row?.revoked ? 'revoked' : STATES[row?.status] ? row.status : null)

