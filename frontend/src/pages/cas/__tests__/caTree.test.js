/**
 * CAs page data: tab counters, the tree a view and a search leave, the layout of the roots
 * of a large installation, the state of an authority, when chain repair shows unasked.
 */
import { describe, it, expect } from 'vitest'
import { buildForest, layoutRoots, viewCounts, filterCAs, caState, chainNeedsAttention, nestedForest, IDLE_BUNDLE_MIN } from '../caTree'
import { ca, smallHierarchy, largeInstallation } from './caFixtures'

const ids = (list) => list.map((c) => c.id)

describe('viewCounts', () => {
  it('counts all, roots, intermediates and expired, and the other states only when there are some', () => {
    expect(viewCounts(smallHierarchy())).toEqual([
      { id: '', count: 6 }, { id: 'roots', count: 2 }, { id: 'intermediates', count: 4 },
      { id: 'expired', count: 1 }, { id: 'offline', count: 1 },
    ])
    expect(viewCounts([ca(1), ca(2, { status: 'Revoked' }), ca(3, { status: 'Pending' })]).map((v) => v.id))
      .toEqual(['', 'roots', 'intermediates', 'expired', 'revoked', 'pending'])
  })
})

describe('buildForest', () => {
  it('puts each authority under its parent and keeps the level of each', () => {
    const forest = buildForest(smallHierarchy())
    expect(ids(forest.roots)).toEqual([1, 6])
    expect(ids(forest.kids.get(1))).toEqual([5, 2])
    expect(ids(forest.kids.get(2))).toEqual([3, 4])
    expect(forest.levelOf.get(3)).toBe(3)
    expect(forest.parentOf.get(3)).toBe(2)
  })

  it('keeps the ancestors of what a search finds and drops the rest', () => {
    const forest = buildForest(smallHierarchy(), { query: 'internal' })
    expect(ids(forest.roots)).toEqual([1])
    expect(ids(forest.kids.get(1))).toEqual([2])
    expect(ids(forest.kids.get(2))).toEqual([3])
    // The counters never follow the filter
    expect(forest.allKids.get(2)).toHaveLength(2)
  })

  it('searches the name, the common name and the subject', () => {
    const list = [ca(1, { name: 'A', common_name: 'alpha' }), ca(2, { name: 'B', subject: 'CN=x,O=Zeta' }), ca(3, { name: 'C' })]
    expect(ids(filterCAs(list, { query: 'ALPHA' }))).toEqual([1])
    expect(ids(filterCAs(list, { query: 'zeta' }))).toEqual([2])
  })

  it('applies a tab view to the tree', () => {
    const forest = buildForest(smallHierarchy(), { view: 'expired' })
    expect(ids(forest.roots)).toEqual([1])
    expect(ids(forest.kids.get(2))).toEqual([4])
    expect(ids(buildForest(smallHierarchy(), { view: 'roots' }).roots)).toEqual([1, 6])
    expect(buildForest(smallHierarchy(), { view: 'roots' }).kids.size).toBe(0)
  })

  it('lists an intermediate without a known parent as the head of its own subtree', () => {
    const forest = buildForest([ca(1), ca(2, { type: 'intermediate', parent_id: 99 }), ca(3, { type: 'intermediate', parent_id: 2 })])
    expect(ids(forest.roots)).toEqual([1, 2])
    expect([...forest.orphans]).toEqual([2])
    expect(ids(forest.kids.get(2))).toEqual([3])
  })

  it('nests the forest for the views that walk children', () => {
    const [root] = nestedForest(buildForest(smallHierarchy()))
    expect(root.children.map((c) => c.name)).toEqual(['Identities', 'Services'])
    expect(root.children[1].children).toHaveLength(2)
  })
})

describe('layoutRoots', () => {
  it('folds the idle roots of a large installation into one group', () => {
    const cas = largeInstallation()
    const layout = layoutRoots(buildForest(cas))
    expect(ids(layout.branches)).toEqual([1, 2])
    expect(layout.compact).toHaveLength(9)
    expect(layout.idle).toHaveLength(120)
  })

  it('leaves a few idle roots as plain lines', () => {
    const cas = Array.from({ length: IDLE_BUNDLE_MIN - 1 }, (_, i) => ca(i + 1))
    const layout = layoutRoots(buildForest(cas))
    expect(layout.idle).toHaveLength(0)
    expect(layout.compact).toHaveLength(IDLE_BUNDLE_MIN - 1)
  })

  it('shows what a search found instead of folding it', () => {
    const cas = largeInstallation()
    const layout = layoutRoots(buildForest(cas, { query: 'smoke' }), { query: 'smoke' })
    expect(layout.idle).toHaveLength(0)
    expect(layout.compact).toHaveLength(120)
  })

  it('draws a root that a cross-certificate links as a card', () => {
    const layout = layoutRoots(buildForest(largeInstallation()), { linked: new Set([25]) })
    expect(ids(layout.branches)).toEqual([1, 2, 25])
    expect(layout.idle).toHaveLength(119)
  })
})

describe('caState', () => {
  const now = new Date('2026-11-19T00:00:00Z')
  it('reads the state of the server, then how close the end is', () => {
    expect(caState(ca(1, { status: 'Pending' }), now)).toBe('pending')
    expect(caState(ca(1, { status: 'Revoked' }), now)).toBe('revoked')
    expect(caState(ca(1, { status: 'Expired' }), now)).toBe('expired')
    expect(caState(ca(1, { valid_to: '2026-12-01T00:00:00Z' }), now)).toBe('expiring')
    expect(caState(ca(1, { valid_to: '2027-12-01T00:00:00Z' }), now)).toBe('active')
    expect(caState(ca(1, { valid_to: null }), now)).toBe('active')
  })
})

describe('chainNeedsAttention', () => {
  it('is quiet when every chain is linked and nothing runs', () => {
    expect(chainNeedsAttention({ stats: { total_cas: 5, orphan_cas: 0 } }, [], false)).toBe(false)
    expect(chainNeedsAttention(null)).toBe(false)
  })
  it('speaks up for an orphan, a shared key, a finding or a run', () => {
    expect(chainNeedsAttention({ stats: { orphan_cas: 1 } })).toBe(true)
    expect(chainNeedsAttention({ stats: { same_key_distinct_certs: 2 } })).toBe(true)
    expect(chainNeedsAttention({ stats: {} }, [{ kind: 'shadowed_root' }])).toBe(true)
    expect(chainNeedsAttention({ stats: {} }, [], true)).toBe(true)
  })
})
