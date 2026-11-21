/**
 * CAs page: the state of an authority, the tab views and the trust tree, as plain data.
 */
import { buildTree } from '../../lib/overviewHierarchy'
import { daysRemaining } from '../../lib/utils'
import { EXPIRY_WINDOW_DAYS, expiryBucket } from '../../lib/expiry'
import { holdsNoKey, needsKeyImport } from '../../lib/caSelection'
import { isPostQuantum } from '../../lib/keyAlgorithms'

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

// The mockup's caStates (active, revoked) and the product's own states, in the same grammar
export const CA_STATES = {
  active: { tone: 'good', icon: 'check', key: 'cas.state.active' },
  expiring: { tone: 'warn', icon: 'clock', key: 'cas.state.expiring' },
  expired: { tone: 'bad', icon: 'warning', key: 'cas.state.expired' },
  revoked: { tone: 'bad', icon: 'block', key: 'cas.state.revoked' },
  pending: { tone: 'warn', icon: 'clock', key: 'cas.awaitingCertificate' },
}

/** The marks an authority carries, as [{ id, icon, label, title, tone, cross }]. */
export function caMarks(ca, t, { orphan = false } = {}) {
  const marks = []
  if (ca.offline) {
    const mode = ca.offline_mode === 'file_exported' ? t('cas.offlineFileExported') : t('cas.offlinePasswordProtected')
    marks.push({ id: 'offline', icon: 'lock', label: t('cas.offline'), title: ca.offline_reason || mode })
  }
  if (ca.uses_hsm) {
    const where = [ca.hsm_provider_name, ca.hsm_key_label].filter(Boolean).join(' / ')
    marks.push({ id: 'hsm', icon: 'chip', label: 'HSM', title: where || t('cas.detail.hsmBacked') })
  }
  if (holdsNoKey(ca)) {
    const expected = needsKeyImport(ca)
    marks.push({
      id: 'nokey', icon: 'key', tone: expected ? 'warn' : undefined,
      label: t(expected ? 'cas.certificateOnly' : 'cas.noPrivateKey'),
      title: t(expected ? 'cas.certificateOnlyBanner' : 'cas.noPrivateKeyBanner'),
    })
  }
  if (ca.revoked_in_chain && !ca.revoked) {
    marks.push({ id: 'chain', icon: 'warning', tone: 'bad', label: t('cas.chainRevoked'), title: t('cas.chainRevokedBanner') })
  }
  if (ca.cross_certificate_count > 0) {
    marks.push({ id: 'cross', icon: 'link', cross: true, label: t('crossCerts.badge', { count: ca.cross_certificate_count }) })
  }
  if (ca.post_quantum || isPostQuantum(ca.key_type)) {
    marks.push({ id: 'pq', icon: 'key', label: t('common.postQuantum'), title: t('common.postQuantumHint') })
  }
  if (orphan) marks.push({ id: 'orphan', icon: 'link', tone: 'warn', label: t('cas.tree.orphan') })
  return marks
}


/** Why this authority cannot issue now, or '' (the mockup's `reason`, on the product's real states). */
export function issueBlockReason(ca, t) {
  if (!ca) return ''
  if (ca.pending || ca.status === 'Pending') return t('cas.side.blocked.pending')
  if (ca.revoked || ca.status === 'Revoked') return t('cas.side.blocked.revoked')
  if (ca.revoked_in_chain) return t('cas.side.blocked.chainRevoked')
  if (ca.status === 'Expired' || (ca.valid_to && Date.parse(ca.valid_to) < Date.now())) return t('cas.side.blocked.expired')
  if (ca.offline) return t('cas.side.blocked.offline')
  if (!ca.has_private_key && !ca.uses_hsm) return t('cas.side.blocked.noKey')
  return ''
}
