/** Hierarchy card: bounded whatever the installation holds, the active trees first. */
import { describe, it, expect } from 'vitest'
import { HIERARCHY_LIMIT, boundedTree, buildTree } from '../overviewHierarchy'

const ca = (id, parent, name = `CA ${id}`) => ({ id, refid: `r${id}`, descr: name, parent_id: parent ?? null })
const listed = (tree) => {
  const walk = (node) => [node.id, ...(tree.shown.get(node.id) || []).flatMap(walk)]
  return tree.roots.flatMap(walk)
}

describe('bounded tree', () => {
  it('never lists more than the limit: 139 authorities give 10 lines', () => {
    // 45 roots, each with an issuing CA, and 49 more leaves under the first issuing CA
    const cas = []
    for (let i = 1; i <= 45; i += 1) cas.push(ca(i), ca(100 + i, i))
    for (let i = 1; i <= 49; i += 1) cas.push(ca(200 + i, 101))
    expect(cas).toHaveLength(139)
    const tree = boundedTree(cas, new Map())
    expect(listed(tree)).toHaveLength(HIERARCHY_LIMIT)
    expect(tree.listed).toBe(HIERARCHY_LIMIT)
    expect(tree.rootCount).toBe(45)
    expect(new Set(listed(tree)).size).toBe(HIERARCHY_LIMIT)
  })

  it('shows a small hierarchy whole', () => {
    const cas = [ca(1), ca(2, 1), ca(3, 1), ca(4, 2), ca(5), ca(6, 5)]
    const tree = boundedTree(cas, new Map())
    expect(listed(tree).sort()).toEqual([1, 2, 3, 4, 5, 6])
    expect(tree.listed).toBe(6)
  })

  it('starts with the tree that issued most, then the largest', () => {
    const cas = [ca(1, null, 'Quiet'), ca(2, 1), ca(3, 1), ca(10, null, 'Busy'), ca(11, 10), ca(20, null, 'Alone')]
    const tree = boundedTree(cas, new Map([['r11', 7]]))
    expect(tree.roots.map((r) => r.descr)).toEqual(['Busy', 'Quiet', 'Alone'])
  })

  it('with several roots shows more than one tree, then spends what is left on the first', () => {
    const cas = [ca(1), ca(50)]
    for (let i = 2; i <= 20; i += 1) cas.push(ca(i, 1))
    const tree = boundedTree(cas, new Map())
    expect(tree.roots.map((r) => r.id)).toEqual([1, 50])
    expect(tree.shown.get(1)).toHaveLength(8)
    expect(tree.kids.get(1).length - tree.shown.get(1).length).toBe(11)
  })

  it('a single tree may take every line', () => {
    const cas = [ca(1)]
    for (let i = 2; i <= 30; i += 1) cas.push(ca(i, 1))
    expect(boundedTree(cas, null).shown.get(1)).toHaveLength(HIERARCHY_LIMIT - 1)
  })

  it('a CA whose parent is not listed is a root', () => {
    expect(buildTree([ca(3, 99)]).roots.map((r) => r.id)).toEqual([3])
  })
})
