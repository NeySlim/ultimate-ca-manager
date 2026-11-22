/**
 * The column contract and the layout of a list (COLONNES-SPEC L3 to L7, R2), as pure functions: what each
 * column declares (kind, grow, priority, sort), the order in which the columns fold, and the widths a region
 * gives them from their natural widths. No DOM: DataTable measures, these decide.
 */
import { describe, it, expect } from 'vitest'
import { columnKind, columnPriority, columnErrors, checkColumns, foldOrder, layoutColumns, columnBounds, BOUNDS, RESIZE } from '../columnShare'

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

describe('the layout of the columns: the need first (R1, R2)', () => {
  // A name, a growing description, a state, an issuer (text), an owner (text), a source, an expiry: natural widths in px
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
  const near = (out, expected) => Object.entries(expected).forEach(([id, w]) => expect(out.widths[id], id).toBeCloseTo(w, 1))

  it('all fits: every column gets its need, the growing one the rest, no ceiling anywhere', () => {
    const out = layoutColumns(columns, measures, 2000)
    expect(out.folded).toEqual([])
    expect(out.absorber).toBe('description')
    expect(out.widths).toMatchObject({ name: 300, status: 80, ca: 240, owner: 150, source: 70, expiry: 130, description: 1030 })
    expect(out.caps).toEqual({})
  })

  it('a long name or text is never bounded while the sum fits, a short text keeps its own width', () => {
    const out = layoutColumns(columns, { ...measures, name: { natural: 520 }, ca: { natural: 410 }, owner: { natural: 40 } }, 3000)
    expect(out.widths).toMatchObject({ name: 520, ca: 410, owner: 40 })
    expect(out.caps).toEqual({})
    expect(BOUNDS).not.toHaveProperty('entityMax')
    expect(BOUNDS).not.toHaveProperty('textMax')
  })

  it('short of room, the growing text gives way first, down to its floor', () => {
    // 1370 needed in 1200: the description gives 170
    const out = layoutColumns(columns, measures, 1200)
    expect(out.folded).toEqual([])
    expect(out.widths.description).toBe(230)
    expect(out.caps).toEqual({})
  })

  it('then the name and the texts give way together, in proportion to what each has above its comfort floor', () => {
    // Description at its comfort, 160: 1130 needed in 1100. Above comfort: the name 20 (280), the issuer 80 (160), the owner none (150 < 160)
    const out = layoutColumns(columns, measures, 1100)
    expect(out.folded).toEqual([])
    near(out, { description: 160, name: 294, ca: 216, owner: 150 })
    expect(out.caps.name.max).toBeCloseTo(294, 1)
    expect(out.caps.ca.max).toBeCloseTo(216, 1)
    expect(out.caps.owner).toBeUndefined()
  })

  it('the growing text keeps its comfort while a column of priority 3 or 4 can fold: rather than 64 px, it folds (R8)', () => {
    // At comfort the columns need 1030 in 1000: the description (priority 4) folds, the name takes the room left
    const out = layoutColumns(columns, measures, 1000)
    expect(out.folded).toEqual(['description'])
    expect(out.absorber).toBe('name')
    near(out, { name: 330, ca: 240, owner: 150 })
    // A growing text of priority 2 stays: the columns of priority 3 fold first, then it goes down to 64 before the name
    const kept = columns.map((c) => (c.id === 'description' ? { ...c, priority: 2 } : c))
    const tight = layoutColumns(kept, measures, 1000)
    expect(tight.folded).toEqual(['source'])
    near(tight, { description: 160, name: 288, ca: 192 })
    // Only priority 2 left to fold: the growing text goes first, down to its hard floor
    const hard = layoutColumns(kept, measures, 800)
    expect(hard.folded).toEqual(['source', 'owner'])
    near(hard, { description: 64, name: 297.2, ca: 228.8 })
  })

  it('a short growing text never grows to reach its comfort: under 160 px of need it keeps its need', () => {
    const short = { ...measures, description: { natural: 120, header: 50 } }
    expect(layoutColumns(columns, short, 1060).folded).toEqual([])
    expect(layoutColumns(columns, short, 1080).widths.description).toBe(120)
    expect(layoutColumns(columns, short, 980).folded).toEqual(['description'])
  })

  it('rather than go under comfort, a column of priority 4 folds, then those of priority 3, right to left', () => {
    // At comfort the columns need 934: in 900 the description folds and the name absorbs
    let out = layoutColumns(columns, measures, 900)
    expect(out.folded).toEqual(['description'])
    expect(out.absorber).toBe('name')
    near(out, { name: 286, ca: 184 })
    out = layoutColumns(columns, measures, 800)
    expect(out.folded).toEqual(['description', 'source'])
    near(out, { name: 280, ca: 160 })
    // Each fold computes the widths again from the needs: the owner gone, the name and the issuer get room back
    out = layoutColumns(columns, measures, 700)
    expect(out.folded).toEqual(['description', 'source', 'owner'])
    near(out, { name: 290, ca: 200 })
  })

  it('under comfort only once nothing but priority 2 is left to fold, down to the hard floors, then priority 2 folds', () => {
    // 650 at comfort in 600: the expiry (priority 2) stays, the name and the issuer share the last 50 above 200 and 96
    let out = layoutColumns(columns, measures, 600)
    expect(out.folded).toEqual(['description', 'source', 'owner'])
    near(out, { name: 252.22, ca: 137.78 })
    expect(sum(out.widths)).toBeCloseTo(600, 1)
    // 506 at the hard floors in 480: the expiry folds, the rightmost priority 2
    out = layoutColumns(columns, measures, 480)
    expect(out.folded).toEqual(['description', 'source', 'owner', 'expiry'])
    near(out, { name: 257.78, ca: 142.22 })
  })

  it('never folds the sorted column: the next one goes in its place', () => {
    const out = layoutColumns(columns, measures, 480, { sortKey: 'days' })
    expect(out.folded).toEqual(['description', 'source', 'owner', 'ca'])
    expect(out.widths).toMatchObject({ expiry: 130, name: 270 })
  })

  it('keeps a header whole and a name\'s marks beside it: their floors', () => {
    const two = [col('name', { kind: 'entity', priority: 1 }), col('owner', { kind: 'text', priority: 2 })]
    expect(layoutColumns(two, { name: { natural: 300 }, owner: { natural: 150, header: 130 } }, 330).widths).toEqual({ name: 200, owner: 130 })
    // A name whose marks ask 220
    const marked = { name: { natural: 300, floor: 220 }, owner: { natural: 150, header: 130 } }
    expect(layoutColumns(two, marked, 350)).toMatchObject({ folded: [], widths: { name: 220, owner: 130 } })
    expect(layoutColumns(two, marked, 340).folded).toEqual(['owner'])
  })

  it('a name 250 px at least on a window of 1800 px and more', () => {
    const two = [col('name', { kind: 'entity', priority: 1 }), col('owner', { kind: 'text', priority: 2 })]
    const m = { name: { natural: 300 }, owner: { natural: 150, header: 130 } }
    expect(layoutColumns(two, m, 350).folded).toEqual([])
    const out = layoutColumns(two, m, 350, { wide: true })
    expect(out.folded).toEqual(['owner'])
    // Alone, the name takes the whole room
    expect(out.widths.name).toBe(350)
  })

  it('a list whose name grows (the authorities): the name absorbs, gives way down to comfort, then the columns fold', () => {
    const cas = [col('name', { kind: 'entity', priority: 1, grow: true }), col('type', { kind: 'fit', priority: 3 }), col('certs', { kind: 'number', priority: 3 })]
    const m = { name: { natural: 500 }, type: { natural: 100 }, certs: { natural: 90 } }
    expect(layoutColumns(cas, m, 1000)).toMatchObject({ folded: [], absorber: 'name', caps: {} })
    expect(layoutColumns(cas, m, 600)).toMatchObject({ folded: [], caps: { name: { max: 410 } } })
    expect(layoutColumns(cas, m, 350)).toMatchObject({ folded: ['certs', 'type'], caps: { name: { max: 350 } } })
  })

  it('when nothing more can fold, every column stays at its floor', () => {
    const out = layoutColumns(columns, measures, 100)
    expect(out.folded).toEqual(['description', 'source', 'owner', 'expiry', 'ca'])
    expect(out.widths).toMatchObject({ name: 200 })
  })
})

describe('a width set by hand (C2): a fixed need, never at the cost of the folds nor of the room', () => {
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

  it('keeps the width while it fits: the column neither gives way nor grows, the absorbing one takes the rest', () => {
    const out = layoutColumns(columns, measures, 2000, { fixed: { ca: 400, source: 120 } })
    expect(out.folded).toEqual([])
    expect(out.fixed).toEqual({ ca: 400, source: 120 })
    expect(out.widths).toMatchObject({ ca: 400, source: 120, name: 300, description: 820 })
    expect(out.caps.ca).toEqual({ min: 400, max: 400 })
    // Short of room the description goes to its comfort, then the name gives way, the issuer set by hand does not
    const tight = layoutColumns(columns, measures, 1280, { fixed: { ca: 400 } })
    expect(tight.folded).toEqual([])
    expect(tight.widths.ca).toBe(400)
    expect(tight.widths.description).toBe(160)
    expect(tight.widths.name).toBeCloseTo(290, 1)
  })

  it('a widened column does not stop the folds: they come first, in their declared order', () => {
    const without = layoutColumns(columns, measures, 900)
    const widened = layoutColumns(columns, measures, 900, { fixed: { ca: 420 } })
    expect(without.folded).toEqual(['description'])
    expect(widened.folded).toEqual(foldOrder(columns).slice(0, widened.folded.length))
    expect(widened.folded.length).toBeGreaterThan(without.folded.length)
    expect(widened.fixed).toEqual({ ca: 420 })
    expect(Object.values(widened.widths).reduce((a, b) => a + b, 0)).toBeLessThanOrEqual(900.5)
  })

  it('when only folding the column set by hand would make room, its width is ignored for this render', () => {
    const out = layoutColumns(columns, measures, 560, { fixed: { ca: 600 } })
    expect(out.fixed).toEqual({})
    expect(out).toMatchObject({ folded: layoutColumns(columns, measures, 560).folded, widths: layoutColumns(columns, measures, 560).widths })
  })

  it('never below a hard floor: a name at 200, a fitted column at its content', () => {
    const out = layoutColumns(columns, measures, 2000, { fixed: { name: 120, status: 30 } })
    expect(out.fixed).toMatchObject({ name: 200, status: 80 })
  })

  it('a growing column set by hand hands the rest of the room to the name', () => {
    const out = layoutColumns(columns, measures, 2000, { fixed: { description: 300 } })
    expect(out.absorber).toBe('name')
    expect(out.widths.description).toBe(300)
    expect(out.widths.name).toBe(2000 - 300 - 80 - 240 - 150 - 70 - 130)
  })

  it('a handle\'s bounds: the hard floors of the spec, 640 at most unless the content is wider', () => {
    expect(RESIZE).toEqual({ min: 64, max: 640, step: 16, bigStep: 64 })
    expect(columnBounds(col('n', { kind: 'entity' }), { natural: 300, header: 60 })).toEqual({ min: 200, max: 640 })
    expect(columnBounds(col('n', { kind: 'entity' }), { natural: 900, header: 60 }, { wide: true })).toEqual({ min: 250, max: 900 })
    expect(columnBounds(col('t', { kind: 'text' }), { natural: 300, header: 120 })).toEqual({ min: 120, max: 640 })
    expect(columnBounds(col('t', { kind: 'text' }), { natural: 50, header: 40 })).toEqual({ min: 50, max: 640 })
    expect(columnBounds(col('d', { kind: 'text', grow: true }), { natural: 300, header: 40 }, { absorber: true })).toEqual({ min: 64, max: 640 })
    expect(columnBounds(col('f', { kind: 'fit' }), { natural: 130 })).toEqual({ min: 130, max: 640 })
    expect(columnBounds(col('f', { kind: 'fit' }))).toEqual({ min: 64, max: 640 })
  })
})

describe('the data of the maintainer\'s capture (Certificates, long names, empty descriptions)', () => {
  // Natural widths read on the capture: 14 px of side padding at 1600 and 1920, 10 px at 1000 and beside the dock
  const certs = [
    col('name', { kind: 'entity', priority: 1 }),
    col('description', { kind: 'text', priority: 4, grow: true }),
    col('status', { kind: 'fit', priority: 1 }),
    col('ca', { kind: 'text', priority: 2 }),
    col('source', { kind: 'fit', priority: 3 }),
    col('expiry', { kind: 'fit', priority: 2, sort: 'days' }),
    col('key', { kind: 'fit', priority: 3, sort: 'key' }),
  ]
  const wide = { name: 427, description: 110, status: 81, ca: 301, source: 106, expiry: 162, key: 143 }
  const narrow = { name: 419, description: 102, status: 73, ca: 293, source: 98, expiry: 150, key: 135 }
  const of = (n) => Object.fromEntries(Object.entries(n).map(([id, w]) => [id, { natural: w, header: id === 'description' ? w : 60 }]))
  // The region less the checkbox (40) and the actions (83, or 47 with the Export hidden)
  const sorted = { sortKey: 'days' }

  it('at 1600 and 1920 nothing is cut: the name and the issuer whole, the empty description takes the rest', () => {
    let out = layoutColumns(certs, of(wide), 1550 - 40 - 83, sorted)
    expect(out).toMatchObject({ folded: [], caps: {}, widths: { name: 427, ca: 301, description: 207 } })
    out = layoutColumns(certs, of(wide), 1850 - 40 - 83, sorted)
    expect(out).toMatchObject({ folded: [], caps: {}, widths: { name: 427, ca: 301, description: 507 } })
  })

  it('at 1406 beside the dock: the name about 296, the issuer about 176, the source kept', () => {
    const out = layoutColumns(certs, of(narrow), 880 - 40 - 47, sorted)
    expect(out.folded).toEqual(['description', 'key'])
    expect(out.widths.name).toBeCloseTo(296, 0)
    expect(out.widths.ca).toBeCloseTo(176, 0)
    expect(out.widths).toHaveProperty('source', 98)
  })

  it('at 1000: the key algorithm folds, the name about 336, the issuer about 214', () => {
    const out = layoutColumns(certs, of({ ...narrow, expiry: 154 }), 962 - 40 - 47, sorted)
    expect(out.folded).toEqual(['description', 'key'])
    expect(out.widths.name).toBeCloseTo(336, 0)
    expect(out.widths.ca).toBeCloseTo(214, 0)
  })
})

describe('the two invariants of the layout, on random lists', () => {
  // A small deterministic generator: the same lists at every run
  let seed = 7
  const rand = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647 }
  const pick = (a) => a[Math.floor(rand() * a.length)]
  const comfort = (c, m) => (c.kind === 'entity' ? Math.min(m.natural, BOUNDS.nameComfort) : Math.min(m.natural, BOUNDS.textComfort))

  it('no cell is cut while another column has 16 px more than it needs; no priority 1 or 2 under comfort beside a 3 or a 4', () => {
    for (let n = 0; n < 400; n += 1) {
      const cols = [col('name', { kind: 'entity', priority: 1 })]
      const m = { name: { natural: 200 + Math.round(rand() * 400), header: 60 } }
      const count = 2 + Math.floor(rand() * 6)
      for (let i = 0; i < count; i += 1) {
        const kind = pick(['text', 'text', 'fit', 'number'])
        const id = `c${i}`
        cols.push(col(id, { kind, priority: pick([1, 2, 2, 3, 3, 4]), ...(kind === 'text' && i === 0 && rand() < 0.5 ? { grow: true } : {}) }))
        m[id] = { natural: 40 + Math.round(rand() * (kind === 'text' ? 360 : 140)), header: 40 }
      }
      const room = 300 + Math.round(rand() * 1500)
      const out = layoutColumns(cols, m, room)
      const shown = cols.filter((c) => !out.folded.includes(c.id))
      const need = (c) => Math.max(m[c.id].natural, c.kind === 'entity' ? BOUNDS.entityMin : 0)
      const cut = shown.filter((c) => out.widths[c.id] < need(c) - 0.5)
      const spare = shown.filter((c) => out.widths[c.id] > need(c) + 16 && c.id !== out.absorber)
      if (cut.length) expect(spare.map((c) => c.id), `list ${n}`).toEqual([])
      const under = shown.filter((c) => (c.priority <= 2) && ['entity', 'text'].includes(c.kind) && !c.grow && out.widths[c.id] < comfort(c, m[c.id]) - 0.5)
      const low = shown.filter((c) => c.priority >= 3)
      if (under.length) expect(low.map((c) => c.id), `list ${n}`).toEqual([])
    }
  })
})
