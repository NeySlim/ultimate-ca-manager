/**
 * Mobile Context - Manages responsive layout state
 * 
 * Breakpoints:
 * - Mobile: < 640px (phones)
 * - Tablet: 640px - 899px (tablets, small windows)
 * - Desktop: >= 900px (laptops, desktops)
 * - Large: >= 1280px (large monitors)
 * 
 * Touch detection for input method
 * Force Desktop Mode: User preference to disable responsive mobile layout
 */
import { createContext, useContext, useState, useEffect, useCallback } from 'react'

const MobileContext = createContext(null)

// Breakpoint values (adjusted for better PC experience)
const BREAKPOINTS = {
  sm: 640,   // Mobile threshold
  md: 768,   // Tailwind md
  lg: 900,   // Desktop threshold (lowered from 1024)
  xl: 1280,
  '2xl': 1536
}

// LocalStorage key for force desktop preference
const FORCE_DESKTOP_KEY = 'ucm-force-desktop-mode'

export function MobileProvider({ children }) {
  const [screenSize, setScreenSize] = useState({
    width: typeof window !== 'undefined' ? window.innerWidth : 1024,
    height: typeof window !== 'undefined' ? window.innerHeight : 768
  })
  const [isTouch, setIsTouch] = useState(false)
  const [explorerOpen, setExplorerOpen] = useState(false)
  
  // Force desktop mode preference
  const [forceDesktop, setForceDesktopState] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem(FORCE_DESKTOP_KEY) === 'true'
    }
    return false
  })

  // Toggle force desktop mode with persistence
  const setForceDesktop = useCallback((value) => {
    setForceDesktopState(value)
    if (typeof window !== 'undefined') {
      if (value) {
        localStorage.setItem(FORCE_DESKTOP_KEY, 'true')
      } else {
        localStorage.removeItem(FORCE_DESKTOP_KEY)
      }
    }
  }, [])

  // Detect touch device
  useEffect(() => {
    const checkTouch = () => {
      setIsTouch(
        'ontouchstart' in window || 
        navigator.maxTouchPoints > 0 ||
        window.matchMedia('(pointer: coarse)').matches
      )
    }
    checkTouch()
  }, [])

  // Track screen size
  useEffect(() => {
    const handleResize = () => {
      const width = window.innerWidth
      const height = window.innerHeight
      setScreenSize({ width, height })
      
      // Auto-close explorer when switching to desktop
      if (width >= BREAKPOINTS.lg || forceDesktop) {
        setExplorerOpen(false)
      }
    }
    
    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [forceDesktop])

  // Computed values - forceDesktop overrides responsive behavior
  const isMobile = forceDesktop ? false : screenSize.width < BREAKPOINTS.lg  // < 900px
  const isTablet = forceDesktop ? false : screenSize.width >= BREAKPOINTS.sm && screenSize.width < BREAKPOINTS.lg  // 640-899px
  const isDesktop = forceDesktop ? true : screenSize.width >= BREAKPOINTS.lg  // >= 900px
  const isLargeScreen = screenSize.width >= BREAKPOINTS.xl  // >= 1280px
  const isExtraLarge = screenSize.width >= BREAKPOINTS['2xl']  // >= 1536px

  // Close explorer when item is selected (for mobile navigation)
  const closeOnSelect = useCallback(() => {
    if (isMobile) {
      setExplorerOpen(false)
    }
  }, [isMobile])

  // Get optimal panel width based on screen size
  const getPanelWidth = useCallback((preset = 'default') => {
    const presets = {
      narrow: { base: 288, lg: 320 },  // w-72, xl:w-80
      default: { base: 320, lg: 384, xl: 420 },  // w-80, xl:w-96, 2xl:w-[420px]
      wide: { base: 384, lg: 450, xl: 520 }  // w-96, xl:w-[450px], 2xl:w-[520px]
    }
    const sizes = presets[preset] || presets.default
    
    if (isExtraLarge && sizes.xl) return sizes.xl
    if (isLargeScreen && sizes.lg) return sizes.lg
    return sizes.base
  }, [isLargeScreen, isExtraLarge])

  const value = {
    // Screen info
    screenWidth: screenSize.width,
    screenHeight: screenSize.height,
    
    // Device type flags
    isMobile,       // < 900px (phones + tablets) - unless forceDesktop
    isTablet,       // 640px - 899px - unless forceDesktop
    isDesktop,      // >= 900px OR forceDesktop
    isLargeScreen,  // >= 1280px
    isExtraLarge,   // >= 1536px
    isTouch,        // Touch-capable device
    
    // Force desktop mode
    forceDesktop,
    setForceDesktop,
    toggleForceDesktop: () => setForceDesktop(!forceDesktop),
    
    // Explorer state (mobile menu)
    explorerOpen,
    openExplorer: () => setExplorerOpen(true),
    closeExplorer: () => setExplorerOpen(false),
    toggleExplorer: () => setExplorerOpen(prev => !prev),
    closeOnSelect,
    
    // Utilities
    getPanelWidth,
    breakpoints: BREAKPOINTS
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
    // Fallback for usage outside provider
    return {
      screenWidth: 1024,
      screenHeight: 768,
      isMobile: false,
      isTablet: false,
      isDesktop: true,
      isLargeScreen: false,
      isExtraLarge: false,
      isTouch: false,
      forceDesktop: false,
      setForceDesktop: () => {},
      toggleForceDesktop: () => {},
      explorerOpen: false,
      openExplorer: () => {},
      closeExplorer: () => {},
      toggleExplorer: () => {},
      closeOnSelect: () => {},
      getPanelWidth: () => 320,
      breakpoints: BREAKPOINTS
    }
  }
  return context
}
