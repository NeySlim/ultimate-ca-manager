/**
 * Bottom Sheet Component - Mobile explorer panel
 * Always visible peek bar, slides up on drag or tap
 */
import { useState, useRef, useEffect } from 'react'
import { X, CaretUp, CaretDown, List } from '@phosphor-icons/react'
import { cn } from '../lib/utils'

const PEEK_HEIGHT = 56 // Height of the always-visible bar

export function BottomSheet({ 
  open, 
  onOpenChange, 
  title,
  children,
  snapPoints = ['25%', '50%', '90%'],
  defaultSnap = 1
}) {
  const [currentSnap, setCurrentSnap] = useState(open ? defaultSnap : -1) // -1 = peek only
  const [isDragging, setIsDragging] = useState(false)
  const [dragOffset, setDragOffset] = useState(0)
  const sheetRef = useRef(null)
  const startY = useRef(0)
  const startHeight = useRef(0)
  const hasMoved = useRef(false)

  // Sync with open prop
  useEffect(() => {
    if (open && currentSnap === -1) {
      setCurrentSnap(defaultSnap)
    } else if (!open && currentSnap !== -1) {
      setCurrentSnap(-1)
    }
  }, [open, defaultSnap])

  // Get height from snap point
  const getSnapHeight = (snapIndex) => {
    if (snapIndex === -1) return PEEK_HEIGHT
    const snap = snapPoints[snapIndex]
    if (typeof snap === 'string' && snap.endsWith('%')) {
      return (parseInt(snap) / 100) * window.innerHeight
    }
    return parseInt(snap)
  }

  const currentHeight = getSnapHeight(currentSnap) - dragOffset
  const isExpanded = currentSnap !== -1

  // Handle drag start
  const handleDragStart = (e) => {
    setIsDragging(true)
    hasMoved.current = false
    startY.current = e.touches ? e.touches[0].clientY : e.clientY
    startHeight.current = currentHeight
  }

  // Handle drag move
  const handleDragMove = (e) => {
    if (!isDragging) return
    
    const clientY = e.touches ? e.touches[0].clientY : e.clientY
    const delta = clientY - startY.current
    
    // Mark as moved if delta is significant
    if (Math.abs(delta) > 5) {
      hasMoved.current = true
    }
    
    const maxOffset = startHeight.current - PEEK_HEIGHT
    const minOffset = -(window.innerHeight * 0.9 - startHeight.current)
    
    setDragOffset(Math.max(minOffset, Math.min(maxOffset, delta)))
  }

  // Handle drag end - snap to nearest point
  const handleDragEnd = () => {
    const wasDragging = isDragging && hasMoved.current
    setIsDragging(false)
    
    if (!wasDragging) {
      // It was a tap, not a drag
      setDragOffset(0)
      return
    }
    
    const finalHeight = currentHeight
    
    // Find nearest snap point (including peek at -1)
    let nearestSnap = -1
    let nearestDistance = Math.abs(PEEK_HEIGHT - finalHeight)
    
    snapPoints.forEach((_, index) => {
      const snapHeight = getSnapHeight(index)
      const distance = Math.abs(snapHeight - finalHeight)
      if (distance < nearestDistance) {
        nearestDistance = distance
        nearestSnap = index
      }
    })
    
    setCurrentSnap(nearestSnap)
    onOpenChange(nearestSnap !== -1)
    setDragOffset(0)
  }

  // Handle tap on peek bar (separate from drag)
  const handleTap = () => {
    if (!isExpanded) {
      setCurrentSnap(defaultSnap)
      onOpenChange(true)
    }
  }

  // Close sheet
  const handleClose = () => {
    setCurrentSnap(-1)
    onOpenChange(false)
  }

  // Cycle through snap points
  const cycleSnap = (direction) => {
    if (direction === 'up') {
      if (currentSnap === -1) {
        setCurrentSnap(0)
        onOpenChange(true)
      } else {
        setCurrentSnap(Math.min(currentSnap + 1, snapPoints.length - 1))
      }
    } else {
      if (currentSnap === 0) {
        handleClose()
      } else if (currentSnap > 0) {
        setCurrentSnap(currentSnap - 1)
      }
    }
  }

  return (
    <>
      {/* Backdrop - only when expanded */}
      {isExpanded && (
        <div 
          className="fixed inset-0 bg-black/50 z-40 transition-opacity"
          onClick={handleClose}
        />
      )}

      {/* Sheet */}
      <div
        ref={sheetRef}
        className={cn(
          "fixed left-0 right-0 bottom-0 z-50 bg-bg-secondary rounded-t-xl shadow-2xl flex flex-col",
          !isDragging && "transition-all duration-200"
        )}
        style={{ height: Math.max(PEEK_HEIGHT, currentHeight) }}
      >
        {/* Peek Bar Header - always tappable */}
        <div
          className={cn(
            "flex-shrink-0",
            !isExpanded && "bg-bg-tertiary cursor-pointer active:bg-bg-secondary"
          )}
          onClick={!isExpanded ? handleTap : undefined}
        >
          {/* Drag handle area */}
          <div
            className="cursor-grab active:cursor-grabbing touch-none"
            onMouseDown={handleDragStart}
            onMouseMove={handleDragMove}
            onMouseUp={handleDragEnd}
            onMouseLeave={() => isDragging && handleDragEnd()}
            onTouchStart={handleDragStart}
            onTouchMove={handleDragMove}
            onTouchEnd={handleDragEnd}
          >
            {/* Drag indicator line */}
            <div className="pt-2 pb-1">
              <div className="w-10 h-1 bg-border rounded-full mx-auto" />
            </div>
          </div>

          {/* Title bar */}
          <div className="flex items-center justify-between px-4 h-10">
            <div className="flex items-center gap-3">
              <List size={18} className="text-text-secondary" />
              <span className="text-sm font-semibold text-text-primary uppercase tracking-wide">
                {title}
              </span>
            </div>
            <div className="flex items-center gap-1">
              {isExpanded ? (
                <>
                  <button
                    onClick={(e) => { e.stopPropagation(); cycleSnap('up') }}
                    className="w-7 h-7 flex items-center justify-center rounded text-text-secondary hover:bg-bg-primary/50"
                    disabled={currentSnap === snapPoints.length - 1}
                  >
                    <CaretUp size={16} />
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); cycleSnap('down') }}
                    className="w-7 h-7 flex items-center justify-center rounded text-text-secondary hover:bg-bg-primary/50"
                  >
                    <CaretDown size={16} />
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleClose() }}
                    className="w-7 h-7 flex items-center justify-center rounded text-text-secondary hover:bg-bg-primary/50 ml-1"
                  >
                    <X size={16} />
                  </button>
                </>
              ) : (
                <CaretUp size={18} className="text-text-tertiary" />
              )}
            </div>
          </div>
        </div>

        {/* Content - only visible when expanded */}
        {isExpanded && (
          <div className="flex-1 overflow-auto min-h-0 border-t border-border">
            {children}
          </div>
        )}
      </div>
    </>
  )
}
