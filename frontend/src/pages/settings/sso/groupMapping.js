// UCM fields an attribute mapping row can target (same list as the backend).
const UCM_FIELDS = ['username', 'email', 'fullname', 'groups']

const clean = (s) => (typeof s === 'string' ? s.trim() : '')

// Attributes of the legacy `groups -> attribute` rows the backend stops reading because
// a row `attribute -> groups` exists (same trimming rules as its mapped_attributes).
export function hiddenLegacyGroupRows(mapping) {
  const entries = Object.entries(mapping || {}).map(([k, v]) => [clean(k), clean(v)])
  if (!entries.some(([k, v]) => k && v === 'groups')) return []
  const legacy = entries.filter(([k, v]) => k === 'groups' && v && !UCM_FIELDS.includes(v)).map(([, v]) => v)
  return [...new Set(legacy)]
}
