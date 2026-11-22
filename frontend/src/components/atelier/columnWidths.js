/**
 * The widths a list's columns were given by hand (COLONNES-SPEC C2), kept in this browser under the list's key
 * ({ id: px }); storage refused (private mode, quota) keeps them for the session only.
 */
import { useCallback, useEffect, useRef, useState } from 'react'

/** Only positive finite widths, whatever the storage held. */
export function cleanWidths(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
  return Object.fromEntries(Object.entries(value).filter(([, w]) => typeof w === 'number' && Number.isFinite(w) && w > 0))
}

function read(key) {
  if (!key) return {}
  try {
    const saved = localStorage.getItem(key)
    return saved ? cleanWidths(JSON.parse(saved)) : {}
  } catch {
    return {}
  }
}

function write(key, widths) {
  if (!key) return
  try {
    if (Object.keys(widths).length) localStorage.setItem(key, JSON.stringify(widths))
    else localStorage.removeItem(key)
  } catch { /* quota exceeded, private mode */ }
}

/** @returns {[Record<string, number>, (id: string, width: number|null) => void, () => void]}  null clears one width */
export function useColumnWidths(key) {
  const [state, setState] = useState(() => ({ key, widths: read(key) }))
  // Another list (another key) reads its own widths
  const current = state.key === key ? state : { key, widths: read(key) }
  if (current !== state) setState(current)
  const touched = useRef(false)
  useEffect(() => {
    if (touched.current) write(state.key, state.widths)
    touched.current = false
  }, [state])
  const setWidth = useCallback((id, width) => {
    touched.current = true
    setState((prev) => {
      const widths = { ...prev.widths }
      if (width === null || width === undefined) delete widths[id]
      else widths[id] = Math.round(width)
      return { key: prev.key, widths }
    })
  }, [])
  const clear = useCallback(() => {
    touched.current = true
    setState((prev) => ({ key: prev.key, widths: {} }))
  }, [])
  return [current.widths, setWidth, clear]
}
