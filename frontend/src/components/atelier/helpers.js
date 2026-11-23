/**
 * Helpers of the Atelier gabarits (not components): skeleton widths, tone icons, dock heights,
 * and the focus moves the mockup makes after an operation.
 */
export const skWidth = (i, base, spread) => `${base + ((i * 37) % spread)}%`

/** A column's skeleton bar: { width } fixed, or { base, spread } varying from row to row. */
export const barOf = (sk, i) => (sk?.base !== undefined ? skWidth(i, sk.base, sk.spread) : sk?.width)

export const TONE_ICONS = { good: 'check', warn: 'clock', bad: 'warning', muted: 'block' }

/** The bottom dock keeps 210 to 450 px, and never more than 60 % of the window height. */
export const heightMax = () => Math.min(450, Math.floor(window.innerHeight * 0.6))
export const heightMin = () => Math.min(210, heightMax())

export const focusMainTitle = () => requestAnimationFrame(() => document.getElementById('main-title')?.focus())

/**
 * Scrolls to a settings section and gives its title the focus without moving the page again.
 * `quiet` (a link landing, no key pressed) keeps the focus without its keyboard outline until the title loses it.
 */
export function jumpTo(id, { quiet = false } = {}) {
  const sec = document.getElementById(`set-sec-${id}`)
  if (!sec) return
  sec.scrollIntoView?.({ block: 'start' })
  const title = document.getElementById(`set-title-${id}`)
  if (!title) return
  if (quiet) {
    title.setAttribute('data-quiet-focus', '')
    title.addEventListener('blur', () => title.removeAttribute('data-quiet-focus'), { once: true })
  }
  title.focus({ preventScroll: true })
}

/** Where the focus goes after a queue operation: the action of the row now at the same place, else the history toggle. */
export function workSpot(ids) {
  return [...document.querySelectorAll('.work-row')].findIndex((li) => ids.map(String).includes(li.dataset.workRow))
}
export function focusWork(index) {
  const list = [...document.querySelectorAll('.work-row')]
  const row = list[Math.min(Math.max(index, 0), list.length - 1)]
  ;(row?.querySelector('.work-action .btn:not(:disabled)') || document.getElementById('work-history-toggle') || document.getElementById('main-title'))?.focus()
}

const COLON_HEX = /^[0-9A-F]{2}(:[0-9A-F]{2})+$/i

// Bytes a line when the room is unknown or wide: 29 characters, a SHA-1 in two lines, a SHA-256 in four
export const HEX_PER_LINE = 10

/**
 * A colon-separated digest in equal lines of at most `room` bytes (10 when unknown): the widest divisor of its
 * length, or lines as even as they can be when no divisor is at least half the room; any other text whole.
 */
export function hexLines(text, room) {
  const value = String(text ?? '')
  if (!COLON_HEX.test(value)) return value
  const bytes = value.split(':')
  const limit = room === undefined || room === null ? HEX_PER_LINE : Math.min(HEX_PER_LINE, Math.max(1, Math.floor(room)))
  let per = bytes.length
  if (per > limit) {
    per = limit
    while (bytes.length % per) per -= 1
    if (per * 2 < limit) per = Math.ceil(bytes.length / Math.ceil(bytes.length / limit))
  }
  const lines = []
  for (let i = 0; i < bytes.length; i += per) lines.push(bytes.slice(i, i + per).join(':') + (i + per < bytes.length ? ':' : ''))
  return lines.join('\n')
}
