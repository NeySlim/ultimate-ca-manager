/** What a list's headers say of its column contract, read from the DOM. */

const heads = (root) => [...root.querySelectorAll('thead th')]

/** The sort keys the headers offer. */
export const sortKeys = (root) => heads(root).flatMap((th) => [...th.querySelectorAll(':scope > button[data-sort]')].map((b) => b.dataset.sort))

/** The sorted header, its label and direction: one, and one only. */
export const sortedHeaders = (root) => heads(root).filter((th) => /^(a|de)scending$/.test(th.getAttribute('aria-sort') || ''))
  .map((th) => [th.textContent, th.getAttribute('aria-sort')])

/** The column that takes the room left: the one data header without `fit`. */
export const absorbing = (root) => heads(root).filter((th) => !th.classList.contains('fit') && !th.querySelector('input, .sr-only')).map((th) => th.textContent)

/** The number columns, at the right. */
export const numberHeads = (root) => heads(root).filter((th) => th.classList.contains('num')).map((th) => th.textContent)

/** The facts of a phone record, each in its words. */
export const recordFacts = (record) => [...record.querySelectorAll('.row-meta > span')].map((s) => s.textContent)
