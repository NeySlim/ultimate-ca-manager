/**
 * Open state of the shell's popovers, one open at a time (openPanel.js): closes on Escape (focus back
 * to the button), on a click outside, when focus leaves, on a route change and when another panel opens.
 * `{ light: false }` keeps a side panel open when the focus leaves it. `partRef` marks a panel drawn apart
 * from the root (the Modules menu after the bar's links, the notifications in their slot): inside too.
 */
import { useCallback, useEffect, useId, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { usePanel } from './openPanel'

export function useDisclosure({ light = true } = {}) {
  const { pathname } = useLocation()
  const [open, setOpen] = usePanel(useId())
  const rootRef = useRef(null)
  const buttonRef = useRef(null)
  const partRef = useRef(null)
  const inside = (el) => !!(rootRef.current?.contains(el) || partRef.current?.contains(el))

  const close = useCallback((restoreFocus = false) => {
    setOpen(false)
    if (restoreFocus) buttonRef.current?.focus()
  }, [setOpen])

  useEffect(() => { setOpen(false) }, [pathname]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!open) return undefined
    const onDown = (e) => { if (!inside(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  const onKeyDown = (e) => {
    if (open && e.key === 'Escape') {
      e.preventDefault()
      close(true)
    }
  }
  const onBlur = (e) => {
    if (light && open && e.relatedTarget && !inside(e.relatedTarget)) setOpen(false)
  }

  return { open, setOpen, close, rootRef, buttonRef, partRef, rootProps: { ref: rootRef, onKeyDown, onBlur }, partProps: { ref: partRef, onKeyDown, onBlur } }
}

/** Arrow, Home and End moves over `items` (an array of elements); returns true when the key was handled. */
export function moveFocus(e, items) {
  if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key) || items.length === 0) return false
  e.preventDefault()
  const i = items.indexOf(document.activeElement)
  const last = items.length - 1
  let next
  if (e.key === 'Home') next = 0
  else if (e.key === 'End') next = last
  else if (i < 0) next = e.key === 'ArrowUp' ? last : 0
  else next = (i + (e.key === 'ArrowDown' ? 1 : last)) % items.length
  items[next].focus()
  return true
}
