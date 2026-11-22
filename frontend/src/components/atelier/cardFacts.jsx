/** The facts of a phone record drawn from a list's columns (ListView, COLONNES-SPEC R5). */
import { columnKind } from './columnShare'

const absent = (v) => v === null || v === undefined || v === false || v === '' || v === '—'

/** A value that does not read alone (a date, a number, a yes or no) after its column's label (G9). */
export const labelledFact = (label, value) => <><span className="fact-label">{label}</span> {value}</>

/**
 * The facts of a phone record (R5): the columns of priority 2, then 3, three at most (a list without priorities: its
 * first three); a date, a number or a yes or no (`labelled`, a number column) after its column's label (span.fact-label,
 * adjust.css: muted beside its value, G9); nothing absent.
 */
export function cardFacts(cols, row) {
  const data = cols.filter((c) => columnKind(c) !== 'entity' && c.id !== 'status')
  const migrated = data.some((c) => c.priority !== undefined)
  const picked = migrated
    ? data.map((c, i) => ({ c, i })).filter(({ c }) => c.priority === 2 || c.priority === 3)
      .sort((a, b) => a.c.priority - b.c.priority || a.i - b.i).map(({ c }) => c)
    : data
  return picked.map((c) => [c, c.cell(row)]).filter(([, v]) => !absent(v)).slice(0, 3)
    .map(([c, v]) => (c.labelled || c.kind === 'number' ? labelledFact(c.label, v) : v))
}
