/**
 * usePersistedFilters - Save/restore filter state to localStorage
 * 
 * Usage:
 *   const { filters, setFilter, clearFilters } = usePersistedFilters('certificates', {
 *     status: '', ca_id: '', search: ''
 *   })
 */
import { useState, useCallback, useEffect, useRef } from 'react'

const STORAGE_PREFIX = 'ucm-filters-'

export function usePersistedFilters(pageId, defaultFilters = {}) {
  const storageKey = `${STORAGE_PREFIX}${pageId}`
  
  const [filters, setFilters] = useState(() => {
    try {
      const saved = localStorage.getItem(storageKey)
      if (saved) {
        const parsed = JSON.parse(saved)
        // Merge with defaults to handle new filter keys
        return { ...defaultFilters, ...parsed }
      }
    } catch { /* ignore */ }
    return { ...defaultFilters }
  })

  const isInitialMount = useRef(true)

  // Debounced save to localStorage
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false
      return
    }
    const timer = setTimeout(() => {
      try {
        // Only save non-default values
        const toSave = {}
        let hasValues = false
        Object.entries(filters).forEach(([key, value]) => {
          if (value !== '' && value !== null && value !== undefined && 
              !(Array.isArray(value) && value.length === 0)) {
            toSave[key] = value
            hasValues = true
          }
        })
        if (hasValues) {
          localStorage.setItem(storageKey, JSON.stringify(toSave))
        } else {
          localStorage.removeItem(storageKey)
        }
      } catch { /* quota exceeded, Safari private mode */ }
    }, 300)
    return () => clearTimeout(timer)
  }, [filters, storageKey])

  const setFilter = useCallback((key, value) => {
    setFilters(prev => ({ ...prev, [key]: value }))
  }, [])

  const clearFilters = useCallback(() => {
    setFilters({ ...defaultFilters })
    try { localStorage.removeItem(storageKey) } catch { /* ignore */ }
  }, [defaultFilters, storageKey])

  const activeCount = Object.entries(filters).reduce((count, [, value]) => {
    if (Array.isArray(value)) return count + (value.length > 0 ? 1 : 0)
    return count + (value ? 1 : 0)
  }, 0)

  return { filters, setFilter, setFilters, clearFilters, activeCount }
}
