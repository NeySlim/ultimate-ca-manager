/**
 * The section a page shows or jumps to, kept in `?tab=` so a link opens on it. On a page
 * of stacked frames a change scrolls to the frame; on a page of one frame at a time the
 * new frame's title takes the focus.
 */
import { useCallback, useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { jumpToSection, sectionTitleId } from './SectionedForm'

export function useSectionParam(ids, fallback, { stacked = false, ready = true } = {}) {
  const [params, setParams] = useSearchParams()
  const raw = params.get('tab')
  const current = ids.includes(raw) ? raw : fallback
  // A link that names a section on a one-frame page also lands the focus on its title
  const focusNext = useRef(Boolean(raw && ids.includes(raw)))

  const select = useCallback((id) => {
    const next = new URLSearchParams(params)
    if (id === fallback) next.delete('tab')
    else next.set('tab', id)
    setParams(next, { replace: true })
    if (stacked) jumpToSection(id)
    else focusNext.current = true
  }, [params, setParams, fallback, stacked])

  // A link that names a section lands on it once the frames are on the page
  useEffect(() => {
    if (stacked && ready && raw && ids.includes(raw)) jumpToSection(raw)
  }, [raw, ready, stacked]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (stacked || !ready || !focusNext.current) return
    focusNext.current = false
    document.getElementById(sectionTitleId(current))?.focus()
  }, [current, stacked, ready])

  return [current, select]
}
