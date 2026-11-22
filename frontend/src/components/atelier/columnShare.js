/** The share of a list's width among its free-text columns when short of room (DataTable). */

// The narrowest a free-text column gives way to before a column folds (its header and CSS minimum may hold it wider)
export const CEDE_FLOOR = 120

/**
 * The ceilings that absorb `over` px from the free-text columns of these natural widths: one ceiling lowered from the
 * widest column down, so the widest gives way first, none under its floor (CEDE_FLOOR or the cell's own minimum, `floors`).
 * Null when no column is wider than its floor.
 */
export function cedeWidths(widths, over, floors = {}) {
  const items = Object.entries(widths).map(([id, w]) => [id, w, Math.max(CEDE_FLOOR, floors[id] || 0)]).filter(([, w, f]) => w > f)
  if (!items.length) return null
  const freed = (level) => items.reduce((sum, [, w, f]) => sum + Math.max(0, w - Math.max(f, level)), 0)
  // The highest whole ceiling that frees enough; 0 when even the floors are not enough
  let lo = 0
  let hi = Math.ceil(Math.max(...items.map(([, w]) => w)))
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2)
    if (freed(mid) >= over) lo = mid; else hi = mid - 1
  }
  return Object.fromEntries(items.filter(([, w, f]) => w > Math.max(f, lo)).map(([id, , f]) => [id, Math.max(f, lo)]))
}
