/**
 * WindowManager — Context for managing multiple floating detail windows
 * 
 * Features:
 * - Open/close detail windows by entity type + ID
 * - Max 6 simultaneous windows (oldest auto-closes)
 * - Z-index focus stack (click = bring to front)
 * - Center positioning (new windows open centered)
 * - Tile/stack/close-all actions
 * - Options: sameWindow (reuse existing), closeOnNav (auto-close on page change)
 */
import { createContext, useContext, useState, useCallback, useRef } from 'react'

const WindowManagerContext = createContext(null)

const MAX_WINDOWS = 6
const CASCADE_OFFSET = 30
const BASE_Z = 100
const PREFS_KEY = 'ucm-window-prefs'

function loadPrefs() {
  try { return JSON.parse(localStorage.getItem(PREFS_KEY)) || {} } catch { return {} }
}
function savePrefs(prefs) {
  try { localStorage.setItem(PREFS_KEY, JSON.stringify(prefs)) } catch {}
}

export function WindowManagerProvider({ children }) {
  const [windows, setWindows] = useState([])
  const zCounter = useRef(BASE_Z)

  // User preferences
  const [sameWindow, setSameWindow] = useState(() => loadPrefs().sameWindow ?? true)
  const [closeOnNav, setCloseOnNav] = useState(() => loadPrefs().closeOnNav ?? true)

  const toggleSameWindow = useCallback(() => {
    setSameWindow(prev => {
      const next = !prev
      savePrefs({ ...loadPrefs(), sameWindow: next })
      return next
    })
  }, [])

  const toggleCloseOnNav = useCallback(() => {
    setCloseOnNav(prev => {
      const next = !prev
      savePrefs({ ...loadPrefs(), closeOnNav: next })
      return next
    })
  }, [])

  const getWindowKey = (type, entityId) => `${type}:${entityId}`

  // Center position for new windows
  const getCenterPos = useCallback((index) => {
    const w = 442, h = 425
    const vw = window.innerWidth
    const vh = window.innerHeight
    const offset = index * CASCADE_OFFSET
    return {
      x: Math.max(20, Math.round((vw - w) / 2) + offset),
      y: Math.max(20, Math.round((vh - h) / 2) + offset),
      w, h,
    }
  }, [])

  const openWindow = useCallback((type, entityId, data = {}) => {
    setWindows(prev => {
      const key = getWindowKey(type, entityId)
      const existing = prev.find(w => w.id === key)

      if (existing) {
        // Already open — bring to front
        zCounter.current += 1
        return prev.map(w => w.id === key ? { ...w, zIndex: zCounter.current, data: { ...w.data, ...data } } : w)
      }

      // sameWindow mode: replace the last window of same type
      if (sameWindow && prev.length > 0) {
        const sameTypeIdx = prev.findLastIndex(w => w.type === type)
        if (sameTypeIdx >= 0) {
          zCounter.current += 1
          const newWindow = {
            id: key, type, entityId, data,
            zIndex: zCounter.current,
            defaultPos: getCenterPos(0),
            _tileKey: Date.now(),
          }
          const next = [...prev]
          next[sameTypeIdx] = newWindow
          return next
        }
      }

      // New window — centered with slight cascade offset
      const defaultPos = getCenterPos(prev.length % 8)

      zCounter.current += 1
      const newWindow = {
        id: key, type, entityId, data,
        zIndex: zCounter.current,
        defaultPos,
      }

      let next = [...prev, newWindow]
      if (next.length > MAX_WINDOWS) {
        next = next.slice(next.length - MAX_WINDOWS)
      }
      return next
    })
  }, [sameWindow, getCenterPos])

  const closeWindow = useCallback((id) => {
    // Remove saved position so next open starts centered
    try { localStorage.removeItem(`ucm-detail-${id}`) } catch {}
    setWindows(prev => prev.filter(w => w.id !== id))
  }, [])

  const closeAll = useCallback(() => {
    setWindows(prev => {
      prev.forEach(w => {
        try { localStorage.removeItem(`ucm-detail-${w.id}`) } catch {}
      })
      try { localStorage.removeItem('ucm-detail-single') } catch {}
      return []
    })
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
      const gap = 12
      const sidebarW = 56
      const headerH = 48
      const footerH = 32
      const startX = sidebarW + gap
      const startY = headerH + gap
      const tileW = 442
      const tileH = 425
      const maxCols = Math.max(1, Math.floor((window.innerWidth - startX - gap) / (tileW + gap)))
      const count = prev.length
      const cols = Math.min(count, maxCols)
      const rows = Math.ceil(count / cols)

      return prev.map((w, i) => {
        const col = i % cols
        const row = Math.floor(i / cols)
        return {
          ...w,
          defaultPos: {
            x: startX + col * (tileW + gap),
            y: startY + row * (tileH + gap),
            w: tileW,
            h: tileH,
          },
          _tileKey: Date.now() + i,
        }
      })
    })
  }, [])

  const stackWindows = useCallback(() => {
    setWindows(prev => prev.map((w, i) => ({
      ...w,
      defaultPos: getCenterPos(i),
      _tileKey: Date.now() + i,
    })))
  }, [getCenterPos])

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
      // Options
      sameWindow,
      closeOnNav,
      toggleSameWindow,
      toggleCloseOnNav,
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
