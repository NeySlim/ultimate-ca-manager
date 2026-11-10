/**
 * Inspector: the objects opened for detail (certificate, CA, trusted
 * certificate, user certificate), the active one and the dock geometry.
 * Position and size follow the user (server preference `inspector`), with a
 * local copy when the server is unreachable.
 */
import { createContext, useContext, useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { useAuth } from './AuthContext'
import { getPreferences, persistPreference, subscribePreferences } from '../stores/userPreferencesStore'

const InspectorContext = createContext(null)

export const MAX_OPEN = 8
export const SIZE_LIMITS = { height: [200, 4000], width: [360, 720] }
const DEFAULTS = { position: 'bottom', height: 380, width: 520 }
const PREFS_KEY = 'ucm-inspector-prefs'

const keyOf = (type, id) => `${type}:${id}`

// Keep only what the server would accept; anything else falls back to the default
export function cleanGeometry(raw) {
  const out = {}
  if (!raw || typeof raw !== 'object') return out
  if (raw.position === 'bottom' || raw.position === 'right') out.position = raw.position
  for (const k of ['height', 'width']) {
    const [lo, hi] = SIZE_LIMITS[k]
    if (Number.isInteger(raw[k]) && raw[k] >= lo && raw[k] <= hi) out[k] = raw[k]
  }
  return out
}

function readLocal() {
  try { return cleanGeometry(JSON.parse(localStorage.getItem(PREFS_KEY))) } catch { return {} }
}
function readLocalCloseOnNav() {
  try { return JSON.parse(localStorage.getItem(PREFS_KEY))?.closeOnNav ?? true } catch { return true }
}
function writeLocal(patch) {
  try {
    const cur = JSON.parse(localStorage.getItem(PREFS_KEY)) || {}
    localStorage.setItem(PREFS_KEY, JSON.stringify({ ...cur, ...patch }))
  } catch { /* storage unavailable: the server copy still applies */ }
}

export function InspectorProvider({ children }) {
  const { isAuthenticated } = useAuth()
  const [opened, setOpened] = useState([])
  const [activeKey, setActiveKey] = useState(null)
  const [geometry, setGeometry] = useState(() => ({ ...DEFAULTS, ...readLocal(), ...cleanGeometry(getPreferences().inspector) }))
  const [closeOnNav, setCloseOnNav] = useState(readLocalCloseOnNav)
  const [focusToken, setFocusToken] = useState(0)
  const origins = useRef(new Map())
  const openedRef = useRef([])
  const geometryRef = useRef(geometry)
  const activeRef = useRef(null)
  activeRef.current = activeKey

  // The server copy arrives after sign-in and wins over the local one
  useEffect(() => subscribePreferences((prefs) => {
    const server = cleanGeometry(prefs.inspector)
    if (!Object.keys(server).length) return
    geometryRef.current = { ...geometryRef.current, ...server }
    setGeometry(geometryRef.current)
  }), [])

  // `origin` names the control to refocus on close when it is not the one focused now (the palette)
  const openEntity = useCallback((type, entityId, { data, origin } = {}) => {
    if (entityId == null) return
    const key = keyOf(type, entityId)
    const from = origin || document.activeElement
    // The latest opening of an object names its origin
    if (from && from !== document.body && !from.closest?.('[data-testid="inspector-dock"], [data-inspector-control]')) origins.current.set(key, from)
    if (!openedRef.current.some((o) => o.key === key)) {
      const next = [...openedRef.current, { key, type, entityId, data: data || null }]
      openedRef.current = next.length > MAX_OPEN ? next.slice(next.length - MAX_OPEN) : next
      // An object pushed out by the limit takes its origin with it
      for (const k of [...origins.current.keys()]) if (!openedRef.current.some((o) => o.key === k)) origins.current.delete(k)
      setOpened(openedRef.current)
    }
    setActiveKey(key)
    setFocusToken((n) => n + 1)
  }, [])

  const closeEntity = useCallback((key) => {
    const list = openedRef.current
    const idx = list.findIndex((o) => o.key === key)
    if (idx < 0) return
    const next = list.filter((o) => o.key !== key)
    const origin = origins.current.get(key)
    origins.current.delete(key)
    const focused = document.activeElement
    const focusInDock = !focused || focused === document.body || !!focused.closest?.('[data-testid="inspector-dock"], [data-inspector-control]')
    openedRef.current = next
    setOpened(next)
    setActiveKey((cur) => (cur === key ? (next[Math.min(idx, next.length - 1)]?.key ?? null) : cur))
    // Last object closed: the focus goes back to the control that opened it
    if (!next.length && origin?.isConnected) queueMicrotask(() => origin.focus())
    // Another object stays open: the active tab takes the focus if the closed object
    // held it or the focus sat in the dock (an inactive tab's own close button)
    else if (next.length && (key === activeRef.current || focusInDock)) setFocusToken((n) => n + 1)
  }, [])

  const closeAll = useCallback(() => {
    // The opener of the active object, else the latest one still in the page, gets the focus back
    const cands = [origins.current.get(activeRef.current), ...[...origins.current.values()].reverse()]
    const origin = cands.find((o) => o?.isConnected)
    origins.current.clear()
    // Focus the operator moved elsewhere (a link, a field) is left alone; a control
    // that closes the inspector goes away with it and does not count
    const focused = document.activeElement
    const free = !focused || focused === document.body || !focused.isConnected
      || !!focused.closest?.('[data-testid="inspector-dock"], [data-inspector-control]')
    if (origin && free) queueMicrotask(() => origin.focus())
    openedRef.current = []
    setOpened([])
    setActiveKey(null)
  }, [])

  const setEntityData = useCallback((key, data) => {
    openedRef.current = openedRef.current.map((o) => (o.key === key ? { ...o, data } : o))
    setOpened(openedRef.current)
  }, [])

  // `persist: false` follows a drag in progress; the last call of the drag persists
  const updateGeometry = useCallback((patch, { persist = true } = {}) => {
    const cur = geometryRef.current
    const next = { ...cur, ...cleanGeometry({ ...cur, ...patch }) }
    geometryRef.current = next
    setGeometry(next)
    if (!persist) return
    writeLocal(next)
    persistPreference('inspector', { position: next.position, height: next.height, width: next.width })
  }, [])

  const toggleCloseOnNav = useCallback(() => {
    setCloseOnNav((prev) => { writeLocal({ closeOnNav: !prev }); return !prev })
  }, [])

  // Nothing stays open across a sign-out
  useEffect(() => { if (!isAuthenticated) closeAll() }, [isAuthenticated, closeAll])

  const value = useMemo(() => ({
    opened, activeKey, setActiveKey, openEntity, closeEntity, closeAll, setEntityData,
    openCount: opened.length, focusToken,
    ...geometry, setGeometry: updateGeometry,
    closeOnNav, toggleCloseOnNav,
  }), [opened, activeKey, openEntity, closeEntity, closeAll, setEntityData, focusToken, geometry, updateGeometry, closeOnNav, toggleCloseOnNav])

  return <InspectorContext.Provider value={value}>{children}</InspectorContext.Provider>
}

export function useInspector() {
  const ctx = useContext(InspectorContext)
  if (!ctx) throw new Error('useInspector must be used within InspectorProvider')
  return ctx
}
