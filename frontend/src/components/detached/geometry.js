/**
 * Geometry of the detached windows: a rect { x, y, w, h } in viewport pixels, always kept inside
 * the visible area, never under the minimum size, cascaded on opening.
 */
export const MIN_W = 360
export const MIN_H = 220
export const STEP = 20
const CASCADE = 28
const ORIGIN = { x: 96, y: 72 }

const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), Math.max(lo, hi))

/** The viewport as the windows see it: above the status bar, which stays reachable under them. */
export const viewport = () => {
  const bar = document.querySelector('.shell-app .statusbar')?.getBoundingClientRect().height || 0
  return { w: window.innerWidth, h: Math.max(0, window.innerHeight - bar) }
}

/** The stage's margin at a viewport width, as the mockup sets it (.stage padding). */
export const stageMargin = (width) => (width >= 1800 ? 34 : width <= 1000 ? 18 : 24)

/** Past 1920 px the page holds 1852 px, centred (adjust.css --page-max): its side margin is what the measure leaves. */
export const PAGE_MAX = 1852
export const stageSide = (width) => (width > 1920 ? (width - PAGE_MAX) / 2 : stageMargin(width))

/** The work area: the stage between the masthead and the status bar, the whole viewport without a shell. */
export const workArea = () => {
  const main = document.querySelector('.shell-app > .shell-main')?.getBoundingClientRect()
  const view = viewport()
  if (!main || main.height <= 0) return { x: 0, y: 0, w: view.w, h: view.h }
  return { x: 0, y: Math.round(main.top), w: view.w, h: Math.max(0, view.h - Math.round(main.top)) }
}

/** A maximized window: the work area inside the stage's margins, the shell left uncovered. */
export function maxRect(area, width) {
  const m = stageMargin(width)
  const s = stageSide(width)
  return { x: area.x + s, y: area.y + m, w: Math.max(0, area.w - 2 * s), h: Math.max(0, area.h - 2 * m) }
}

/** The rect moved and shrunk to fit the viewport: inside it whole, as large as it fits, never under the minimum. */
export function clampRect(rect, view) {
  const w = clamp(Math.round(rect.w), MIN_W, view.w)
  const h = clamp(Math.round(rect.h), MIN_H, view.h)
  return { x: clamp(Math.round(rect.x), 0, view.w - w), y: clamp(Math.round(rect.y), 0, view.h - h), w, h }
}

/**
 * The n-th window opened: in the free margin right of a centred page when it holds the window, clear of the
 * page; else down and to the right of the one before, moved with a centred page (the inspector's controls, at
 * the right, stay uncovered). Back to the top after eight.
 */
export function cascadeRect(n, size, view) {
  const step = (n % 8) * CASCADE
  const margin = stageMargin(view.w)
  const shift = stageSide(view.w) - margin
  if (shift >= size.w) {
    return clampRect({ x: view.w - margin - size.w - Math.min(step, shift - size.w), y: ORIGIN.y + step, w: size.w, h: size.h }, view)
  }
  return clampRect({ x: ORIGIN.x + shift + step, y: ORIGIN.y + step, w: size.w, h: size.h }, view)
}

/** A drag of the edge (n, s, e, w or a corner such as 'se') by dx, dy: the opposite edges stay put. */
export function resizeRect(rect, edge, dx, dy, view) {
  let { x, y, w, h } = rect
  if (edge.includes('e')) w = clamp(w + dx, MIN_W, view.w - x)
  if (edge.includes('s')) h = clamp(h + dy, MIN_H, view.h - y)
  if (edge.includes('w')) {
    const right = x + w
    const nx = clamp(x + dx, 0, right - MIN_W)
    w = right - nx
    x = nx
  }
  if (edge.includes('n')) {
    const bottom = y + h
    const ny = clamp(y + dy, 0, bottom - MIN_H)
    h = bottom - ny
    y = ny
  }
  return clampRect({ x, y, w, h }, view)
}

/** The keyboard of the window's handle: arrows move it, Shift and arrows resize it. */
export function keyRect(rect, key, shift, view) {
  const d = { ArrowLeft: [-STEP, 0], ArrowRight: [STEP, 0], ArrowUp: [0, -STEP], ArrowDown: [0, STEP] }[key]
  if (!d) return null
  if (shift) return clampRect({ ...rect, w: rect.w + d[0], h: rect.h + d[1] }, view)
  return clampRect({ ...rect, x: rect.x + d[0], y: rect.y + d[1] }, view)
}
