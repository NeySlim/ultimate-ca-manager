// Short name for the summary chip: 'SHA256' of 'SHA256-RSA', 'RSASSA-PSS' of a PSS label
export function signatureShortName(signatureAlgorithm) {
  if (!signatureAlgorithm) return '—'
  if (signatureAlgorithm.startsWith('RSASSA-PSS')) return 'RSASSA-PSS'
  return signatureAlgorithm.split('-')[0]
}
