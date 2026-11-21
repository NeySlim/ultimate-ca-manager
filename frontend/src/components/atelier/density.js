/**
 * The row density of every list: one preference for the whole interface, as the mockup's
 * state.comfortable that puts `comfortable` on #app (M:56, M:1108, M:1317). Kept in this browser.
 */
import { useSyncExternalStore } from 'react'

export const DENSITY_KEY = 'ucm-atelier-density'
const listeners = new Set()
// Used once the browser refuses its storage: the choice then lasts until a reload
let memory = null

function read() {
  if (memory !== null) return memory
  try { return localStorage.getItem(DENSITY_KEY) === 'comfortable' } catch { return false }
}

function subscribe(listener) {
  listeners.add(listener)
  // Another tab changing the density redraws this one too
  const onStorage = (e) => { if (e.key === DENSITY_KEY || e.key === null) listener() }
  window.addEventListener('storage', onStorage)
  return () => { listeners.delete(listener); window.removeEventListener('storage', onStorage) }
}

export function setComfortable(on) {
  try {
    if (on) localStorage.setItem(DENSITY_KEY, 'comfortable')
    else localStorage.removeItem(DENSITY_KEY)
  } catch { memory = !!on }
  listeners.forEach((l) => l())
}

/** @returns {boolean} whether the rows are comfortable (44 px) rather than compact (36 px) */
export function useComfortable() {
  return useSyncExternalStore(subscribe, read, () => false)
}
