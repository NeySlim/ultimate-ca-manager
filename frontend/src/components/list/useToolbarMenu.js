/**
 * Keyboard of a pop menu of the mockup (theme menu, « +N »): opening puts the focus on the
 * first item, the arrows, Home and End move between items, Left and Right between the two
 * items of a line, Escape and Tab close it on its button. The key is marked handled, so a
 * layer under it (the inspector) only answers the next Escape.
 */
import { useCallback, useEffect, useRef } from 'react'

const ITEMS = '[role="menuitem"]:not(:disabled)'

export function useToolbarMenu(open, setOpen) {
  const buttonRef = useRef(null)
  const menuRef = useRef(null)
  const focusAt = useRef('first')
  const setOpenRef = useRef(setOpen)
  setOpenRef.current = setOpen

  useEffect(() => {
    if (!open) return undefined
    const menu = menuRef.current
    const items = () => [...(menuRef.current?.querySelectorAll(ITEMS) || [])]
    const shown = items()
    const target = focusAt.current === 'last' ? shown.at(-1) : shown[0]
    if (target) target.focus()
    else menu?.focus()
    focusAt.current = 'first'
    const close = () => { setOpenRef.current(false); buttonRef.current?.focus() }
    const onKey = (e) => {
      if (e.defaultPrevented) return
      const inMenu = menuRef.current?.contains(e.target)
      if (e.key === 'Escape') { e.preventDefault(); close(); return }
      // Tab leaves from an item or the button; a field of the menu keeps its own Tab
      if (e.key === 'Tab' && (!inMenu || e.target.matches?.(ITEMS) || e.target === menuRef.current)) { e.preventDefault(); close(); return }
      if (!inMenu) return
      const list = items()
      const i = list.indexOf(e.target)
      if (!list.length || i < 0) return
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        const pair = [...(e.target.parentElement?.querySelectorAll(':scope > [role="menuitem"]') || [])]
        if (pair.length === 2) { e.preventDefault(); pair[1 - pair.indexOf(e.target)].focus() }
        return
      }
      if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) return
      e.preventDefault()
      // Up and Down go by line: a line of two items sits in a role="none" wrapper, led by its first item
      const lead = (el) => (el.parentElement?.getAttribute('role') === 'none' ? el.parentElement.querySelector(ITEMS) : el)
      const lines = list.filter((el) => lead(el) === el)
      const at = lines.indexOf(lead(e.target))
      const n = lines.length
      const next = e.key === 'Home' ? 0 : e.key === 'End' ? n - 1 : (at + (e.key === 'ArrowDown' ? 1 : n - 1)) % n
      lines[next]?.focus()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  // The down and up arrows on the closed button open the menu on its first or last item
  const onButtonKeyDown = useCallback((e) => {
    if (open || (e.key !== 'ArrowDown' && e.key !== 'ArrowUp')) return
    e.preventDefault()
    focusAt.current = e.key === 'ArrowUp' ? 'last' : 'first'
    setOpenRef.current(true)
  }, [open])

  return { buttonRef, menuRef, onButtonKeyDown }
}
