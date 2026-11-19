/**
 * CAs page: the state of an authority, the tab views and the trust tree, as plain data.
 */
import { buildTree } from '../../lib/overviewHierarchy'
import { daysRemaining } from '../../lib/utils'
import { EXPIRY_WINDOW_DAYS, expiryBucket } from '../../lib/expiry'

export const nameOfCA = (ca) => ca?.name || ca?.descr || ca?.common_name || ''

/** 'pending' | 'revoked' | 'expired' | 'expiring' | 'active': the one state a node shows. */
export function caState(ca, now) {
  if (ca.status === 'Pending') return 'pending'
  if (ca.status === 'Revoked' || ca.revoked) return 'revoked'
  if (ca.status === 'Expired') return 'expired'
  const bucket = expiryBucket(daysRemaining(ca.valid_to || ca.not_after, now), EXPIRY_WINDOW_DAYS)
  if (bucket === 'expired') return 'expired'
  return bucket === 'expiring' ? 'expiring' : 'active'
}

/** Tab views, in order. The first three always show; the others only when they count something. */
export const CA_VIEWS = [
  { id: '', test: () => true, always: true },
  { id: 'roots', test: (ca) => ca.type === 'root', always: true },
  { id: 'intermediates', test: (ca) => ca.type !== 'root', always: true },
  { id: 'expired', test: (ca) => ca.status === 'Expired', always: true },
  { id: 'offline', test: (ca) => !!ca.offline },
  { id: 'revoked', test: (ca) => ca.status === 'Revoked' },
  { id: 'pending', test: (ca) => ca.status === 'Pending' },
]

const viewTest = (view) => (CA_VIEWS.find((v) => v.id === view) || CA_VIEWS[0]).test

/** [{ id, count }] of the tabs to show. */
export function viewCounts(cas) {
  return CA_VIEWS
    .map((v) => ({ id: v.id, count: cas.filter(v.test).length, always: v.always }))
    .filter((v) => v.always || v.count > 0)
    .map(({ id, count }) => ({ id, count }))
}

export function matchesQuery(ca, query) {
  const q = (query || '').trim().toLowerCase()
  if (!q) return true
  return [ca.name, ca.descr, ca.common_name, ca.subject].some((v) => (v || '').toLowerCase().includes(q))
}

/** The authorities a view and a search keep, in list order. */
export function filterCAs(cas, { view = '', query = '' } = {}) {
  const test = viewTest(view)
  return cas.filter((ca) => test(ca) && matchesQuery(ca, query))
}

const byName = (a, b) => nameOfCA(a).localeCompare(nameOfCA(b)) || a.id - b.id

/**
 * The trust tree a view and a search leave: a node stays when it matches or when one below it does.
 * `kids` holds the children shown, `allKids` every child (the counters never follow the filter).
 * A CA typed root is a root whatever parent it names; an intermediate without a known parent
 * heads its own subtree and is listed in `orphans`.
 */
export function buildForest(cas, { view = '', query = '' } = {}) {
  const { roots, kids: allKids } = buildTree(
    cas.map((ca) => (ca.type === 'root' && ca.parent_id ? { ...ca, parent_id: null } : ca)))
  const test = viewTest(view)
  const kids = new Map()
  const parentOf = new Map()
  const levelOf = new Map()
  const keep = (ca, level) => {
    levelOf.set(ca.id, level)
    const shown = (allKids.get(ca.id) || []).filter((child) => {
      parentOf.set(child.id, ca.id)
      return keep(child, level + 1)
    }).sort(byName)
    if (shown.length) kids.set(ca.id, shown)
    return shown.length > 0 || (test(ca) && matchesQuery(ca, query))
  }
  const shownRoots = roots.filter((ca) => keep(ca, 1)).sort(byName)
  const orphans = new Set(roots.filter((ca) => ca.type !== 'root').map((ca) => ca.id))
  const byId = new Map(cas.map((ca) => [ca.id, ca]))
  return { roots: shownRoots, kids, allKids, parentOf, levelOf, orphans, byId }
}

/** The forest with each node carrying its `children`, for the views that walk nested data. */
export function nestedForest({ roots, kids }) {
  const nest = (ca) => ({ ...ca, children: (kids.get(ca.id) || []).map(nest) })
  return roots.map(nest)
}

/** Roots with neither a sub-authority nor a certificate: bundled apart once there are this many. */
export const IDLE_BUNDLE_MIN = 9

/**
 * How the roots lay out: `branches` are drawn as cards with their subtree, `compact` on one line
 * each, `idle` folded in one group. A root that a cross-certificate links stays a card.
 */
export function layoutRoots(forest, { query = '', linked = new Set() } = {}) {
  const branches = []
  const leaves = []
  for (const root of forest.roots) {
    if (forest.kids.has(root.id) || linked.has(root.id)) branches.push(root)
    else leaves.push(root)
  }
  const isIdle = (ca) => !(ca.certs > 0) && !(forest.allKids.get(ca.id) || []).length
  const idle = leaves.filter(isIdle)
  // A search shows what it found: nothing stays folded
  if ((query || '').trim() || idle.length < IDLE_BUNDLE_MIN) return { branches, compact: leaves, idle: [] }
  return { branches, compact: leaves.filter((ca) => !isIdle(ca)), idle }
}

/** Something to repair, or a repair running: the chain repair strip then shows unasked. */
export const chainNeedsAttention = (data, findings = [], running = false) => running
  || findings.length > 0
  || (data?.stats?.orphan_cas || 0) > 0
  || (data?.stats?.same_key_distinct_certs || 0) > 0
