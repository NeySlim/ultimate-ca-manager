/**
 * The address as the router's history holds it now. The browser router draws a new URL in a
 * transition: until then useLocation() is the last one drawn, and a write built on it drops what
 * another component (the dock, the page's search) wrote meanwhile.
 */
import { useCallback, useContext, useRef } from 'react'
import { UNSAFE_NavigationContext, useLocation } from 'react-router-dom'

export function useLatestLocation() {
  const rendered = useLocation()
  const { navigator, basename = '/' } = useContext(UNSAFE_NavigationContext)
  const drawn = useRef(rendered)
  drawn.current = rendered
  return useCallback(() => {
    const at = drawn.current
    const live = navigator?.location
    if (!live || typeof live.search !== 'string') return at
    // Another page's address says nothing of this one's parameters
    const path = basename !== '/' && live.pathname.startsWith(basename) ? live.pathname.slice(basename.replace(/\/$/, '').length) || '/' : live.pathname
    if (path !== at.pathname) return at
    return { ...live, pathname: at.pathname }
  }, [navigator, basename])
}

export default useLatestLocation
