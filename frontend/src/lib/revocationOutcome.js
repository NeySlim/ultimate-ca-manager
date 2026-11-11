// A revocation the issuing CA (ACME or Microsoft CA) was not told of stays local:
// the server says so in `meta`, and its message is the warning to show.
export function localOnlyRevocationWarning(res, t) {
  const meta = res?.meta || {}
  if (!meta.acme_local_only && !meta.msca_local_only) return null
  return res?.message || t('revocation.revokedLocallyOnly')
}

// A bulk revocation lists in `data` the certificates whose issuing CA was not told
export function bulkLocalOnlyRevocationWarning(data, t) {
  const ids = [...new Set([...(data?.acme_local_only || []), ...(data?.msca_local_only || [])])]
  if (!ids.length) return null
  return t('revocation.bulkRevokedLocallyOnly', { count: ids.length, ids: ids.map(id => `#${id}`).join(', ') })
}

// An approved revocation flags the certificate it returns
export function approvedLocalOnlyRevocationWarning(certificate, t) {
  if (!certificate?.acme_local_only && !certificate?.msca_local_only) return null
  return t('revocation.revokedLocallyOnly')
}
