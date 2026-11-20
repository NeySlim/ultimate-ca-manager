/** Where the focus goes after an operation: the action of the row now at the same place, else the history toggle. */
export function workSpot(root, ids) {
  const rows = [...(root?.querySelectorAll('[data-work-row]') || [])]
  return rows.findIndex((li) => ids.map(String).includes(li.dataset.workRow))
}
export function focusWork(root, index) {
  if (!root) return
  const rows = [...root.querySelectorAll('[data-work-row]')]
  const row = rows[Math.min(Math.max(index, 0), rows.length - 1)]
  const target = row?.querySelector('.wk-action button:not(:disabled)') || root.querySelector('[data-work-history]')
    || document.querySelector('.lv-head h1')
  target?.focus?.()
}
