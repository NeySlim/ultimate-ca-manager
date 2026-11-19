/**
 * Masonry over a CSS grid: each slot spans as many thin rows as its card is high, and the dense
 * flow packs the columns. Only placement changes: the DOM order, hence reading and tab order, stays.
 */
import { useLayoutEffect } from 'react'

// Browsers stop at 10 000 grid lines at the least: taller pages get thicker rows
const MAX_ROWS = 8000

export function masonrySpans(heights, gap) {
  const total = heights.reduce((sum, h) => sum + h + gap, 0)
  const unit = Math.max(1, Math.ceil(total / MAX_ROWS))
  return { unit, spans: heights.map((h) => Math.max(1, Math.ceil((h + gap) / unit))) }
}

export function packGrid(grid) {
  const slots = [...grid.children]
  const gap = parseFloat(getComputedStyle(grid).columnGap) || 0
  const { unit, spans } = masonrySpans(slots.map((s) => s.firstElementChild?.getBoundingClientRect().height || 0), gap)
  grid.style.gridAutoRows = `${unit}px`
  slots.forEach((slot, i) => { slot.style.gridRowEnd = `span ${spans[i]}` })
  grid.setAttribute('data-masonry', '')
}

/** Packs the grid now and whenever a card or the grid changes size; `key` names the cards shown. */
export function useMasonry(ref, key) {
  useLayoutEffect(() => {
    const grid = ref.current
    if (!grid || typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(() => packGrid(grid))
    observer.observe(grid)
    for (const slot of grid.children) if (slot.firstElementChild) observer.observe(slot.firstElementChild)
    packGrid(grid)
    return () => observer.disconnect()
  }, [ref, key])
}
