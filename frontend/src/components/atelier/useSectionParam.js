/**
 * The section a page of the mockup's sectioned form shows or jumps to, kept in `?tab=` so a link
 * opens on it. Stacked sections: a choice scrolls to its frame (`#set-sec-<id>`) and focuses its
 * title; one section at a time: the new frame's title takes the focus once it is drawn.
 */
import { useCallback, useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { jumpTo } from './helpers'

export function useSectionParam(ids, fallback, { stacked = false, ready = true } = {}) {
  const [params, setParams] = useSearchParams()
  const raw = params.get('tab')
  const current = ids.includes(raw) ? raw : fallback
  // A link that names a section lands the focus on its title, quietly (no key was pressed)
  const focusNext = useRef(Boolean(raw && ids.includes(raw)))
  const quietNext = useRef(focusNext.current)
  const chosen = useRef(null)

  const select = useCallback((id) => {
    const next = new URLSearchParams(params)
    // One section at a time: the sort of the list left behind is not the next one's (T9)
    if (!stacked && id !== current) { next.delete('sort'); next.delete('order') }
    if (id === fallback) next.delete('tab')
    else next.set('tab', id)
    chosen.current = id
    setParams(next, { replace: true })
    if (stacked) jumpTo(id)
    else { focusNext.current = true; quietNext.current = false }
  }, [params, setParams, fallback, stacked, current])

  useEffect(() => {
    if (stacked && ready && raw && ids.includes(raw) && raw !== chosen.current) jumpTo(raw, { quiet: true })
  }, [raw, ready, stacked]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (stacked || !ready || !focusNext.current) return
    focusNext.current = false
    jumpTo(current, { quiet: quietNext.current })
    quietNext.current = false
  }, [current, stacked, ready])

  return [current, select]
}

export default useSectionParam
