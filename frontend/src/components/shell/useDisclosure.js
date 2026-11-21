/**
 * Open state shared by the shell's popovers: closes on Escape (focus back to
 * the button), on a click outside, when focus leaves, and on a route change.
 * `{ light: false }` keeps a panel open on a click outside or a focus leaving it. `partRef` marks a
 * panel drawn apart from the root (the mockup's Modules menu follows the bar's links): inside too.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'

export function useDisclosure({ light = true } = {}) {
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)
  const buttonRef = useRef(null)
  const partRef = useRef(null)
  const inside = (el) => !!(rootRef.current?.contains(el) || partRef.current?.contains(el))

  const close = useCallback((restoreFocus = false) => {
    setOpen(false)
    if (restoreFocus) buttonRef.current?.focus()
  }, [])

  useEffect(() => { setOpen(false) }, [pathname])

  useEffect(() => {
    if (!open || !light) return undefined
    const onDown = (e) => { if (!inside(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open, light])

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
