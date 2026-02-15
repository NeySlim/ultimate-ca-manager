/**
 * useFloatingWindow — RAF-based drag & resize hook for floating panels
 * 
 * Extracted from FloatingHelpPanel to be shared across:
 * - FloatingHelpPanel (help system)
 * - FloatingDetailWindow (certificate/CA/trust store detail windows)
 * 
 * Features:
 * - RAF-batched transforms (zero React re-renders during drag/resize)
 * - 8-directional resize (n, s, e, w, ne, nw, se, sw)
 * - Viewport clamping
 * - localStorage persistence
 * - Double-click maximize/restore
 */
import { useRef, useState, useCallback, useEffect } from 'react'

const DEFAULT_CONSTRAINTS = {
  minW: 420,
  maxW: 800,
  minH: 280,
  defW: 500,
  defH: 460,
}

export const EDGES = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']

export const EDGE_CURSORS = {
  n: 'ns-resize', s: 'ns-resize', e: 'ew-resize', w: 'ew-resize',
  ne: 'nesw-resize', nw: 'nwse-resize', se: 'nwse-resize', sw: 'nesw-resize',
}

export const EDGE_STYLES = {
  n: { top: -3, left: 8, right: 8, height: 6 },
  s: { bottom: -3, left: 8, right: 8, height: 6 },
  e: { top: 8, right: -3, bottom: 8, width: 6 },
  w: { top: 8, left: -3, bottom: 8, width: 6 },
  ne: { top: -3, right: -3, width: 14, height: 14 },
  nw: { top: -3, left: -3, width: 14, height: 14 },
  se: { bottom: -3, right: -3, width: 14, height: 14 },
  sw: { bottom: -3, left: -3, width: 14, height: 14 },
}

function loadSaved(storageKey) {
  try { return JSON.parse(localStorage.getItem(storageKey)) } catch { return null }
}

function savePersist(storageKey, pos) {
  try { localStorage.setItem(storageKey, JSON.stringify(pos)) } catch {}
}

/**
 * @param {Object} options
 * @param {string} options.storageKey - localStorage key for persistence
 * @param {Object} [options.defaultPos] - { x, y, w, h } initial position
 * @param {Object} [options.constraints] - { minW, maxW, minH, defW, defH }
 * @param {React.RefObject} options.panelRef - ref to the panel DOM element
 * @param {React.RefObject} [options.bodyRef] - ref to the body (disable pointer-events during drag)
 * @param {boolean} [options.minimized] - whether panel is minimized
 */
export function useFloatingWindow({
  storageKey,
  defaultPos,
  forcePosition = false,
  constraints: userConstraints,
  panelRef,
  bodyRef,
  minimized = false,
}) {
  const constraints = { ...DEFAULT_CONSTRAINTS, ...userConstraints }
  const posRef = useRef(null)
  const isDragging = useRef(false)
  const preMaximizeRef = useRef(null)
  const [, forceUpdate] = useState(0)

  // Init position — forcePosition skips localStorage (used by tile/cascade)
  if (!posRef.current) {
    const saved = forcePosition ? null : loadSaved(storageKey)
    posRef.current = saved || defaultPos || {
      x: window.innerWidth - constraints.defW - 24,
      y: window.innerHeight - constraints.defH - 24,
      w: constraints.defW,
      h: constraints.defH,
    }
  }

  const clamp = useCallback((p) => {
    const vw = window.innerWidth, vh = window.innerHeight
    return {
      x: Math.max(0, Math.min(p.x, vw - 100)),
      y: Math.max(0, Math.min(p.y, vh - 48)),
      w: Math.max(constraints.minW, Math.min(p.w, Math.min(constraints.maxW, vw - 20))),
      h: Math.max(constraints.minH, Math.min(p.h, vh - 40)),
    }
  }, [constraints.minW, constraints.maxW, constraints.minH])

  const applyPos = useCallback(() => {
    const el = panelRef.current
    if (!el) return
    const p = posRef.current
    el.style.transform = `translate3d(${p.x}px, ${p.y}px, 0)`
    el.style.width = p.w + 'px'
    if (!minimized) el.style.height = p.h + 'px'
  }, [panelRef, minimized])

  // Apply on mount
  useEffect(() => { applyPos() }, [applyPos])

  // --- DRAG ---
  const onDragStart = useCallback((e) => {
    if (e.button !== 0) return
    e.preventDefault()
    const sx = e.clientX, sy = e.clientY
    const sp = { ...posRef.current }
    let raf = 0

    document.body.style.userSelect = 'none'
    isDragging.current = true
    if (bodyRef?.current) bodyRef.current.style.pointerEvents = 'none'

    const onMove = (e) => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => {
        posRef.current = clamp({ ...sp, x: sp.x + e.clientX - sx, y: sp.y + e.clientY - sy })
        applyPos()
      })
    }
    const onUp = () => {
      cancelAnimationFrame(raf)
      isDragging.current = false
      document.body.style.userSelect = ''
      if (bodyRef?.current) bodyRef.current.style.pointerEvents = ''
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      savePersist(storageKey, posRef.current)
      forceUpdate(n => n + 1)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [clamp, applyPos, storageKey, bodyRef])

  // --- RESIZE ---
  const onResizeStart = useCallback((edge, e) => {
    e.preventDefault()
    e.stopPropagation()
    const sx = e.clientX, sy = e.clientY
    const sp = { ...posRef.current }
    let raf = 0

    document.body.style.userSelect = 'none'
    const onMove = (e) => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => {
        const dx = e.clientX - sx, dy = e.clientY - sy
        let next = { ...sp }
        if (edge.includes('e')) next.w = sp.w + dx
        if (edge.includes('w')) { next.x = sp.x + dx; next.w = sp.w - dx }
        if (edge.includes('s')) next.h = sp.h + dy
        if (edge.includes('n')) { next.y = sp.y + dy; next.h = sp.h - dy }
        posRef.current = clamp(next)
        applyPos()
      })
    }
    const onUp = () => {
      cancelAnimationFrame(raf)
      document.body.style.userSelect = ''
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      savePersist(storageKey, posRef.current)
      forceUpdate(n => n + 1)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [clamp, applyPos, storageKey])

  // --- MAXIMIZE/RESTORE (double-click header) ---
  const toggleMaximize = useCallback(() => {
    if (preMaximizeRef.current) {
      // Restore
      posRef.current = preMaximizeRef.current
      preMaximizeRef.current = null
    } else {
      // Maximize
      preMaximizeRef.current = { ...posRef.current }
      const margin = 16
      posRef.current = clamp({
        x: margin, y: margin,
        w: window.innerWidth - margin * 2,
        h: window.innerHeight - margin * 2,
      })
    }
    applyPos()
    savePersist(storageKey, posRef.current)
    forceUpdate(n => n + 1)
  }, [clamp, applyPos, storageKey])

  return {
    posRef,
    isDragging,
    applyPos,
    onDragStart,
    onResizeStart,
    toggleMaximize,
    isMaximized: !!preMaximizeRef.current,
    getPos: () => posRef.current,
    setPos: (newPos) => {
      posRef.current = clamp(newPos)
      applyPos()
      savePersist(storageKey, posRef.current)
    },
  }
}
