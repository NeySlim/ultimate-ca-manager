// UCM fields an attribute mapping row can target (same list as the backend).
const UCM_FIELDS = ['username', 'email', 'fullname', 'groups']

// What Python's str.strip() removes: the backend trims with it, and trim() removes another set.
const SPACES = new Set([9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 0x85, 0xa0, 0x1680, 0x2000, 0x2001, 0x2002,
  0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008, 0x2009, 0x200a, 0x2028, 0x2029, 0x202f, 0x205f, 0x3000])

// Linear on any input: the screen runs it on every keystroke.
function clean(s) {
  if (typeof s !== 'string') return ''
  let start = 0
  let end = s.length
  while (start < end && SPACES.has(s.charCodeAt(start))) start += 1
  while (end > start && SPACES.has(s.charCodeAt(end - 1))) end -= 1
  return s.slice(start, end)
}

// Attributes the backend stops reading: those of the legacy `groups -> attribute` rows, once
// a row `attribute -> groups` exists, unless such a row reads them (its mapped_attributes).
export function hiddenLegacyGroupRows(mapping) {
  const entries = Object.entries(mapping || {}).map(([k, v]) => [clean(k), clean(v)])
  const read = new Set(entries.filter(([k, v]) => k && v === 'groups').map(([k]) => k))
  if (!read.size) return []
  const legacy = entries.filter(([k, v]) => k === 'groups' && v && !UCM_FIELDS.includes(v)).map(([, v]) => v)
  return [...new Set(legacy)].filter((attribute) => !read.has(attribute))
}
