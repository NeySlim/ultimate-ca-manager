// ACME has no hold: a hold is local by design, never a CA left to be told
const HOLD_REASONS = new Set(['certificateHold', 'removeFromCRL'])
const isHoldReason = (reason) => HOLD_REASONS.has(reason)

// A revocation the issuing CA (ACME or Microsoft CA) was not told of stays local:
// the server says so in `meta`, and its message is the warning to show.
export function localOnlyRevocationWarning(res, t) {
  const meta = res?.meta || {}
  if (!meta.acme_local_only && !meta.related_acme_local_only && !meta.msca_local_only) return null
  return res?.message || t('revocation.revokedLocallyOnly')
}

// A bulk revocation lists in `data` the certificates whose issuing CA was not told
export function bulkLocalOnlyRevocationWarning(data, t, reason) {
  const acme = isHoldReason(reason) ? [] : (data?.acme_local_only || [])
  const ids = [...new Set([...acme, ...(data?.msca_local_only || [])])]
  if (!ids.length) return null
  return t('revocation.bulkRevokedLocallyOnly', { count: ids.length, ids: ids.map(id => `#${id}`).join(', ') })
}

// An approved revocation flags the certificate it returns, with the single route's ACME warning
export function approvedLocalOnlyRevocationWarning(certificate, t) {
  const acme = !!certificate?.acme_local_only && !isHoldReason(certificate?.reason)
  if (acme && certificate?.acme_message) return certificate.acme_message
  if (!acme && !certificate?.msca_local_only) return null
  return t('revocation.revokedLocallyOnly')
}
