/**
 * The section a page shows or jumps to, kept in `?tab=` so a link opens on it. On a page
 * of stacked frames a change scrolls to the frame; on a page of one frame at a time the
 * new frame's title takes the focus.
 */
import { useCallback, useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { jumpToSection, focusSectionTitle } from './SectionedForm'

export function useSectionParam(ids, fallback, { stacked = false, ready = true } = {}) {
  const [params, setParams] = useSearchParams()
  const raw = params.get('tab')
  const current = ids.includes(raw) ? raw : fallback
  // A link that names a section on a one-frame page also lands the focus on its title
  const focusNext = useRef(Boolean(raw && ids.includes(raw)))
  // A landing (no choice made on the page) focuses quietly; a choice made here is not a landing
  const quietNext = useRef(focusNext.current)
  const chosen = useRef(null)

  const select = useCallback((id) => {
    const next = new URLSearchParams(params)
    if (id === fallback) next.delete('tab')
    else next.set('tab', id)
    chosen.current = id
    setParams(next, { replace: true })
    if (stacked) jumpToSection(id)
    else { focusNext.current = true; quietNext.current = false }
  }, [params, setParams, fallback, stacked])

  // A link that names a section lands on it once the frames are on the page
  useEffect(() => {
    if (stacked && ready && raw && ids.includes(raw) && raw !== chosen.current) jumpToSection(raw, { quiet: true })
  }, [raw, ready, stacked]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (stacked || !ready || !focusNext.current) return
    focusNext.current = false
    focusSectionTitle(current, { quiet: quietNext.current })
    quietNext.current = false
  }, [current, stacked, ready])

  return [current, select]
}
