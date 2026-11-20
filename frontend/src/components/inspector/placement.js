/**
 * Where the inspector sits: in the page flow at the bottom or on the right, full
 * screen on mobile, or nowhere while nothing is open. The shell and the dock read
 * the same answer, so the page and the dock never disagree on the layout.
 */
import { createContext, useContext, useEffect, useState } from 'react'
import { useInspector } from '../../contexts/InspectorContext'
import { useMobile } from '../../contexts/MobileContext'

// The right dock needs room for the list beside it: narrower windows fall back to the bottom
export const RIGHT_MIN_VIEWPORT = 1400

export function useViewport() {
  const [viewport, setViewport] = useState(() => ({ w: window.innerWidth, h: window.innerHeight }))
  useEffect(() => {
    const onResize = () => setViewport({ w: window.innerWidth, h: window.innerHeight })
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  return viewport
}

/** 'bottom' | 'right' | 'mobile', or null while no object is open. */
export function useDockPlacement() {
  const { opened, position } = useInspector()
  const { isMobile } = useMobile()
  const { w } = useViewport()
  if (!opened.length) return null
  if (isMobile) return 'mobile'
  return position === 'right' && w >= RIGHT_MIN_VIEWPORT ? 'right' : 'bottom'
}

// The detail panels lay out in one column when the dock is narrow (right, mobile)
export const DockPlacementContext = createContext('bottom')
export const useDockPlacementContext = () => useContext(DockPlacementContext)
