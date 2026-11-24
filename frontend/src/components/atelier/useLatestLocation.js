/**
 * The address as the router's history holds it now. The browser router draws a new URL in a
 * transition: until then useLocation() is the last one drawn, and a write built on it drops what
 * another component (the dock, the page's search) wrote meanwhile.
 */
import { useCallback, useContext, useEffect, useRef } from 'react'
import { UNSAFE_NavigationContext, parsePath, useLocation, useNavigate } from 'react-router-dom'

// Per history: the last address written through useLatestNavigate and the drawn address it was written over
const written = new WeakMap()

// react-router's own stripBasename: case-insensitive, and only at a segment boundary
function stripBasename(pathname, basename) {
  if (basename === '/') return pathname
  if (!pathname.toLowerCase().startsWith(basename.toLowerCase())) return null
  const start = basename.endsWith('/') ? basename.length - 1 : basename.length
  const next = pathname.charAt(start)
  if (next && next !== '/') return null
  return pathname.slice(start) || '/'
}

export function useLatestLocation() {
  const rendered = useLocation()
  const { navigator, basename = '/' } = useContext(UNSAFE_NavigationContext)
  const drawn = useRef(rendered)
  drawn.current = rendered
  return useCallback(() => {
    const at = drawn.current
    const live = navigator?.location
    if (!live || typeof live.search !== 'string') {
      // Without the history's own address, the last write over the drawn one stands for it (an entry not drawn yet: no key)
      const last = navigator && written.get(navigator)
      return last && last.over === at.key && last.to.pathname === at.pathname ? { ...last.to, key: undefined } : at
    }
    // Another page's address says nothing of this one's parameters
    if (stripBasename(live.pathname, basename) !== at.pathname) return at
    return { ...live, pathname: at.pathname }
  }, [navigator, basename])
}

/** useNavigate() that notes each address it writes, the second source of useLatestLocation(). */
export function useLatestNavigate() {
  const navigate = useNavigate()
  const rendered = useLocation()
  const { navigator } = useContext(UNSAFE_NavigationContext)
  const drawn = useRef(rendered)
  drawn.current = rendered
  // A new entry drawn ends the note: a step back to the entry it was written over must not bring it back
  useEffect(() => {
    const note = navigator && written.get(navigator)
    if (note && note.over !== rendered.key) written.delete(navigator)
  }, [navigator, rendered.key])
  return useCallback((to, options = {}) => {
    if (navigator) {
      if (typeof to === 'number') written.delete(navigator)
      else {
        const { pathname = drawn.current.pathname, search = '', hash = '' } = typeof to === 'string' ? parsePath(to) : to
        written.set(navigator, { over: drawn.current.key, to: { pathname, search, hash, state: options.state ?? null } })
      }
    }
    return navigate(to, options)
  }, [navigate, navigator])
}

export default useLatestLocation
