/**
 * SlideOver Component - Unified responsive detail/filter panel
 * 
 * DESKTOP:
 * - Slim inline panel from right edge
 * - Smooth width animation (200ms)
 * - Compact header (py-2.5)
 * - Fine hover states, keyboard support
 * - Width configurable: narrow (w-72), default (w-80-96), wide (w-96-480)
 * 
 * MOBILE:
 * - Full-screen overlay sliding from right
 * - Touch-friendly header (h-14, 44px buttons)
 * - Swipe right to close
 * - Back arrow navigation
 * - Native feel with momentum scrolling
 * 
 * Features:
 * - Keyboard: Escape to close
 * - Focus management
 * - ARIA attributes for accessibility
 * - CSS transitions (no JS animation libraries)
 * 
 * Usage:
 * <SlideOver
 *   open={showDetails}
 *   onClose={() => setShowDetails(false)}
 *   title="Certificate Details"
 *   subtitle="server.example.com"
 *   width="default"
 * >
 *   <CertificateDetails cert={selectedCert} />
 * </SlideOver>
 */
import { useEffect, useRef, useCallback, useState } from 'react'
import { X, ArrowLeft } from '@phosphor-icons/react'
import { cn } from '../lib/utils'
import { useMobile } from '../contexts'

// Width presets for desktop
const WIDTH_CLASSES = {
  narrow: 'w-72 xl:w-80',
  default: 'w-80 xl:w-96 2xl:w-[420px]',
  wide: 'w-96 xl:w-[450px] 2xl:w-[520px]',
  full: 'w-full max-w-lg'
}

export function SlideOver({
  open,
  onClose,
  title,
  subtitle,
  children,
  // Header actions (desktop: inline icons, mobile: hidden or in menu)
  headerActions,
  // Footer content (both desktop and mobile)
  footer,
  // Width preset for desktop
  width = 'default',
  // Custom class
  className,
  // Accessibility
  'aria-label': ariaLabel,
  // ID for linking
  id
}) {
  const { isMobile } = useMobile()
  const panelRef = useRef(null)
  const [isClosing, setIsClosing] = useState(false)
  
  // Touch tracking for swipe-to-close
  const touchStartX = useRef(0)
  const touchDeltaX = useRef(0)
  const isDragging = useRef(false)

  // ============================================
  // KEYBOARD: Escape to close
  // ============================================
  useEffect(() => {
    if (!open) return
    
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        e.stopPropagation()
        handleClose()
      }
    }
    
    document.addEventListener('keydown', handleKeyDown, true)
    return () => document.removeEventListener('keydown', handleKeyDown, true)
  }, [open])

  // ============================================
  // FOCUS: Focus panel when opened
  // ============================================
  useEffect(() => {
    if (open && panelRef.current) {
      // Small delay to allow animation to start
      const timer = setTimeout(() => {
        panelRef.current?.focus()
      }, 50)
      return () => clearTimeout(timer)
    }
  }, [open])

  // ============================================
  // BODY SCROLL: Prevent on mobile when open
  // ============================================
  useEffect(() => {
    if (isMobile && open) {
      document.body.style.overflow = 'hidden'
      return () => {
        document.body.style.overflow = ''
      }
    }
  }, [isMobile, open])

  // ============================================
  // CLOSE HANDLER: With animation support
  // ============================================
  const handleClose = useCallback(() => {
    if (isClosing) return
    setIsClosing(true)
    
    // Allow animation to complete before calling onClose
    setTimeout(() => {
      setIsClosing(false)
      onClose?.()
    }, 200) // Match CSS transition duration
  }, [onClose, isClosing])

  // ============================================
  // MOBILE: Touch handlers for swipe-to-close
  // ============================================
  const handleTouchStart = useCallback((e) => {
    if (!isMobile) return
    touchStartX.current = e.touches[0].clientX
    touchDeltaX.current = 0
    isDragging.current = true
  }, [isMobile])

  const handleTouchMove = useCallback((e) => {
    if (!isDragging.current || !isMobile) return
    
    const currentX = e.touches[0].clientX
    const delta = currentX - touchStartX.current
    
    // Only allow dragging to the right (positive delta)
    if (delta > 0) {
      touchDeltaX.current = delta
      if (panelRef.current) {
        panelRef.current.style.transform = `translateX(${delta}px)`
        panelRef.current.style.transition = 'none'
      }
    }
  }, [isMobile])

  const handleTouchEnd = useCallback(() => {
    if (!isDragging.current || !isMobile) return
    isDragging.current = false
    
    if (panelRef.current) {
      panelRef.current.style.transition = ''
      panelRef.current.style.transform = ''
    }
    
    // Close if swiped more than 100px to the right
    if (touchDeltaX.current > 100) {
      handleClose()
    }
  }, [isMobile, handleClose])

  // Determine actual open state (considering closing animation)
  const visuallyOpen = open && !isClosing

  // ============================================
  // MOBILE LAYOUT
  // ============================================
  if (isMobile) {
    return (
      <>
        {/* Backdrop with fade */}
        <div 
          className={cn(
            "fixed inset-0 z-40 bg-black/40 transition-opacity duration-200",
            visuallyOpen ? "opacity-100" : "opacity-0 pointer-events-none"
          )}
          onClick={handleClose}
          aria-hidden="true"
        />
        
        {/* Full-screen panel */}
        <div
          ref={panelRef}
          id={id}
          tabIndex={-1}
          role="dialog"
          aria-modal="true"
          aria-label={ariaLabel || title}
          className={cn(
            "fixed inset-0 z-50 bg-bg-primary flex flex-col outline-none",
            "transition-transform duration-200 ease-out",
            visuallyOpen ? "translate-x-0" : "translate-x-full",
            className
          )}
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
        >
          {/* Header - Touch-friendly (56px / 3.5rem) */}
          <header className="shrink-0 h-14 px-4 flex items-center gap-3 border-b border-border bg-bg-secondary">
            {/* Back button - 44px touch target */}
            <button
              type="button"
              onClick={handleClose}
              className={cn(
                "w-11 h-11 -ml-2 flex items-center justify-center rounded-lg",
                "text-text-secondary hover:text-text-primary",
                "hover:bg-bg-tertiary active:bg-bg-tertiary",
                "transition-colors focus:outline-none focus:ring-2 focus:ring-accent-primary/50"
              )}
              aria-label="Close panel"
            >
              <ArrowLeft size={22} weight="bold" />
            </button>
            
            {/* Title area */}
            <div className="flex-1 min-w-0">
              <h2 className="text-base font-semibold text-text-primary truncate">
                {title}
              </h2>
              {subtitle && (
                <p className="text-xs text-text-tertiary truncate">{subtitle}</p>
              )}
            </div>
            
            {/* Optional actions */}
            {headerActions && (
              <div className="flex items-center gap-1">
                {headerActions}
              </div>
            )}
          </header>
          
          {/* Content - Scrollable with momentum */}
          <main 
            className="flex-1 overflow-auto overscroll-contain"
            style={{ WebkitOverflowScrolling: 'touch' }}
          >
            {children}
          </main>
          
          {/* Footer - Optional, fixed at bottom */}
          {footer && (
            <footer className="shrink-0 border-t border-border bg-bg-secondary p-4">
              {footer}
            </footer>
          )}
        </div>
      </>
    )
  }

  // ============================================
  // DESKTOP LAYOUT
  // ============================================
  return (
    <aside
      ref={panelRef}
      id={id}
      tabIndex={-1}
      role="complementary"
      aria-label={ariaLabel || title}
      className={cn(
        "border-l border-border bg-bg-secondary flex flex-col shrink-0 outline-none",
        "transition-all duration-200 ease-out overflow-hidden",
        visuallyOpen ? WIDTH_CLASSES[width] : "w-0 border-l-0",
        className
      )}
    >
      {visuallyOpen && (
        <>
          {/* Header - Compact (40px) */}
          <header className="shrink-0 px-4 py-2.5 border-b border-border">
            <div className="flex items-center justify-between gap-2">
              {/* Title */}
              <div className="flex-1 min-w-0">
                <h2 className="text-sm font-semibold text-text-primary truncate">
                  {title}
                </h2>
                {subtitle && (
                  <p className="text-[11px] text-text-tertiary truncate mt-0.5">{subtitle}</p>
                )}
              </div>
              
              {/* Actions + Close */}
              <div className="flex items-center gap-1 shrink-0">
                {headerActions}
                <button
                  type="button"
                  onClick={handleClose}
                  className={cn(
                    "w-6 h-6 flex items-center justify-center rounded",
                    "text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary",
                    "transition-colors focus:outline-none focus:ring-2 focus:ring-accent-primary/50"
                  )}
                  title="Close (Esc)"
                  aria-label="Close panel"
                >
                  <X size={14} />
                </button>
              </div>
            </div>
          </header>
          
          {/* Content - Scrollable */}
          <main className="flex-1 overflow-auto">
            {children}
          </main>
          
          {/* Footer - Optional */}
          {footer && (
            <footer className="shrink-0 px-3 py-2 border-t border-border bg-bg-tertiary/50 text-xs text-text-secondary">
              {footer}
            </footer>
          )}
        </>
      )}
    </aside>
  )
}

// ============================================
// SLIDE OVER CONTENT HELPERS
// ============================================

/**
 * Section with title - for grouping content
 */
export function SlideOverSection({ 
  title, 
  children, 
  className,
  defaultOpen = true 
}) {
  return (
    <section className={cn("border-b border-border last:border-b-0", className)}>
      {title && (
        <div className="px-4 py-2 bg-bg-tertiary/30">
          <h3 className="text-[11px] font-semibold text-text-secondary uppercase tracking-wider">
            {title}
          </h3>
        </div>
      )}
      <div className="p-4">
        {children}
      </div>
    </section>
  )
}

/**
 * Key-value row for displaying details
 */
export function SlideOverRow({ 
  label, 
  value, 
  mono = false, 
  copyable = false,
  className 
}) {
  const handleCopy = () => {
    if (value && copyable) {
      navigator.clipboard.writeText(String(value))
    }
  }
  
  return (
    <div className={cn("flex items-start py-1.5 gap-3 group", className)}>
      <span className="text-xs text-text-tertiary w-28 shrink-0 pt-0.5">
        {label}
      </span>
      <span 
        className={cn(
          "text-sm text-text-primary flex-1 min-w-0 break-words",
          mono && "font-mono text-xs",
          copyable && "cursor-pointer hover:text-accent-primary"
        )}
        onClick={copyable ? handleCopy : undefined}
        title={copyable ? "Click to copy" : undefined}
      >
        {value || <span className="text-text-tertiary">—</span>}
      </span>
    </div>
  )
}

/**
 * Badge row - for status or tags
 */
export function SlideOverBadges({ label, children, className }) {
  return (
    <div className={cn("flex items-start py-1.5 gap-3", className)}>
      <span className="text-xs text-text-tertiary w-28 shrink-0 pt-1">
        {label}
      </span>
      <div className="flex-1 flex flex-wrap gap-1.5">
        {children}
      </div>
    </div>
  )
}

/**
 * Action buttons row
 */
export function SlideOverActions({ children, className }) {
  return (
    <div className={cn("flex flex-wrap gap-2 p-4 border-t border-border bg-bg-tertiary/30", className)}>
      {children}
    </div>
  )
}

export default SlideOver
