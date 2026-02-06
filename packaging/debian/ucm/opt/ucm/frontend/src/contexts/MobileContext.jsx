/**
 * Mobile Context - Manages responsive layout state
 * 
 * Breakpoints:
 * - Mobile: < 768px (phones)
 * - Tablet: 768px - 1023px (tablets, small laptops)
 * - Desktop: 1024px - 1439px (standard laptops)
 * - Large: >= 1440px (large monitors)
 * 
 * Touch detection for input method
 */
import { createContext, useContext, useState, useEffect, useCallback } from 'react'

const MobileContext = createContext(null)

// Breakpoint values (matching Tailwind defaults)
const BREAKPOINTS = {
  sm: 640,
  md: 768,
  lg: 1024,
  xl: 1280,
  '2xl': 1536
}

export function MobileProvider({ children }) {
  const [screenSize, setScreenSize] = useState({
    width: typeof window !== 'undefined' ? window.innerWidth : 1024,
    height: typeof window !== 'undefined' ? window.innerHeight : 768
  })
  const [isTouch, setIsTouch] = useState(false)
  const [explorerOpen, setExplorerOpen] = useState(false)

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
      if (width >= BREAKPOINTS.lg) {
        setExplorerOpen(false)
      }
    }
    
    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  // Computed values
  const isMobile = screenSize.width < BREAKPOINTS.lg  // < 1024px
  const isTablet = screenSize.width >= BREAKPOINTS.md && screenSize.width < BREAKPOINTS.lg  // 768-1023px
  const isDesktop = screenSize.width >= BREAKPOINTS.lg  // >= 1024px
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
    isMobile,       // < 1024px (phones + tablets)
    isTablet,       // 768px - 1023px
    isDesktop,      // >= 1024px
    isLargeScreen,  // >= 1280px
    isExtraLarge,   // >= 1536px
    isTouch,        // Touch-capable device
    
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
