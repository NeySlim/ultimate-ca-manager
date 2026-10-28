const KINDS = [['ca', 'cas'], ['certificate', 'certificates'], ['csr', 'csrs']]

// The one object a Smart Import created, or null when it created none or several
export function soleImported(result) {
  // A failed import is rolled back, even the ids it lists
  if (!result || result.success === false) return null
  const ids = result?.imported_ids || {}
  const found = KINDS.flatMap(([type, key]) => (ids[key] || []).map((id) => ({ type, id })))
  return found.length === 1 ? found[0] : null
}

// Cross-certificates a Smart Import attached to a held root, or left out because it could not (#400)
export function crossSummary(result) {
  const details = result?.warning_details || []
  return {
    attached: details.filter(d => d.code === 'cross_certificate_attached').length,
    skipped: details.filter(d => d.code === 'cross_certificate_skipped').length,
  }
}
