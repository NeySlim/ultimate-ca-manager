/**
 * Room of the bar's links. Short of room, their side padding tightens (no less than FLOOR); then the
 * pinned labels end in an ellipsis; then the pinned links fold away, as the mockup's narrow bar does.
 * The font and the bar's height never change. Sets `--nav-pad` and `data-room` on the nav.
 */
import { useLayoutEffect } from 'react'

export const FLOOR = 6

/**
 * `room`: width the nav may take; `gap`: between links; `links`: per link its width without padding
 * (`content`), the stylesheet's padding of one side (`mock`), whether it is pinned and its label's
 * natural width when shown (`label`). Returns `{ pad, fold }`; pad null keeps the stylesheet's.
 */
export function planNavRoom({ room, gap, links }) {
  const fit = (list) => {
    const content = list.reduce((s, l) => s + l.content, 0) + gap * Math.max(list.length - 1, 0)
    const mock = list.reduce((s, l) => s + 2 * l.mock, 0)
    if (content + mock <= room) return { pad: null }
    const pad = Math.min(Math.floor(((room - content) / (2 * list.length)) * 10) / 10, Math.min(...list.map(l => l.mock)))
    if (pad >= FLOOR) return { pad }
    // At the floor, the shown pinned labels may give up their width
    const labels = list.reduce((s, l) => s + (l.pinned ? l.label : 0), 0)
    if (content - labels + 2 * FLOOR * list.length <= room) return { pad: FLOOR }
    return null
  }
  const all = fit(links)
  if (all) return { ...all, fold: false }
  const kept = links.filter(l => !l.pinned)
  if (kept.length === links.length) return { pad: FLOOR, fold: false }
  return { ...(fit(kept) || { pad: FLOOR }), fold: true }
}

function measure(nav) {
  const bar = nav.parentElement
  const tools = bar.querySelector('.global-tools')
  if (!tools || nav.getBoundingClientRect().height === 0) return null
  // The stylesheet's own padding and the links' natural widths, read without our override and fold
  nav.style.removeProperty('--nav-pad')
  nav.dataset.room = 'measure'
  const links = [...nav.children].filter(el => el.matches('a, button') && el.getBoundingClientRect().width > 0)
  if (links.length === 0) {
    delete nav.dataset.room
    return null
  }
  const barGap = parseFloat(getComputedStyle(bar).columnGap) || 0
  const plan = {
    room: tools.getBoundingClientRect().left - barGap - nav.getBoundingClientRect().left,
    gap: parseFloat(getComputedStyle(nav).columnGap) || 0,
    links: links.map(el => {
      const s = getComputedStyle(el)
      const mock = parseFloat(s.paddingLeft) || 0
      const pinned = el.classList.contains('pinned-link')
      const lab = pinned ? el.querySelector('.pin-label') : null
      const shown = lab && getComputedStyle(lab).position !== 'absolute'
      return {
        content: el.getBoundingClientRect().width - mock - (parseFloat(s.paddingRight) || 0),
        mock,
        pinned,
        label: shown ? lab.getBoundingClientRect().width : 0,
      }
    }),
  }
  delete nav.dataset.room
  return plan
}

/** Keeps the nav's links in the bar's room; `deps` re-measure (pins, language). */
export function useNavRoom(navRef, deps = []) {
  useLayoutEffect(() => {
    const nav = navRef.current
    if (!nav || typeof ResizeObserver === 'undefined') return undefined
    let frame = 0
    const apply = () => {
      frame = 0
      const m = measure(nav)
      if (!m) return
      const { pad, fold } = planNavRoom(m)
      if (pad != null) nav.style.setProperty('--nav-pad', `${pad}px`)
      if (fold) nav.dataset.room = 'fold'
    }
    const schedule = () => { if (!frame) frame = requestAnimationFrame(apply) }
    apply()
    const ro = new ResizeObserver(schedule)
    ro.observe(nav.parentElement)
    ;[...nav.children].forEach(el => ro.observe(el))
    document.fonts?.ready?.then(schedule)
    return () => { ro.disconnect(); if (frame) cancelAnimationFrame(frame) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
}
