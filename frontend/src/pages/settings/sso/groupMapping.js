// UCM fields an attribute mapping row can target (same list as the backend).
const UCM_FIELDS = ['username', 'email', 'fullname', 'groups']

// What Python's str.strip() removes: the backend trims with it, and trim() removes another set.
const EDGES = /^[\t-\r\x1c-\x20\x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\t-\r\x1c-\x20\x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/g
const clean = (s) => (typeof s === 'string' ? s.replace(EDGES, '') : '')

// Attributes the backend stops reading: those of the legacy `groups -> attribute` rows, once
// a row `attribute -> groups` exists, unless such a row reads them (its mapped_attributes).
export function hiddenLegacyGroupRows(mapping) {
  const entries = Object.entries(mapping || {}).map(([k, v]) => [clean(k), clean(v)])
  const read = new Set(entries.filter(([k, v]) => k && v === 'groups').map(([k]) => k))
  if (!read.size) return []
  const legacy = entries.filter(([k, v]) => k === 'groups' && v && !UCM_FIELDS.includes(v)).map(([, v]) => v)
  return [...new Set(legacy)].filter((attribute) => !read.has(attribute))
}
