/**
 * The detached windows of the console: objects (a certificate, an authority, a request) and
 * comparisons shown in floating windows over the pages, several at once, the last touched in
 * front. Their list, order and geometry last the browser session (sessionStorage); a window
 * reopened later takes back its place. None on a phone (800 px and under): the list stays, unseen.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMobile } from '../../contexts/MobileContext'
import { useAuth } from '../../contexts/AuthContext'
import { cascadeRect, clampRect, viewport } from './geometry'
import { DetachedContext, windowKey } from './useDetached'

const KEY = 'ucm-detached'

// The size a window opens at, by kind: a comparison takes the width of its columns
const SIZES = {
  compare: (view) => ({ w: Math.min(1120, view.w - 120), h: Math.min(600, view.h - 140) }),
  default: (view) => ({ w: Math.min(620, view.w - 120), h: Math.min(560, view.h - 140) }),
}

// The windows keep the order they opened in (the DOM never moves under a click); `z` says which is in front
const topZ = (windows) => windows.reduce((m, w) => Math.max(m, w.z || 0), 0)
function raise(s, key) {
  const w = s.windows.find((x) => x.key === key)
  const top = topZ(s.windows)
  if (!w || (w.z === top && s.windows.filter((x) => x.z === top).length === 1)) return s
  return { ...s, windows: s.windows.map((x) => (x === w ? { ...x, z: top + 1 } : x)) }
}

function readStored() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(KEY) || 'null')
    if (saved && Array.isArray(saved.windows) && saved.rects && typeof saved.rects === 'object') return saved
  } catch { /* storage refused or garbled: start empty */ }
  return { windows: [], rects: {} }
}

export function DetachedProvider({ children }) {
  const { isMobile } = useMobile()
  const auth = useAuth()
  const signedIn = !!auth?.isAuthenticated
  const [state, setState] = useState(readStored)
  const openers = useRef(new Map())
  // A window that asked to come forward takes the focus once drawn
  const [focusKey, setFocusKey] = useState(null)

  useEffect(() => {
    try { sessionStorage.setItem(KEY, JSON.stringify(state)) } catch { /* private mode */ }
  }, [state])

  // Nothing stays open across a sign-out; the session still being checked at load is not one
  const wasSignedIn = useRef(signedIn)
  useEffect(() => {
    if (wasSignedIn.current && !signedIn) setState({ windows: [], rects: {} })
    wasSignedIn.current = signedIn
  }, [signedIn])

  // A narrower browser window brings every window back inside it
  useEffect(() => {
    const onResize = () => setState((s) => {
      const view = viewport()
      const rects = Object.fromEntries(Object.entries(s.rects).map(([k, r]) => [k, clampRect(r, view)]))
      return { ...s, rects }
    })
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const open = useCallback((kind, ids, { title = '' } = {}) => {
    const key = windowKey(kind, ids)
    openers.current.set(key, document.activeElement)
    setState((s) => {
      const view = viewport()
      if (s.windows.some((w) => w.key === key)) return raise(s, key)
      const rect = s.rects[key] ? clampRect(s.rects[key], view) : cascadeRect(s.windows.length, (SIZES[kind] || SIZES.default)(view), view)
      return { windows: [...s.windows, { key, kind, ids: [].concat(ids), title, z: topZ(s.windows) + 1 }], rects: { ...s.rects, [key]: rect } }
    })
    setFocusKey(key)
    return key
  }, [])

  const close = useCallback((key) => {
    setState((s) => ({ ...s, windows: s.windows.filter((w) => w.key !== key) }))
    const back = openers.current.get(key)
    openers.current.delete(key)
    requestAnimationFrame(() => {
      if (back?.isConnected && back.getClientRects().length) back.focus()
    })
  }, [])

  const front = useCallback((key, { focus = false } = {}) => {
    setState((s) => raise(s, key))
    if (focus) setFocusKey(key)
  }, [])

  const place = useCallback((key, rect) => {
    setState((s) => ({ ...s, rects: { ...s.rects, [key]: clampRect(rect, viewport()) } }))
  }, [])

  const retitle = useCallback((key, title) => {
    setState((s) => (s.windows.some((w) => w.key === key && w.title !== title)
      ? { ...s, windows: s.windows.map((w) => (w.key === key ? { ...w, title } : w)) } : s))
  }, [])

  // An authority picked inside its window replaces it there, as a page would
  const replace = useCallback((key, ids) => {
    setState((s) => {
      const w = s.windows.find((x) => x.key === key)
      if (!w) return s
      const next = windowKey(w.kind, ids)
      if (s.windows.some((x) => x.key === next)) return raise({ ...s, windows: s.windows.filter((x) => x.key !== key) }, next)
      return {
        windows: s.windows.map((x) => (x.key === key ? { ...x, key: next, ids: [].concat(ids), title: '' } : x)),
        rects: { ...s.rects, [next]: s.rects[key] },
      }
    })
  }, [])

  const value = useMemo(() => ({
    available: !isMobile,
    windows: state.windows,
    rects: state.rects,
    focusKey,
    clearFocus: () => setFocusKey(null),
    open, close, front, place, retitle, replace,
  }), [isMobile, state, focusKey, open, close, front, place, retitle, replace])

  return <DetachedContext.Provider value={value}>{children}</DetachedContext.Provider>
}

export { useDetached } from './useDetached'
