/**
 * The column contract and the layout of a list (COLONNES-SPEC L3 to L7, R2), as pure functions: what each
 * column declares (kind, grow, priority, sort), the order in which the columns fold, and the widths a region
 * gives them from their natural widths. No DOM: DataTable measures, these decide.
 */
import { describe, it, expect } from 'vitest'
import { columnKind, columnPriority, columnErrors, checkColumns, foldOrder, layoutColumns, BOUNDS } from '../columnShare'

const col = (id, extra = {}) => ({ id, label: id, cell: () => id, ...extra })

describe('the column contract', () => {
  it('reads the declared kind and priority, and translates the flags of the pages not yet migrated', () => {
    expect(columnKind(col('a', { kind: 'number' }))).toBe('number')
    expect(columnKind(col('n', { entity: true }))).toBe('entity')
    expect(columnKind(col('d', { grow: true }))).toBe('text')
    expect(columnKind(col('i', { title: () => 'x' }))).toBe('text')
    expect(columnKind(col('i', { title: () => 'x', fit: true }))).toBe('fit')
    expect(columnKind(col('s'))).toBe('fit')
    expect(columnPriority(col('n', { entity: true }))).toBe(1)
    expect(columnPriority(col('s', { fold: false }))).toBe(1)
    expect(columnPriority(col('e', { priority: 2 }))).toBe(2)
    expect(columnPriority(col('x', { fold: 4 }))).toBeUndefined()
  })

  it('refuses a column declared by halves, an unknown kind, two growing columns, a growing date', () => {
    const name = col('name', { kind: 'entity' })
    expect(columnErrors([name, col('a', { kind: 'fit', priority: 2 }), col('b', { kind: 'text', priority: 4, grow: true })])).toEqual([])
    expect(columnErrors([name, col('a', { kind: 'fit', priority: 2 }), col('b')])).toEqual(['b: no kind nor priority'])
    expect(columnErrors([name, col('a', { kind: 'fit' })])).toEqual(['a: no priority'])
    expect(columnErrors([name, col('a', { kind: 'date', priority: 2 })])).toEqual(['a: unknown kind date'])
    expect(columnErrors([name, col('a', { kind: 'fit', priority: 5 })])).toEqual(['a: priority 5 out of 1 to 4'])
    expect(columnErrors([name, col('a', { kind: 'text', priority: 4, grow: true }), col('b', { kind: 'text', priority: 4, grow: true })])).toEqual(['b: a second growing column'])
    expect(columnErrors([name, col('a', { kind: 'number', priority: 3, grow: true })])).toEqual(['a: a number column never grows'])
    expect(() => checkColumns([name, col('a', { kind: 'fit' })])).toThrow(/a: no priority/)
    // A page not yet migrated declares neither: its flags are translated
    expect(columnErrors([col('n', { entity: true }), col('a', { fit: true }), col('b', { fold: 3 })])).toEqual([])
  })
})

describe('the fold order', () => {
  const columns = [
    col('name', { kind: 'entity', priority: 1 }),
    col('description', { kind: 'text', priority: 4, grow: true }),
    col('status', { kind: 'fit', priority: 1 }),
    col('ca', { kind: 'text', priority: 2 }),
    col('source', { kind: 'fit', priority: 3 }),
    col('expiry', { kind: 'fit', priority: 2, sort: 'days' }),
    col('key', { kind: 'fit', priority: 3, sort: 'key' }),
  ]

  it('folds priority 4, then 3, then 2, right to left at equal priority; never the name nor priority 1', () => {
    expect(foldOrder(columns)).toEqual(['description', 'key', 'source', 'expiry', 'ca'])
  })

  it('spares the sorted column', () => {
    expect(foldOrder(columns, 'key')).toEqual(['description', 'source', 'expiry', 'ca'])
    expect(foldOrder(columns, 'days')).toEqual(['description', 'key', 'source', 'ca'])
  })

  it('a page not yet migrated folds by its fold rank, else from the right', () => {
    expect(foldOrder([col('n', { entity: true }), col('a', { fold: 5 }), col('s', { fold: false }), col('b', { fold: 7 }), col('c')])).toEqual(['b', 'a', 'c'])
    expect(foldOrder([col('n', { entity: true }), col('a'), col('b'), col('c')])).toEqual(['c', 'b', 'a'])
  })
})

describe('the layout of the columns', () => {
  // A name, a growing description, a state, an issuer (text), a source, an expiry, a key: natural widths in px
  const columns = [
    col('name', { kind: 'entity', priority: 1 }),
    col('description', { kind: 'text', priority: 4, grow: true }),
    col('status', { kind: 'fit', priority: 1 }),
    col('ca', { kind: 'text', priority: 2 }),
    col('owner', { kind: 'text', priority: 3 }),
    col('source', { kind: 'fit', priority: 3 }),
    col('expiry', { kind: 'fit', priority: 2, sort: 'days' }),
  ]
  const natural = { name: 300, description: 400, status: 80, ca: 240, owner: 150, source: 70, expiry: 130 }
  const measures = Object.fromEntries(Object.entries(natural).map(([id, n]) => [id, { natural: n, header: 50 }]))
  const sum = (o) => Object.values(o).reduce((a, b) => a + b, 0)

  it('all fits: the fixed columns at their natural width, free text bounded, the growing one takes the rest', () => {
    const out = layoutColumns(columns, measures, 2000)
    expect(out.folded).toEqual([])
    expect(out.absorber).toBe('description')
    expect(out.widths).toMatchObject({ name: 300, status: 80, ca: 240, owner: 150, source: 70, expiry: 130 })
    // Nothing to bound: no ceiling, the growing column has none either
    expect(out.caps).toEqual({})
  })

  it('bounds the free text that does not grow: a name to 360, a text to [96, 280]', () => {
    const out = layoutColumns(columns, { ...measures, name: { natural: 520 }, ca: { natural: 410 }, owner: { natural: 40 } }, 3000)
    expect(out.caps.name).toEqual({ max: BOUNDS.entityMax })
    expect(out.caps.ca).toEqual({ max: BOUNDS.textMax })
    expect(out.caps.owner).toEqual({ min: BOUNDS.textMin })
  })

  it('short of room, the growing column gives way first, down to its minimum', () => {
    // 300 + 400 + 80 + 240 + 150 + 70 + 130 = 1370; 1200 of room: the description gives 170
    const out = layoutColumns(columns, measures, 1200)
    expect(out.folded).toEqual([])
    expect(out.widths.description).toBe(230)
    expect(out.caps).toEqual({})
  })

  it('then the texts, the least important first, down to 96 each, then the name down to 200', () => {
    // Description at 64: 1034 needed. 1000 of room: the owner (priority 3) gives 34 first
    let out = layoutColumns(columns, measures, 1000)
    expect(out.widths).toMatchObject({ description: 64, owner: 116, ca: 240, name: 300 })
    expect(out.caps).toEqual({ owner: { max: 116 } })
    // 850: the owner at 96, the issuer (priority 2) gives the rest
    out = layoutColumns(columns, measures, 850)
    expect(out.widths).toMatchObject({ description: 64, owner: 96, ca: 110, name: 300 })
    // 760: both texts at 96, the name gives way down to 224
    out = layoutColumns(columns, measures, 760)
    expect(out.folded).toEqual([])
    expect(out.widths).toMatchObject({ owner: 96, ca: 96, name: 224 })
    expect(out.caps.name).toEqual({ max: 224 })
    expect(sum(out.widths)).toBe(760)
  })

  it('then folds by priority, the free text whole again at each fold', () => {
    // At their floors the columns need 200 + 64 + 80 + 96 + 96 + 70 + 130 = 736: 700 folds the description (priority 4)
    let out = layoutColumns(columns, measures, 700)
    expect(out.folded).toEqual(['description'])
    // Without a growing column the name takes the room left; the texts give way before it
    expect(out.absorber).toBe('name')
    expect(out.widths).toMatchObject({ owner: 96, ca: 96, name: 228 })
    // 560: the source and the owner (priority 3, right to left) fold, every width computed again from its natural one
    out = layoutColumns(columns, measures, 560)
    expect(out.folded).toEqual(['description', 'source', 'owner'])
    expect(out.widths).toMatchObject({ ca: 96, name: 254 })
  })

  it('never folds the sorted column: the next one goes in its place', () => {
    const out = layoutColumns(columns, measures, 480, { sortKey: 'days' })
    expect(out.folded).toEqual(['description', 'source', 'owner', 'ca'])
    expect(Object.keys(out.widths)).toContain('expiry')
  })

  it('keeps a header whole: no column narrower than its label', () => {
    const out = layoutColumns(columns, { ...measures, owner: { natural: 150, header: 130 } }, 850)
    expect(out.widths.owner).toBe(130)
  })

  it('keeps a name wider than 200 when its marks ask for it (floor)', () => {
    const out = layoutColumns(columns, { ...measures, name: { natural: 300, floor: 220 } }, 760)
    expect(out.widths.name).toBe(224)
    expect(layoutColumns(columns, { ...measures, name: { natural: 300, floor: 230 } }, 760).folded).toEqual(['description'])
  })

  it('a name 250 px at least on a window of 1800 px and more', () => {
    const out = layoutColumns(columns, measures, 556, { wide: true })
    expect(out.folded).toHaveLength(3)
    expect(out.widths.name).toBe(BOUNDS.entityMinWide)
  })

  it('a list whose name grows (the authorities) shrinks the name first, then folds', () => {
    const cas = [col('name', { kind: 'entity', priority: 1, grow: true }), col('type', { kind: 'fit', priority: 3 }), col('certs', { kind: 'number', priority: 3 })]
    const m = { name: { natural: 500 }, type: { natural: 100 }, certs: { natural: 90 } }
    expect(layoutColumns(cas, m, 1000)).toMatchObject({ folded: [], absorber: 'name', caps: {} })
    expect(layoutColumns(cas, m, 600)).toMatchObject({ folded: [], caps: { name: { max: 410 } } })
    expect(layoutColumns(cas, m, 350)).toMatchObject({ folded: ['certs'], caps: { name: { max: 250 } } })
  })

  it('when nothing more can fold, every column stays at its floor', () => {
    const out = layoutColumns(columns, measures, 100)
    expect(out.folded).toEqual(['description', 'source', 'owner', 'expiry', 'ca'])
    expect(out.widths).toMatchObject({ name: 200 })
  })
})
