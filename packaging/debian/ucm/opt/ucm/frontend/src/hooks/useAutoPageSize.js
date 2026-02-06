/**
 * useAutoPageSize Hook
 * Calculates optimal rows per page based on container height
 */
import { useState, useEffect, useRef, useCallback } from 'react'

const ROW_HEIGHT = 41 // px - height of a table row (py-2.5 + content)
const HEADER_HEIGHT = 37 // px - height of table header
const PAGINATION_HEIGHT = 52 // px - height of pagination bar

export function useAutoPageSize(options = {}) {
  const {
    rowHeight = ROW_HEIGHT,
    headerHeight = HEADER_HEIGHT,
    paginationHeight = PAGINATION_HEIGHT,
    minRows = 5,
    maxRows = 100,
    defaultPerPage = 20,
    mode = 'auto' // 'auto' | 'fixed'
  } = options

  const containerRef = useRef(null)
  const [perPage, setPerPage] = useState(defaultPerPage)
  const [autoMode, setAutoMode] = useState(mode === 'auto')

  const calculateRows = useCallback(() => {
    if (!containerRef.current || !autoMode) return

    const containerHeight = containerRef.current.clientHeight
    const availableHeight = containerHeight - headerHeight - paginationHeight
    const calculatedRows = Math.floor(availableHeight / rowHeight)
    const clampedRows = Math.max(minRows, Math.min(maxRows, calculatedRows))
    
    setPerPage(clampedRows)
  }, [autoMode, rowHeight, headerHeight, paginationHeight, minRows, maxRows])

  useEffect(() => {
    calculateRows()

    // Recalculate on resize
    const resizeObserver = new ResizeObserver(() => {
      if (autoMode) calculateRows()
    })

    if (containerRef.current) {
      resizeObserver.observe(containerRef.current)
    }

    return () => resizeObserver.disconnect()
  }, [calculateRows, autoMode])

  const setMode = useCallback((newMode) => {
    if (newMode === 'auto') {
      setAutoMode(true)
      // Recalculate immediately
      setTimeout(calculateRows, 0)
    } else {
      setAutoMode(false)
    }
  }, [calculateRows])

  const setFixedPerPage = useCallback((value) => {
    setAutoMode(false)
    setPerPage(value)
  }, [])

  return {
    containerRef,
    perPage,
    autoMode,
    setMode,
    setPerPage: setFixedPerPage,
    recalculate: calculateRows
  }
}

// Preset page size options
export const PAGE_SIZE_OPTIONS = [
  { value: 'auto', label: 'Auto' },
  { value: 10, label: '10' },
  { value: 20, label: '20' },
  { value: 50, label: '50' },
  { value: 100, label: '100' },
]
