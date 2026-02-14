/**
 * WindowManager — Context for managing multiple floating detail windows
 * 
 * Features:
 * - Open/close detail windows by entity type + ID
 * - Max 6 simultaneous windows (oldest auto-closes)
 * - Z-index focus stack (click = bring to front)
 * - Cascade positioning (+30px offset per window)
 * - Tile/stack/close-all toolbar actions
 */
import { createContext, useContext, useState, useCallback, useRef } from 'react'

const WindowManagerContext = createContext(null)

const MAX_WINDOWS = 6
const CASCADE_OFFSET = 30
const BASE_Z = 100

export function WindowManagerProvider({ children }) {
  // windows: [{ id, type, entityId, data, zIndex }]
  const [windows, setWindows] = useState([])
  const zCounter = useRef(BASE_Z)

  const getWindowKey = (type, entityId) => `${type}:${entityId}`

  const openWindow = useCallback((type, entityId, data = {}) => {
    setWindows(prev => {
      const key = getWindowKey(type, entityId)
      const existing = prev.find(w => w.id === key)

      if (existing) {
        // Already open — bring to front
        zCounter.current += 1
        return prev.map(w => w.id === key ? { ...w, zIndex: zCounter.current, data: { ...w.data, ...data } } : w)
      }

      // Calculate cascade position
      const cascadeIndex = prev.length % 8
      const defaultPos = {
        x: 80 + cascadeIndex * CASCADE_OFFSET,
        y: 60 + cascadeIndex * CASCADE_OFFSET,
        w: 520,
        h: 500,
      }

      zCounter.current += 1
      const newWindow = {
        id: key,
        type,
        entityId,
        data,
        zIndex: zCounter.current,
        defaultPos,
      }

      let next = [...prev, newWindow]

      // Enforce max windows — close oldest
      if (next.length > MAX_WINDOWS) {
        next = next.slice(next.length - MAX_WINDOWS)
      }

      return next
    })
  }, [])

  const closeWindow = useCallback((id) => {
    setWindows(prev => prev.filter(w => w.id !== id))
  }, [])

  const closeAll = useCallback(() => {
    setWindows([])
  }, [])

  const focusWindow = useCallback((id) => {
    zCounter.current += 1
    setWindows(prev => prev.map(w =>
      w.id === id ? { ...w, zIndex: zCounter.current } : w
    ))
  }, [])

  const tileWindows = useCallback(() => {
    setWindows(prev => {
      if (prev.length === 0) return prev
      const margin = 16
      const vw = window.innerWidth - margin * 2
      const vh = window.innerHeight - margin * 2 - 60 // leave space for toolbar
      const count = prev.length

      // Calculate grid: prefer wider tiles
      let cols, rows
      if (count <= 2) { cols = count; rows = 1 }
      else if (count <= 4) { cols = 2; rows = Math.ceil(count / 2) }
      else { cols = 3; rows = Math.ceil(count / 3) }

      const tileW = Math.floor(vw / cols)
      const tileH = Math.floor(vh / rows)

      return prev.map((w, i) => {
        const col = i % cols
        const row = Math.floor(i / cols)
        return {
          ...w,
          defaultPos: {
            x: margin + col * tileW,
            y: margin + row * tileH,
            w: tileW - 8,
            h: tileH - 8,
          },
          _tileKey: Date.now(), // force re-position
        }
      })
    })
  }, [])

  const stackWindows = useCallback(() => {
    setWindows(prev => prev.map((w, i) => ({
      ...w,
      defaultPos: {
        x: 80 + i * CASCADE_OFFSET,
        y: 60 + i * CASCADE_OFFSET,
        w: 520,
        h: 500,
      },
      _tileKey: Date.now(),
    })))
  }, [])

  const updateWindowData = useCallback((id, data) => {
    setWindows(prev => prev.map(w =>
      w.id === id ? { ...w, data: { ...w.data, ...data } } : w
    ))
  }, [])

  return (
    <WindowManagerContext.Provider value={{
      windows,
      openWindow,
      closeWindow,
      closeAll,
      focusWindow,
      tileWindows,
      stackWindows,
      updateWindowData,
      windowCount: windows.length,
    }}>
      {children}
    </WindowManagerContext.Provider>
  )
}

export function useWindowManager() {
  const ctx = useContext(WindowManagerContext)
  if (!ctx) throw new Error('useWindowManager must be used within WindowManagerProvider')
  return ctx
}
