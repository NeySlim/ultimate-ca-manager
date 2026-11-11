// A revocation the issuing CA (ACME or Microsoft CA) was not told of stays local:
// the server says so in `meta`, and its message is the warning to show.
export function localOnlyRevocationWarning(res, t) {
  const meta = res?.meta || {}
  if (!meta.acme_local_only && !meta.msca_local_only) return null
  return res?.message || t('revocation.revokedLocallyOnly')
}
