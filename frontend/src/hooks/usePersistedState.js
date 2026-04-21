/**
 * usePersistedState - Drop-in replacement for useState that persists to localStorage
 *
 * Used for keeping the active filter state across page reloads (issue #57).
 *
 * Usage:
 *   // Same signature as useState, with a storage key prepended
 *   const [filterStatus, setFilterStatus] = usePersistedState(
 *     'ucm-filter-certs-status',
 *     []
 *   )
 *
 * The value is auto-saved to localStorage on every change (debounced 200ms).
 * On mount, the saved value (if any) is restored. If parsing fails or no value
 * is saved, the default is used.
 *
 * To clear: call setFilterStatus(defaultValue) — the hook will remove the
 * key from localStorage when the value matches the default.
 */
import { useState, useEffect, useRef, useCallback } from 'react'

const isEmpty = (value) => {
  if (value === '' || value === null || value === undefined) return true
  if (Array.isArray(value) && value.length === 0) return true
  if (typeof value === 'object' && value !== null && Object.keys(value).length === 0) return true
  return false
}

export function usePersistedState(storageKey, defaultValue) {
  const [value, setValue] = useState(() => {
    if (!storageKey) return defaultValue
    try {
      const saved = localStorage.getItem(storageKey)
      if (saved === null) return defaultValue
      const parsed = JSON.parse(saved)
      return parsed
    } catch {
      return defaultValue
    }
  })

  const isInitialMount = useRef(true)

  useEffect(() => {
    if (!storageKey) return
    if (isInitialMount.current) {
      isInitialMount.current = false
      return
    }
    const timer = setTimeout(() => {
      try {
        if (isEmpty(value)) {
          localStorage.removeItem(storageKey)
        } else {
          localStorage.setItem(storageKey, JSON.stringify(value))
        }
      } catch { /* quota exceeded, Safari private mode */ }
    }, 200)
    return () => clearTimeout(timer)
  }, [value, storageKey])

  const reset = useCallback(() => {
    setValue(defaultValue)
    try { localStorage.removeItem(storageKey) } catch { /* ignore */ }
  }, [defaultValue, storageKey])

  return [value, setValue, reset]
}
