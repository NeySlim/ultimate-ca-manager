/**
 * The server caps a bulk request at 100 ids (services/deletion_blockers).
 *
 * The screens let an operator select a whole page and more, so a selection
 * past the cap answered 400 with nothing done. Splitting it here keeps the
 * one-request-per-batch contract the routes were written for.
 */
export const MAX_BULK_IDS = 100

// relatedOf(id) names the other member of a pair: both selected members go in one
// batch, since the server only knows what it did with a pair within one request.
export function chunkIds(ids, size = MAX_BULK_IDS, relatedOf = null) {
  const list = Array.isArray(ids) ? ids : []
  if (!relatedOf) {
    const chunks = []
    for (let start = 0; start < list.length; start += size) {
      chunks.push(list.slice(start, start + size))
    }
    return chunks
  }
  const selected = new Set(list)
  const partner = new Map()
  for (const id of list) {
    const other = relatedOf(id)
    // Only a mutual link is a pair to the server: a one-way link must not claim a member
    if (other == null || other === id || !selected.has(other) || relatedOf(other) !== id) continue
    partner.set(id, other)
  }
  const chunks = []
  const placed = new Set()
  let current = []
  for (const id of list) {
    if (placed.has(id)) continue
    const other = partner.get(id)
    const group = other != null && !placed.has(other) ? [id, other] : [id]
    if (current.length && current.length + group.length > size) {
      chunks.push(current)
      current = []
    }
    for (const member of group) { current.push(member); placed.add(member) }
  }
  if (current.length) chunks.push(current)
  return chunks
}

/**
 * Run `send` over each batch and merge the bodies into one result.
 *
 * Every array the routes answer with is concatenated, not just `success` and
 * `failed`: bulk sign also answers `pending_approval`, and merging a fixed
 * pair dropped it, so a selection over the cap looked like zero approvals
 * raised while the server had created them.
 */
export async function runInBatches(ids, send, { relatedOf } = {}) {
  const batches = chunkIds(ids, MAX_BULK_IDS, relatedOf)
  if (batches.length <= 1) return send(batches[0] || [])

  const merged = {}
  for (const batch of batches) {
    const answer = await send(batch)
    const body = answer?.data ?? answer ?? {}
    for (const [key, value] of Object.entries(body)) {
      if (Array.isArray(value)) {
        merged[key] = [...(merged[key] || []), ...value]
      } else if (!(key in merged)) {
        // A scalar the route reports once (a count, a message): the first
        // batch answers for the selection rather than the last.
        merged[key] = value
      }
    }
  }
  // Keep the shape the callers read even when no batch reported them.
  merged.success = merged.success || []
  merged.failed = merged.failed || []
  return { data: merged }
}
