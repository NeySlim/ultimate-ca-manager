/**
 * Pinned modules: at most three registry ids per user, kept in the server
 * preferences under `pins`. Stored order is display order.
 */
import { useEffect, useState } from 'react'
import { getPreferences, subscribePreferences, persistPreference } from '../../stores/userPreferencesStore'
import { isVisible, moduleById } from '../../navigation/registry'

export const MAX_PINS = 3
// Always present in the bar: never pinned twice
export const FIXED_IDS = ['dashboard', 'certificates', 'cas']

export const canPinModule = (mod) => !!mod && mod.pinnable && !FIXED_IDS.includes(mod.id)

/** Stored ids that are known, pinnable and visible to `can`, capped at MAX_PINS; the rest is hidden, not an error. */
export function visiblePins(stored, can) {
  const seen = new Set()
  const out = []
  for (const id of Array.isArray(stored) ? stored : []) {
    const mod = typeof id === 'string' ? moduleById(id) : null
    if (!canPinModule(mod) || !isVisible(mod, can) || seen.has(id)) continue
    seen.add(id)
    out.push(id)
  }
  return out.slice(0, MAX_PINS)
}

/** Next pin list after toggling `id`, or null when a fourth pin is refused. */
export function togglePinList(current, id) {
  if (current.includes(id)) return current.filter(p => p !== id)
  if (current.length >= MAX_PINS) return null
  return [...current, id]
}

export function usePins(can) {
  const [stored, setStored] = useState(() => getPreferences().pins)
  useEffect(() => {
    setStored(getPreferences().pins)
    return subscribePreferences((prefs) => setStored(prefs.pins))
  }, [])

  const pins = visiblePins(stored, can)

  // Writes the visible list: a pin hidden by a withdrawn right is dropped here,
  // which also keeps the stored list within the server's cap of three.
  const toggle = (id) => {
    const next = togglePinList(pins, id)
    if (!next) return false
    persistPreference('pins', next)
    return true
  }

  return { pins, toggle }
}
