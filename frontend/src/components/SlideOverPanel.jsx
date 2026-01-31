/**
 * SlideOverPanel - Animated panel that slides in from the right
 * 
 * Used for detail views, forms, and contextual content.
 * Automatically handles:
 * - Desktop: slide-over from right edge
 * - Mobile: full-screen overlay with back navigation
 * 
 * Usage:
 * <SlideOverPanel
 *   open={!!selectedItem}
 *   onClose={() => setSelectedItem(null)}
 *   title="Details"
 * >
 *   <DetailContent item={selectedItem} />
 * </SlideOverPanel>
 */
import { useState, useEffect, useCallback } from 'react'
import { cn } from '../lib/utils'
import { useMobile } from '../contexts'
import { X, ArrowLeft } from '@phosphor-icons/react'

export function SlideOverPanel({
  // State
  open = false,
  onClose,
  
  // Content
  title = 'Details',
  children,
  
  // Desktop options
  width = 'md',  // 'sm' | 'md' | 'lg' | 'xl' | 'full' | custom string
  
  // Mobile options
  mobileFullScreen = true,
  
  // Styling
  className,
  contentClassName,
  
  // Behavior
  closeOnEscape = true,
  showCloseButton = true,
}) {
  const { isMobile } = useMobile()
  
  // Handle escape key
  useEffect(() => {
    if (!closeOnEscape || !open) return
    
    const handleEscape = (e) => {
      if (e.key === 'Escape') {
        onClose?.()
      }
    }
    
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [closeOnEscape, open, onClose])
  
  // Width classes for desktop
  const widthClasses = {
    sm: 'w-72 xl:w-80',
    md: 'w-80 xl:w-96 2xl:w-[420px]',
    lg: 'w-96 xl:w-[420px] 2xl:w-[480px]',
    xl: 'w-[420px] xl:w-[480px] 2xl:w-[560px]',
    full: 'w-full max-w-lg',
  }
  
  const desktopWidth = widthClasses[width] || width
  
  // ===================
  // MOBILE: Full-screen overlay
  // ===================
  if (isMobile && mobileFullScreen) {
    return (
      <div 
        className={cn(
          "fixed inset-0 z-50 bg-bg-primary flex flex-col",
          "transition-transform duration-300 ease-out",
          open ? "translate-x-0" : "translate-x-full",
          className
        )}
      >
        {/* Header */}
        <div className="px-4 py-3 border-b border-border bg-bg-secondary flex items-center gap-3 shrink-0">
          <button
            onClick={onClose}
            className="p-1.5 -ml-1.5 rounded-md hover:bg-bg-tertiary text-text-secondary hover:text-text-primary transition-colors"
            aria-label="Close"
          >
            <ArrowLeft size={20} />
          </button>
          <h2 className="text-base font-semibold text-text-primary flex-1 truncate">
            {title}
          </h2>
        </div>
        
        {/* Content */}
        <div className={cn("flex-1 overflow-auto", contentClassName)}>
          {open && children}
        </div>
      </div>
    )
  }
  
  // ===================
  // DESKTOP: Slide-over panel
  // ===================
  return (
    <div 
      className={cn(
        "border-l border-border bg-bg-secondary flex flex-col shrink-0",
        "transition-all duration-300 ease-out overflow-hidden",
        open ? desktopWidth : "w-0 border-l-0",
        className
      )}
    >
      {open && (
        <>
          {/* Header */}
          <div className="px-4 py-3 border-b border-border flex items-center justify-between shrink-0">
            <h2 className="text-sm font-semibold text-text-primary truncate">
              {title}
            </h2>
            {showCloseButton && (
              <button
                onClick={onClose}
                className="p-1 rounded hover:bg-bg-tertiary text-text-tertiary hover:text-text-primary transition-colors"
                aria-label="Close"
              >
                <X size={16} />
              </button>
            )}
          </div>
          
          {/* Content */}
          <div className={cn("flex-1 overflow-auto", contentClassName)}>
            {children}
          </div>
        </>
      )}
    </div>
  )
}

/**
 * Hook to manage slide-over panel state
 * 
 * Usage:
 * const { isOpen, selectedItem, open, close, toggle } = useSlideOver()
 */
export function useSlideOver(initialItem = null) {
  const [selectedItem, setSelectedItem] = useState(initialItem)
  
  const open = useCallback((item) => {
    setSelectedItem(item)
  }, [])
  
  const close = useCallback(() => {
    setSelectedItem(null)
  }, [])
  
  const toggle = useCallback((item) => {
    setSelectedItem(prev => prev === item ? null : item)
  }, [])
  
  return {
    isOpen: selectedItem !== null,
    selectedItem,
    open,
    close,
    toggle,
    setSelectedItem
  }
}
