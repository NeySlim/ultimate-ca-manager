/**
 * The one open panel of the shell: the bar's menus (modules, language, theme, account), the notifications,
 * the help and the palette. Opening one closes the one open before; a module state, so the sign-in pages'
 * menus share it without the shell.
 */
import { useCallback, useEffect, useSyncExternalStore } from 'react'

let current = null
const listeners = new Set()
const emit = () => listeners.forEach((l) => l())
const subscribe = (l) => { listeners.add(l); return () => listeners.delete(l) }

export const openPanel = (id) => { if (current !== id) { current = id; emit() } }
export const closePanel = (id) => { if (current === id) { current = null; emit() } }
export const openedPanel = () => current

/** [open, setOpen] of the panel `id`; a panel that unmounts open leaves the state free. */
export function usePanel(id) {
  const open = useSyncExternalStore(subscribe, () => current === id, () => false)
  const setOpen = useCallback((on) => (on ? openPanel(id) : closePanel(id)), [id])
  useEffect(() => () => closePanel(id), [id])
  return [open, setOpen]
}
