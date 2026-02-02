/**
 * FilterPanel Component - Responsive filter interface
 * 
 * DESKTOP:
 * - Inline panel in sidebar/focus area
 * - Compact inputs (h-8)
 * - Visible by default
 * - Live filtering (no apply button needed)
 * 
 * MOBILE:
 * - Bottom drawer (slides up from bottom)
 * - Touch-friendly inputs (h-11)
 * - Opens via button click
 * - Apply/Clear buttons
 * - Swipe down to close
 * 
 * Features:
 * - Filter chip display for active filters
 * - Stats display (optional)
 * - Quick filter presets (optional)
 * - Clear all functionality
 * 
 * Usage:
 * <FilterPanel
 *   open={showFilters}
 *   onOpenChange={setShowFilters}
 *   filters={[
 *     { key: 'status', label: 'Status', type: 'select', value: status, onChange: setStatus, options: [...] },
 *     { key: 'from', label: 'From Date', type: 'date', value: fromDate, onChange: setFromDate }
 *   ]}
 *   stats={[
 *     { label: 'Total', value: 54 },
 *     { label: 'Expiring', value: 5, color: 'text-status-warning' }
 *   ]}
 *   onClearAll={() => { setStatus(''); setFromDate(''); }}
 * />
 */
import { useState, useRef, useCallback, useEffect } from 'react'
import { X, Funnel, Eraser, CaretDown, Check } from '@phosphor-icons/react'
import { cn } from '../lib/utils'
import { useMobile } from '../contexts'
import { Button } from './Button'
import { Badge } from './Badge'

// ============================================
// FILTER INPUT COMPONENTS
// ============================================

/**
 * Select input for filters
 */
function FilterSelect({ 
  value, 
  onChange, 
  options = [], 
  placeholder = 'All', 
  isMobile 
}) {
  return (
    <select
      value={value || ''}
      onChange={(e) => onChange(e.target.value)}
      className={cn(
        'select-native w-full',
        isMobile ? 'select-native-lg h-11' : 'h-8',
        value && 'active'
      )}
    >
      <option value="">{placeholder}</option>
      {options.map(opt => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  )
}

/**
 * Date input for filters
 */
function FilterDate({ value, onChange, placeholder, isMobile }) {
  return (
    <input
      type="date"
      value={value || ''}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className={cn(
        "w-full bg-bg-tertiary border border-border rounded text-text-primary",
        "focus:outline-none focus:ring-2 focus:ring-accent-primary/50 focus:border-accent-primary",
        "transition-colors",
        isMobile ? "h-11 px-3 text-base" : "h-8 px-2.5 text-sm"
      )}
    />
  )
}

/**
 * Text input for filters
 */
function FilterText({ value, onChange, placeholder, isMobile }) {
  return (
    <input
      type="text"
      value={value || ''}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className={cn(
        "w-full bg-bg-tertiary border border-border rounded text-text-primary",
        "placeholder:text-text-tertiary",
        "focus:outline-none focus:ring-2 focus:ring-accent-primary/50 focus:border-accent-primary",
        "transition-colors",
        isMobile ? "h-11 px-3 text-base" : "h-8 px-2.5 text-sm"
      )}
    />
  )
}

// ============================================
// MAIN FILTER PANEL COMPONENT
// ============================================

export function FilterPanel({
  open,
  onOpenChange,
  // Filter definitions
  filters = [],  // [{ key, label, type: 'select'|'date'|'text', value, onChange, options?, placeholder? }]
  // Optional stats to display
  stats,         // [{ label, value, color?, icon? }]
  // Quick filter presets
  quickFilters,  // [{ label, icon?, onClick, active }]
  // Clear all callback
  onClearAll,
  // Custom content
  children,
  // Title (mobile drawer)
  title = 'Filters',
  // Class name
  className
}) {
  const { isMobile } = useMobile()
  const drawerRef = useRef(null)
  
  // Touch tracking for mobile drawer
  const touchStartY = useRef(0)
  const touchDeltaY = useRef(0)
  const isDragging = useRef(false)

  // Count active filters
  const activeCount = filters.filter(f => f.value && f.value !== '').length

  // ============================================
  // MOBILE: Touch handlers for swipe-to-close
  // ============================================
  const handleTouchStart = useCallback((e) => {
    touchStartY.current = e.touches[0].clientY
    touchDeltaY.current = 0
    isDragging.current = true
  }, [])

  const handleTouchMove = useCallback((e) => {
    if (!isDragging.current) return
    
    const currentY = e.touches[0].clientY
    const delta = currentY - touchStartY.current
    
    // Only allow dragging down (positive delta)
    if (delta > 0) {
      touchDeltaY.current = delta
      if (drawerRef.current) {
        drawerRef.current.style.transform = `translateY(${delta}px)`
        drawerRef.current.style.transition = 'none'
      }
    }
  }, [])

  const handleTouchEnd = useCallback(() => {
    if (!isDragging.current) return
    isDragging.current = false
    
    if (drawerRef.current) {
      drawerRef.current.style.transition = ''
      drawerRef.current.style.transform = ''
    }
    
    // Close if swiped more than 80px down
    if (touchDeltaY.current > 80) {
      onOpenChange(false)
    }
  }, [onOpenChange])

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
  // FILTER INPUT RENDERER
  // ============================================
  const renderFilter = (filter) => {
    const { key, label, type, value, onChange, options, placeholder } = filter
    
    return (
      <div key={key} className={cn(isMobile ? "space-y-2" : "space-y-1.5")}>
        <label className={cn(
          "font-medium text-text-secondary uppercase tracking-wider",
          isMobile ? "text-xs" : "text-[11px]"
        )}>
          {label}
        </label>
        
        {type === 'select' && (
          <FilterSelect
            value={value}
            onChange={onChange}
            options={options}
            placeholder={placeholder || `All ${label}`}
            isMobile={isMobile}
          />
        )}
        
        {type === 'date' && (
          <FilterDate
            value={value}
            onChange={onChange}
            placeholder={placeholder}
            isMobile={isMobile}
          />
        )}
        
        {type === 'text' && (
          <FilterText
            value={value}
            onChange={onChange}
            placeholder={placeholder || `Filter by ${label.toLowerCase()}...`}
            isMobile={isMobile}
          />
        )}
      </div>
    )
  }

  // ============================================
  // STATS RENDERER
  // ============================================
  const renderStats = () => {
    if (!stats || stats.length === 0) return null
    
    return (
      <div className={cn(
        "grid gap-2",
        stats.length === 2 ? "grid-cols-2" : 
        stats.length === 3 ? "grid-cols-3" :
        stats.length >= 4 ? "grid-cols-2" : "grid-cols-1"
      )}>
        {stats.map((stat, i) => {
          const Icon = stat.icon
          return (
            <div 
              key={i} 
              className={cn(
                "text-center rounded-lg",
                isMobile ? "bg-bg-tertiary p-3" : "bg-bg-tertiary/50 p-2"
              )}
            >
              {Icon && (
                <Icon 
                  size={isMobile ? 18 : 14} 
                  className={cn("mx-auto mb-1", stat.color || "text-accent-primary")} 
                />
              )}
              <p className={cn(
                "font-bold",
                stat.color || "text-text-primary",
                isMobile ? "text-xl" : "text-base"
              )}>
                {stat.value}
              </p>
              <p className={cn(
                "text-text-tertiary",
                isMobile ? "text-xs" : "text-[10px]"
              )}>
                {stat.label}
              </p>
            </div>
          )
        })}
      </div>
    )
  }

  // ============================================
  // QUICK FILTERS RENDERER
  // ============================================
  const renderQuickFilters = () => {
    if (!quickFilters || quickFilters.length === 0) return null
    
    return (
      <div className="space-y-1.5">
        <label className={cn(
          "font-medium text-text-secondary uppercase tracking-wider",
          isMobile ? "text-xs" : "text-[11px]"
        )}>
          Quick Filters
        </label>
        <div className="flex flex-wrap gap-1.5">
          {quickFilters.map((qf, i) => {
            const Icon = qf.icon
            return (
              <button
                key={i}
                type="button"
                onClick={qf.onClick}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full transition-colors",
                  isMobile ? "px-3 py-2 text-sm" : "px-2.5 py-1 text-xs",
                  qf.active
                    ? "bg-accent-primary/15 text-accent-primary border border-accent-primary/30"
                    : "bg-bg-tertiary text-text-secondary hover:text-text-primary hover:bg-bg-tertiary/80 border border-transparent"
                )}
              >
                {Icon && <Icon size={isMobile ? 16 : 12} />}
                {qf.label}
                {qf.active && <Check size={12} weight="bold" />}
              </button>
            )
          })}
        </div>
      </div>
    )
  }

  // ============================================
  // MOBILE: Bottom Drawer
  // ============================================
  if (isMobile) {
    return (
      <>
        {/* Backdrop */}
        <div 
          className={cn(
            "fixed inset-0 z-40 bg-black/40 transition-opacity duration-200",
            open ? "opacity-100" : "opacity-0 pointer-events-none"
          )}
          onClick={() => onOpenChange(false)}
          aria-hidden="true"
        />
        
        {/* Drawer */}
        <div
          ref={drawerRef}
          role="dialog"
          aria-modal="true"
          aria-label={title}
          className={cn(
            "fixed left-0 right-0 bottom-0 z-50 bg-bg-secondary rounded-t-2xl",
            "transition-transform duration-200 ease-out",
            "max-h-[85vh] flex flex-col shadow-2xl",
            open ? "translate-y-0" : "translate-y-full",
            className
          )}
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
        >
          {/* Drag handle */}
          <div className="flex justify-center py-3">
            <div className="w-10 h-1 bg-border rounded-full" />
          </div>
          
          {/* Header */}
          <div className="px-4 pb-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Funnel size={20} className="text-accent-primary" weight="bold" />
              <span className="text-base font-semibold text-text-primary">{title}</span>
              {activeCount > 0 && (
                <Badge variant="primary" size="sm">{activeCount}</Badge>
              )}
            </div>
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              className="w-11 h-11 flex items-center justify-center rounded-lg text-text-secondary hover:bg-bg-tertiary"
              aria-label="Close filters"
            >
              <X size={22} />
            </button>
          </div>
          
          {/* Content - Scrollable */}
          <div className="flex-1 overflow-auto px-4 pb-4 space-y-5">
            {/* Stats */}
            {renderStats()}
            
            {/* Filters */}
            {filters.length > 0 && (
              <div className="space-y-4">
                {filters.map(renderFilter)}
              </div>
            )}
            
            {/* Quick filters */}
            {renderQuickFilters()}
            
            {/* Custom content */}
            {children}
          </div>
          
          {/* Footer actions */}
          <div className="shrink-0 border-t border-border p-4 flex gap-3 bg-bg-secondary">
            {activeCount > 0 && onClearAll && (
              <Button 
                variant="ghost" 
                size="md" 
                onClick={() => { onClearAll(); onOpenChange(false); }} 
                className="flex-1"
              >
                <Eraser size={18} />
                Clear All
              </Button>
            )}
            <Button 
              variant="primary" 
              size="md" 
              onClick={() => onOpenChange(false)} 
              className="flex-1"
            >
              Apply Filters
            </Button>
          </div>
        </div>
      </>
    )
  }

  // ============================================
  // DESKTOP: Inline Panel
  // ============================================
  return (
    <div className={cn("space-y-4", className)}>
      {/* Stats */}
      {renderStats()}
      
      {/* Filters */}
      {filters.length > 0 && (
        <div className="space-y-3">
          {filters.map(renderFilter)}
        </div>
      )}
      
      {/* Quick filters */}
      {renderQuickFilters()}
      
      {/* Custom content */}
      {children}
      
      {/* Clear button */}
      {activeCount > 0 && onClearAll && (
        <Button 
          variant="ghost" 
          size="sm" 
          onClick={onClearAll} 
          className="w-full"
        >
          <Eraser size={14} />
          Clear All Filters
        </Button>
      )}
    </div>
  )
}

// ============================================
// FILTER CHIPS: Display active filters inline
// ============================================

export function FilterChips({ 
  filters = [], 
  onRemove,
  className 
}) {
  const activeFilters = filters.filter(f => f.value && f.value !== '')
  
  if (activeFilters.length === 0) return null
  
  return (
    <div className={cn("flex flex-wrap gap-1.5", className)}>
      {activeFilters.map(f => {
        // Get display value (for select, find the label)
        let displayValue = f.value
        if (f.options) {
          const option = f.options.find(o => o.value === f.value)
          if (option) displayValue = option.label
        }
        
        return (
          <span
            key={f.key}
            className="inline-flex items-center gap-1 px-2 py-0.5 bg-accent-primary/10 text-accent-primary rounded text-xs"
          >
            <span className="text-text-tertiary">{f.label}:</span>
            <span className="font-medium">{displayValue}</span>
            {onRemove && (
              <button
                type="button"
                onClick={() => onRemove(f.key)}
                className="ml-0.5 hover:text-accent-primary/70 focus:outline-none"
                aria-label={`Remove ${f.label} filter`}
              >
                <X size={12} />
              </button>
            )}
          </span>
        )
      })}
    </div>
  )
}

// ============================================
// FILTER BUTTON: Trigger for mobile drawer
// ============================================

export function FilterButton({ 
  onClick, 
  activeCount = 0,
  className 
}) {
  const { isMobile } = useMobile()
  
  return (
    <Button
      variant="secondary"
      size={isMobile ? "md" : "sm"}
      onClick={onClick}
      className={cn("shrink-0", className)}
    >
      <Funnel size={isMobile ? 18 : 14} weight={activeCount > 0 ? "fill" : "regular"} />
      <span className={isMobile ? "" : "hidden sm:inline"}>Filters</span>
      {activeCount > 0 && (
        <Badge variant="primary" size="sm" className="ml-1">
          {activeCount}
        </Badge>
      )}
    </Button>
  )
}

export default FilterPanel
