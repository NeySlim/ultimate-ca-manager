/** Hierarchy card of the overview: the tree under its roots, bounded to a few lines. */

/** The card never lists more authorities than this, whatever the installation holds. */
export const HIERARCHY_LIMIT = 10
// With several roots, each first gets this many lines so that more than one tree shows
const PER_ROOT = 5

/** Roots first: a CA whose parent is absent from the list is a root of its own subtree. */
export function buildTree(cas) {
  const ids = new Set(cas.map((c) => c.id))
  const kids = new Map()
  const roots = []
  for (const ca of cas) {
    if (ca.parent_id && ids.has(ca.parent_id)) {
      kids.set(ca.parent_id, [...(kids.get(ca.parent_id) || []), ca])
    } else roots.push(ca)
  }
  return { roots, kids }
}

export const nameOf = (ca) => ca.descr || ca.common_name || '–'

/**
 * At most `limit` authorities: the trees that issued most, then the largest, each filled level
 * by level. `shown` maps an authority to its children kept; `listed` counts the lines.
 */
export function boundedTree(cas, issued, limit = HIERARCHY_LIMIT) {
  const { roots, kids } = buildTree(cas)
  const weight = new Map()
  const weigh = (ca) => {
    const below = (kids.get(ca.id) || []).map(weigh)
    const w = { size: 1 + below.reduce((s, b) => s + b.size, 0),
      issued: (issued?.get(ca.refid) || 0) + below.reduce((s, b) => s + b.issued, 0) }
    weight.set(ca.id, w)
    return w
  }
  roots.forEach(weigh)
  const rank = (a, b) => weight.get(b.id).issued - weight.get(a.id).issued
    || weight.get(b.id).size - weight.get(a.id).size || nameOf(a).localeCompare(nameOf(b))
  const shown = new Map()
  const picked = []
  let left = limit
  const fill = (queue, budget) => {
    let room = budget
    while (queue.length > 0 && room > 0) {
      const node = queue[0]
      const next = [...(kids.get(node.id) || [])].sort(rank)[shown.get(node.id).length]
      if (!next) { queue.shift(); continue }
      shown.get(node.id).push(next)
      shown.set(next.id, [])
      queue.push(next)
      room -= 1
      left -= 1
    }
  }
  const queues = []
  const ordered = [...roots].sort(rank)
  for (const root of ordered) {
    if (left <= 0) break
    picked.push(root)
    shown.set(root.id, [])
    left -= 1
    const queue = [root]
    queues.push(queue)
    fill(queue, Math.min(left, (ordered.length > 1 ? PER_ROOT : limit) - 1))
  }
  // Lines left over go to the trees already shown, in the same order
  for (const queue of queues) fill(queue, left)
  return { roots: picked, shown, kids, rootCount: roots.length, listed: limit - left }
}
