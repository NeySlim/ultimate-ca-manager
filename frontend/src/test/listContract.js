/**
 * A list's headers as a user meets them (COLONNES-SPEC T1, T4, L7): each data header's label, whether it takes the room
 * left (the one header DataTable does not mark `fit`), whether it is a number, the sort key of its button, its aria-sort.
 */
export function headersOf(container) {
  return [...container.querySelectorAll('thead th')].filter((th) => !th.querySelector('.sr-only, input')).map((th) => ({
    label: (th.querySelector('button') || th).textContent,
    grows: !th.classList.contains('fit'),
    number: th.classList.contains('num'),
    sort: th.querySelector('button[data-sort]')?.getAttribute('data-sort') ?? null,
    aria: th.getAttribute('aria-sort'),
  }))
}

/** The labels of the headers that take the room left: one, by the contract. */
export const absorbers = (container) => headersOf(container).filter((h) => h.grows).map((h) => h.label)

/** The sorted header and its direction: one, by T4. */
export const sortedHeaders = (container) => headersOf(container).filter((h) => /ending$/.test(h.aria || '')).map((h) => [h.label, h.aria])

/** The sort keys the headers offer, in their order (T1). */
export const sortKeys = (container) => headersOf(container).map((h) => h.sort).filter(Boolean)

/** The names of the rows, in their order. */
export const rowNames = (container) => [...container.querySelectorAll('tbody tr .entity-name')].map((n) => n.textContent)

/** The facts of each phone record, as read. */
export const recordFacts = (container) => [...container.querySelectorAll('article.mobile-record')]
  .map((r) => [...r.querySelectorAll('.row-meta > span')].map((s) => s.textContent))
