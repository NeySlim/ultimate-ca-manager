/**
 * The column contract of the lists and their layout (COLONNES-SPEC L3 to L7, R1, R2), as pure functions:
 * DataTable measures the natural widths, these decide the widths, the absorbing column and the folds.
 */

export const KINDS = ['entity', 'text', 'fit', 'number']
// Hard floors (the mockup's 200, 250 from 1800 px, and 96, 64), then the comfort a name or a text keeps while a column can fold
export const BOUNDS = { entityMin: 200, entityMinWide: 250, textMin: 96, growMin: 64, nameComfort: 280, textComfort: 160 }
// The narrowest a name's own text gives way to beside its marks (its key, its pair, its badges)
export const NAME_TEXT_FLOOR = 120

/** A column's nature; a page not yet migrated is read from its flags (entity, fit, grow, a whole text in title). */
export function columnKind(col) {
  if (col.kind) return col.kind
  if (col.entity) return 'entity'
  if (col.fit) return 'fit'
  return col.grow || col.title ? 'text' : 'fit'
}

/** 1 never folds, 4 folds first; the name and a column marked `fold: false` are 1, a migrated column says its own. */
export function columnPriority(col) {
  if (col.priority !== undefined) return col.priority
  if (col.kind === 'entity' || col.entity || col.fold === false) return 1
  return undefined
}

const declared = (c) => c.kind !== undefined || c.priority !== undefined

/** Declaration errors: a list declares the contract on every column (the name aside) or on none (the old flags). */
export function columnErrors(columns) {
  const errors = []
  const migrated = columns.some((c) => declared(c) && columnKind(c) !== 'entity')
  let grows = 0
  for (const c of columns) {
    const kind = columnKind(c)
    if (!KINDS.includes(kind)) errors.push(`${c.id}: unknown kind ${kind}`)
    else if (migrated && !declared(c) && kind !== 'entity') errors.push(`${c.id}: no kind nor priority`)
    else if (c.kind && kind !== 'entity' && c.priority === undefined) errors.push(`${c.id}: no priority`)
    else if (c.priority !== undefined && ![1, 2, 3, 4].includes(c.priority)) errors.push(`${c.id}: priority ${c.priority} out of 1 to 4`)
    else if (c.grow && (kind === 'fit' || kind === 'number')) errors.push(`${c.id}: a ${kind} column never grows`)
    else if (c.grow && ++grows > 1) errors.push(`${c.id}: a second growing column`)
  }
  return errors
}

export function checkColumns(columns) {
  const errors = columnErrors(columns)
  if (errors.length) throw new Error(`DataTable columns: ${errors.join('; ')}`)
}

/**
 * The columns that may fold, first to go first: priority 4, then 3, then 2, right to left at equal priority
 * (a page not yet migrated: its `fold` rank, higher first, else from the right). The name, priority 1 and the
 * sorted column never fold.
 */
export function foldOrder(columns, sortKey) {
  return columns
    .map((c, i) => ({ c, p: columnPriority(c), rank: c.priority !== undefined ? i : (c.fold ?? i) }))
    .filter(({ c, p }) => columnKind(c) !== 'entity' && p !== 1 && !(sortKey && c.sort === sortKey))
    .sort((a, b) => (b.p ?? 4) - (a.p ?? 4) || b.rank - a.rank)
    .map(({ c }) => c.id)
}

/**
 * One state of the list (these columns shown) at one level of floors, the need first (R1, R2): every column starts at
 * its natural width, no ceiling; short of room the growing text gives way down to its floor, then the name and the
 * texts together, in proportion to what each has above its comfort floor; at the 'hard' level, then above its hard floor.
 */
function share(shown, measures, room, level, wide, fixed = {}) {
  // A column set by hand does not absorb while another can: the growing one, else the name
  const pick = (list) => (list.find((c) => c.grow) || list.find((c) => columnKind(c) === 'entity'))?.id
  const absorber = pick(shown.filter((c) => !fixed[c.id])) ?? pick(shown) ?? null
  const span = {}
  for (const c of shown) {
    const { natural = 0, header = 0, floor = 0 } = measures[c.id] || {}
    const kind = columnKind(c)
    let need = natural
    let hard = natural
    let comfort = natural
    if (kind === 'entity') {
      hard = Math.max(wide ? BOUNDS.entityMinWide : BOUNDS.entityMin, header, floor)
      need = Math.max(natural, hard)
      comfort = Math.max(hard, Math.min(need, BOUNDS.nameComfort))
    } else if (kind === 'text') {
      // A text never grows to reach a floor: a short one keeps its own width
      hard = Math.min(natural, Math.max(c.id === absorber ? BOUNDS.growMin : BOUNDS.textMin, header))
      comfort = c.id === absorber ? hard : Math.max(hard, Math.min(natural, BOUNDS.textComfort))
    }
    span[c.id] = { natural, need, hard, comfort, kind }
    // A width set by hand is a fixed need, never under the column's hard floor (C2)
    if (fixed[c.id]) {
      const w = Math.max(fixed[c.id], hard)
      span[c.id] = { natural, need: w, hard: w, comfort: w, kind, fixed: w }
    }
  }
  const widths = Object.fromEntries(shown.map((c) => [c.id, span[c.id].need]))
  let over = Object.values(widths).reduce((a, b) => a + b, 0) - room
  const growText = shown.find((c) => c.id === absorber && span[c.id].kind === 'text')
  if (over > 0 && growText) {
    const take = Math.min(over, widths[growText.id] - span[growText.id].hard)
    widths[growText.id] -= take
    over -= take
  }
  const yielding = shown.filter((c) => c !== growText && ['entity', 'text'].includes(span[c.id].kind))
  // Each column gives in proportion to what it has above the floor of this round
  for (const floor of level === 'hard' ? ['comfort', 'hard'] : ['comfort']) {
    if (over <= 0) break
    const above = yielding.map((c) => [c.id, Math.max(0, widths[c.id] - span[c.id][floor])])
    const total = above.reduce((s, [, a]) => s + a, 0)
    const take = Math.min(over, total)
    for (const [id, a] of above) if (total > 0) widths[id] -= (take * a) / total
    over -= take
  }
  // The room left goes to the absorbing column (CSS gives it the rest of the table)
  if (over < 0 && absorber) widths[absorber] -= over
  // A ceiling where a free text is under its natural width, a minimum where it is over; the growing text needs neither
  const caps = {}
  const held = {}
  for (const c of shown) {
    const { natural, kind, fixed: w } = span[c.id]
    if (w && c.id === absorber) {
      if (kind === 'entity' || kind === 'text') caps[c.id] = { min: w }
      continue
    }
    if (w) {
      held[c.id] = w
      if (kind === 'entity' || kind === 'text') caps[c.id] = { min: w, max: w }
      continue
    }
    if ((kind !== 'entity' && kind !== 'text') || (c.id === absorber && kind === 'text')) continue
    if (widths[c.id] < natural - 0.01) caps[c.id] = { max: widths[c.id] }
    else if (widths[c.id] > natural + 0.01 && c.id !== absorber) caps[c.id] = { min: widths[c.id] }
  }
  return { fits: over <= 0.5, widths, caps, absorber, fixed: held }
}

/**
 * The layout of a list in `room` px (its region less the checkbox and the actions), from each column's measures
 * ({ natural, header, floor }): the fewest folds, in foldOrder, with which the columns fit. No column of priority 1
 * or 2 goes under its comfort floor while a column of priority 3 or 4 can still fold (R2).
 * `fixed`: the widths set by hand ({ id: px }).
 * @returns {{ folded: string[], widths: Record<string, number>, caps: Record<string, {min?, max?}>, absorber: string|null,
 *   fixed: Record<string, number>, fits: boolean }}  `fixed`: the widths set by hand this layout holds
 */
export function layoutColumns(columns, measures, room, { sortKey, wide = false, fixed = {} } = {}) {
  const order = foldOrder(columns, sortKey)
  const run = (set) => {
    for (let k = 0; ; k += 1) {
      const folded = order.slice(0, k)
      const next = columns.find((c) => c.id === order[k])
      const level = next && (columnPriority(next) ?? 4) > 2 ? 'comfort' : 'hard'
      const out = share(columns.filter((c) => !folded.includes(c.id)), measures, room, level, wide, set)
      if (out.fits || k >= order.length) return { folded, ...out }
    }
  }
  // Widths set by hand hold while the columns fit, other columns folding first; when only folding a column set by
  // hand would make room, the widths are ignored for this render (C2)
  const set = Object.fromEntries(Object.entries(fixed || {}).filter(([id, w]) => w > 0 && columns.some((c) => c.id === id)))
  const plain = run({})
  if (Object.keys(set).length) {
    const out = run(set)
    if (out.fits && out.folded.every((id) => !set[id] || plain.folded.includes(id))) return out
  }
  return plain
}

// A handle's bounds and steps (C2): 64 to 640 px, by 16, by 64 with Shift
export const RESIZE = { min: 64, max: 640, step: 16, bigStep: 64 }

/**
 * The narrowest and widest a handle sets a column: the hard floor of its kind (a name 200, 250 on a wide window,
 * a text 96 or its header, the growing one 64; a fitted column its content), 640 unless its content is wider.
 */
export function columnBounds(col, measure, { wide = false, absorber = false } = {}) {
  if (!measure) return { min: RESIZE.min, max: RESIZE.max }
  const { natural = 0, header = 0, floor = 0 } = measure
  const kind = columnKind(col)
  let min = natural || RESIZE.min
  if (kind === 'entity') min = Math.max(wide ? BOUNDS.entityMinWide : BOUNDS.entityMin, header, floor)
  else if (kind === 'text') min = Math.min(natural || Infinity, Math.max(absorber ? BOUNDS.growMin : BOUNDS.textMin, header))
  return { min: Math.ceil(min), max: Math.max(RESIZE.max, Math.ceil(natural)) }
}
