/** The page title, focusable by script only (tabindex -1), as the mockup's main title. */
export function focusTitle() {
  const title = document.querySelector('.lv-head h1')
  if (!title) return
  if (!title.hasAttribute('tabindex')) title.setAttribute('tabindex', '-1')
  title.focus()
}

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
  if (target) target.focus()
  else focusTitle()
}

/**
 * The control a dialog was opened from, given focus back when the dialog closes without
 * an outcome that moves it elsewhere (Escape, Cancel, the close button). `fallback` (an
 * element or a function giving one) stands in when that control left the page (a menu item).
 */
export function rememberFocus(fallback) {
  const origin = typeof document !== 'undefined' ? document.activeElement : null
  return () => requestAnimationFrame(() => {
    const target = origin?.isConnected && origin !== document.body ? origin : (typeof fallback === 'function' ? fallback() : fallback)
    target?.focus?.()
  })
}
