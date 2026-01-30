/**
 * Mobile Context - Manages responsive layout state
 */
import { createContext, useContext, useState, useEffect, useCallback } from 'react'

const MobileContext = createContext(null)

export function MobileProvider({ children }) {
  const [isMobile, setIsMobile] = useState(false)
  const [isLargeScreen, setIsLargeScreen] = useState(false)
  const [explorerOpen, setExplorerOpen] = useState(false)

  useEffect(() => {
    const checkScreen = () => {
      const width = window.innerWidth
      const mobile = width < 1024
      const large = width >= 1300
      setIsMobile(mobile)
      setIsLargeScreen(large)
      // Close explorer when switching to desktop
      if (!mobile) setExplorerOpen(false)
    }
    checkScreen()
    window.addEventListener('resize', checkScreen)
    return () => window.removeEventListener('resize', checkScreen)
  }, [])

  // Close explorer when item is selected (for mobile)
  const closeOnSelect = useCallback(() => {
    if (isMobile) {
      setExplorerOpen(false)
    }
  }, [isMobile])

  const value = {
    isMobile,
    isLargeScreen, // >= 1300px
    explorerOpen,
    openExplorer: () => setExplorerOpen(true),
    closeExplorer: () => setExplorerOpen(false),
    toggleExplorer: () => setExplorerOpen(prev => !prev),
    closeOnSelect
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
    return {
      isMobile: false,
      isLargeScreen: false,
      explorerOpen: false,
      openExplorer: () => {},
      closeExplorer: () => {},
      toggleExplorer: () => {},
      closeOnSelect: () => {}
    }
  }
  return context
}
