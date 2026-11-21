/** Pure helpers of the protocol pages, apart so the pages export components only. */

const DAY = 24 * 3600 * 1000

/** The state of a CRL from its real dates: none, past its nextUpdate, due within 24 h, up to date (M12). */
export function crlState(row, now = Date.now()) {
  if (!row.has_crl) return 'none'
  const next = row.crl_next_update ? Date.parse(row.crl_next_update) : NaN
  if (Number.isFinite(next) && next < now) return 'expired'
  if (Number.isFinite(next) && next - now < DAY) return 'soon'
  return 'current'
}

/** Ids of the rows whose non-empty key an earlier row already holds. */
export function repeatedRows(rows) {
  const seen = new Set()
  const repeated = new Set()
  for (const r of rows) {
    if (r.key && seen.has(r.key)) repeated.add(r.id)
    seen.add(r.key)
  }
  return repeated
}
