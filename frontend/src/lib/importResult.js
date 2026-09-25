const KINDS = [['ca', 'cas'], ['certificate', 'certificates'], ['csr', 'csrs']]

// The one object a Smart Import created, or null when it created none or several
export function soleImported(result) {
  const ids = result?.imported_ids || {}
  const found = KINDS.flatMap(([type, key]) => (ids[key] || []).map((id) => ({ type, id })))
  return found.length === 1 ? found[0] : null
}
