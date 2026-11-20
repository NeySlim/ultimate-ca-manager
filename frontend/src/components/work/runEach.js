/**
 * Bulk action without a bulk route: the unit calls run one after the other, and
 * each item gets its outcome (ok, or why it failed), in the order given.
 */
export async function runEach(items, call) {
  const out = []
  for (const item of items) {
    try {
      const result = await call(item)
      out.push({ item, ok: true, result })
    } catch (err) {
      out.push({ item, ok: false, reason: err?.message || String(err || '') })
    }
  }
  return out
}
