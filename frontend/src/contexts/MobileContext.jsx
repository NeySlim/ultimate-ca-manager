/**
 * Mobile Context - Manages mobile layout state
 */
import { createContext, useContext, useState, useEffect, useCallback } from 'react'

const MobileContext = createContext(null)

export function MobileProvider({ children }) {
  const [isMobile, setIsMobile] = useState(false)
  const [explorerOpen, setExplorerOpen] = useState(false)

  useEffect(() => {
    const checkMobile = () => {
      const mobile = window.innerWidth < 1024
      setIsMobile(mobile)
      // Close explorer when switching to desktop
      if (!mobile) setExplorerOpen(false)
    }
    checkMobile()
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [])

  // Close explorer when item is selected (for mobile)
  const closeOnSelect = useCallback(() => {
    if (isMobile) {
      setExplorerOpen(false)
    }
  }, [isMobile])

  const value = {
    isMobile,
    explorerOpen,
    openExplorer: () => setExplorerOpen(true),
    closeExplorer: () => setExplorerOpen(false),
    toggleExplorer: () => setExplorerOpen(prev => !prev),
    closeOnSelect // Call this when an item is selected
  }

  return (
    <MobileContext.Provider value={value}>
      {children}
    </MobileContext.Provider>
  )
}

export function useMobile() {
  const context = useContext(MobileContext)
  if (!context) {
    // Return default values if not wrapped in provider
    return {
      isMobile: false,
      explorerOpen: false,
      openExplorer: () => {},
      closeExplorer: () => {},
      toggleExplorer: () => {},
      closeOnSelect: () => {}
    }
  }
  return context
}
