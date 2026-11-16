// UCM fields an attribute mapping row can target (same list as the backend).
const UCM_FIELDS = ['username', 'email', 'fullname', 'groups']

const clean = (s) => (typeof s === 'string' ? s.trim() : '')

// The legacy `groups -> attribute` row, trimmed like the backend, when a form row
// `attribute -> groups` makes the backend stop reading it; else null.
function hiddenLegacyRow(mapping) {
  const entries = Object.entries(mapping || {})
  const hasFormRow = entries.some(([k, v]) => clean(k) && clean(k) !== 'groups' && clean(v) === 'groups')
  if (!hasFormRow) return null
  const row = entries.find(([k, v]) => clean(k) === 'groups' && clean(v) && !UCM_FIELDS.includes(clean(v)))
  return row ? { key: row[0], attribute: clean(row[1]) } : null
}

// The attribute a hidden legacy row names when it already is a key aimed elsewhere: no rewrite can keep both.
export function legacyGroupsConflict(mapping) {
  const legacy = hiddenLegacyRow(mapping)
  if (!legacy) return null
  const clash = Object.entries(mapping).some(([k, v]) => clean(k) === legacy.attribute && clean(v) !== 'groups')
  return clash ? legacy.attribute : null
}

// Rewrite the hidden legacy row into the form's shape so both group sources stay read.
export function keepLegacyGroupsRead(mapping) {
  const legacy = hiddenLegacyRow(mapping)
  if (!legacy || legacyGroupsConflict(mapping)) return mapping
  const { [legacy.key]: _legacy, ...rest } = mapping
  const covered = Object.keys(rest).some(k => clean(k) === legacy.attribute)
  return covered ? rest : { ...rest, [legacy.attribute]: 'groups' }
}
