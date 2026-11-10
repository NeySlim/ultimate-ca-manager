/**
 * List filters the overview links carry in the URL (`filter_hint` of the API):
 * parsed, sent to the certificate list as they are, and removable one by one.
 */
export const OVERVIEW_FILTER_KEYS = [
  'status', 'live', 'key_algo', 'key_algo_prefix', 'key_bits_below', 'sig_hash', 'server',
  'lifetime_over_days', 'no_key', 'incomplete_chain', 'renewal',
]
const MULTI = new Set(['status', 'key_algo', 'sig_hash', 'renewal'])
// The statuses the list accepts (CERTIFICATE_STATUS_FILTERS); any other is dropped from the link
export const CERT_STATUSES = ['valid', 'expiring', 'expired', 'revoked', 'orphan', 'archived']
const ALLOWED = { status: new Set(CERT_STATUSES) }

/** Ordered [key, value] pairs of the known filters in a query string. */
export function parseOverviewFilters(search) {
  const params = new URLSearchParams(search || '')
  const pairs = []
  for (const key of OVERVIEW_FILTER_KEYS) {
    const values = MULTI.has(key) ? params.getAll(key) : params.getAll(key).slice(0, 1)
    for (const value of values) {
      if (value !== '' && (!ALLOWED[key] || ALLOWED[key].has(value))) pairs.push([key, value])
    }
  }
  return pairs
}

/** The params object certificatesService.getAll expects (arrays for repeated keys). */
export function toListParams(pairs) {
  const out = {}
  for (const [key, value] of pairs) {
    if (MULTI.has(key)) out[key] = [...(out[key] || []), value]
    else out[key] = value
  }
  return out
}

/** `/certificates?...` for an API filter hint ({key: value | [values]}); null without a hint. */
export function listHref(hint) {
  if (!hint || typeof hint !== 'object') return null
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(hint)) {
    for (const v of Array.isArray(value) ? value : [value]) params.append(key, String(v))
  }
  return `/certificates?${params.toString()}`
}

/** The query string without one filter (or one value of a repeated filter). */
export function withoutFilter(search, key, value) {
  const params = new URLSearchParams(search || '')
  const kept = value === undefined ? [] : params.getAll(key).filter((v) => v !== value)
  params.delete(key)
  for (const v of kept) params.append(key, v)
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

/** The query string (`?a=1&b=2`, or '') of known-filter pairs. */
export function toSearch(pairs) {
  const params = new URLSearchParams()
  for (const [key, value] of pairs) params.append(key, value)
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}
