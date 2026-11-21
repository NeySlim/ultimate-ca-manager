/**
 * Open state shared by the shell's popovers: closes on Escape (focus back to
 * the button), on a click outside, when focus leaves, and on a route change.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'

export function useDisclosure() {
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)
  const buttonRef = useRef(null)

  const close = useCallback((restoreFocus = false) => {
    setOpen(false)
    if (restoreFocus) buttonRef.current?.focus()
  }, [])

  useEffect(() => { setOpen(false) }, [pathname])

  useEffect(() => {
    if (!open) return undefined
    const onDown = (e) => { if (!rootRef.current?.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const onKeyDown = (e) => {
    if (open && e.key === 'Escape') {
      e.preventDefault()
      close(true)
    }
  }
  const onBlur = (e) => {
    if (open && e.relatedTarget && !rootRef.current?.contains(e.relatedTarget)) setOpen(false)
  }

  return { open, setOpen, close, rootRef, buttonRef, rootProps: { ref: rootRef, onKeyDown, onBlur } }
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
