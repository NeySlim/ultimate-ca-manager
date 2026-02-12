/**
 * ResponsiveLayout - SINGLE unified layout for all pages
 * 
 * ARCHITECTURE:
 * ┌──────────────────────────────────────────────────┐
 * │ HEADER (title, subtitle, tabs, actions)         │
 * ├──────────────────────────────────────────────────┤
 * │ STATS BAR (optional - quick stats)              │
 * ├──────────────────────────────────────────────────┤
 * │                                                  │
 * │ CONTENT                      │ SLIDE-OVER       │
 * │ (table/form/custom)          │ (details/edit)   │
 * │                              │                   │
 * │                              │ [Desktop: inline] │
 * │                              │ [Mobile: overlay] │
 * └──────────────────────────────────────────────────┘
 * 
 * DESKTOP: Dense, hover states, keyboard shortcuts, inline panels
 * MOBILE: Touch targets 44px+, swipe gestures, full-screen panels
 */
import { useState, useRef, useEffect, useCallback } from 'react'
import { X, ArrowLeft, Question } from '@phosphor-icons/react'
import { useMobile } from '../../../contexts'
import { cn } from '../../../lib/utils'
import { UnifiedPageHeader } from '../UnifiedPageHeader'
import { FilterSelect } from '../Select'
import { HelpModal } from '../HelpModal'

// =============================================================================
// PANEL WIDTH CONSTANTS
// =============================================================================
const PANEL_WIDTH_KEY = 'ucm-detail-panel-width'
const MIN_PANEL_WIDTH = 280
const MAX_PANEL_WIDTH = 600
const DEFAULT_PANEL_WIDTH = 380

// =============================================================================
// MAIN LAYOUT COMPONENT
// =============================================================================

export function ResponsiveLayout({
  // Header
  title,
  subtitle,
  icon: Icon,
  
  // Tabs (optional)
  tabs,
  activeTab,
  onTabChange,
  
  // Actions (top-right buttons)
  actions,
  
  // Stats bar (optional - array of { icon, label, value, variant, filterValue })
  stats,
  // Custom content rendered inline after stats (e.g., chain repair widget)
  afterStats,
  // Stats clicking - when stats are clickable for filtering
  activeStatFilter, // currently active stat filter value
  onStatClick, // (stat) => void - called when stat is clicked
  
  // Filters (optional - for filter drawer/panel)
  filters,
  activeFilters = 0, // count of active filters
  onClearFilters,
  
  // Help - pass pageKey to show contextual help modal
  helpPageKey, // e.g., 'cas', 'certificates', 'settings'
  // Legacy support - JSX content (deprecated)
  helpContent,
  helpTitle = 'Help',
  
  // Slide-over panel
  slideOverOpen = false,
  slideOverTitle,
  slideOverContent,
  slideOverWidth = 'default', // 'narrow' | 'default' | 'wide'
  slideOverActions, // ReactNode - actions to show in slide-over header (e.g., favorite button)
  onSlideOverClose,
  
  // Split view (xl+ screens) - panel always visible
  splitView = false, // Enable permanent split view on large screens
  splitEmptyContent, // Content to show when nothing selected in split view
  
  // Main content
  children,
  
  // Loading state
  loading = false,
  
  // Custom class
  className
}) {
  const { isMobile, isTablet, isDesktop, isTouch, isLargeScreen, screenWidth } = useMobile()
  
  // Show inline header when sidebar is visible (matches AppShell's breakpoint)
  const showInlineHeader = screenWidth >= 768
  
  // Local state for filter/help drawers (mobile only)
  const [filterDrawerOpen, setFilterDrawerOpen] = useState(false)
  const [helpDrawerOpen, setHelpDrawerOpen] = useState(false)
  
  // Resizable panel state
  const [panelWidth, setPanelWidth] = useState(() => {
    if (typeof window === 'undefined') return DEFAULT_PANEL_WIDTH
    try {
      const saved = localStorage.getItem(PANEL_WIDTH_KEY)
      if (saved) {
        const parsed = parseInt(saved, 10)
        if (parsed >= MIN_PANEL_WIDTH && parsed <= MAX_PANEL_WIDTH) {
          return parsed
        }
      }
    } catch {
      // localStorage unavailable (Safari private mode, etc.)
    }
    return DEFAULT_PANEL_WIDTH
  })
  const [isResizing, setIsResizing] = useState(false)
  const panelRef = useRef(null)
  const widthRef = useRef(panelWidth)
  
  // Keep ref in sync
  useEffect(() => {
    widthRef.current = panelWidth
  }, [panelWidth])
  
  // Handle resize
  const handleResizeStart = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsResizing(true)
  }, [])
  
  useEffect(() => {
    if (!isResizing) return
    
    const handleMouseMove = (e) => {
      if (!panelRef.current) return
      const containerRect = panelRef.current.parentElement.getBoundingClientRect()
      const newWidth = containerRect.right - e.clientX
      const clampedWidth = Math.max(MIN_PANEL_WIDTH, Math.min(MAX_PANEL_WIDTH, newWidth))
      setPanelWidth(clampedWidth)
      widthRef.current = clampedWidth
    }
    
    const handleMouseUp = () => {
      setIsResizing(false)
      try {
        localStorage.setItem(PANEL_WIDTH_KEY, widthRef.current.toString())
      } catch {
        // localStorage unavailable (Safari private mode, quota exceeded, etc.)
      }
    }
    
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    
    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [isResizing])
  
  // Close slide-over on Escape (desktop)
  useEffect(() => {
    if (!isDesktop) return
    
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && slideOverOpen) {
        onSlideOverClose?.()
      }
    }
    
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isDesktop, slideOverOpen, onSlideOverClose])
  
  return (
    <div className={cn(
      'flex flex-col h-full w-full overflow-hidden',
      className
    )}>
      {/* HEADER - Show when sidebar is visible (>= 768px) */}
      {showInlineHeader && (
        <UnifiedPageHeader
          title={title}
          subtitle={subtitle}
          icon={Icon}
          tabs={tabs}
          activeTab={activeTab}
          onTabChange={onTabChange}
          filters={filters}
          activeFilters={activeFilters}
          onClearFilters={onClearFilters}
          onOpenFilters={() => setFilterDrawerOpen(true)}
          actions={actions}
          showHelp={!!helpPageKey || !!helpContent}
          onHelpClick={() => setHelpDrawerOpen(true)}
          isMobile={false}
        />
      )}
      
      {/* MOBILE ONLY (< 768px): Tabs bar */}
      {!showInlineHeader && tabs && tabs.length > 0 && (
        <div className="shrink-0 border-b border-border/50 bg-bg-secondary/50 overflow-x-auto scrollbar-hide px-2">
          <div className="flex gap-0.5 min-w-max">
            {tabs.map((tab) => {
              const TabIcon = tab.icon
              const isActive = activeTab === tab.id
              return (
                <button
                  key={tab.id}
                  onClick={() => onTabChange?.(tab.id)}
                  className={cn(
                    "flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium transition-all",
                    "border-b-2 -mb-px",
                    isActive
                      ? "border-accent-primary text-accent-primary"
                      : "border-transparent text-text-secondary"
                  )}
                >
                  {TabIcon && <TabIcon size={14} weight={isActive ? "fill" : "regular"} />}
                  <span>{tab.label}</span>
                  {tab.count !== undefined && (
                    <span className={cn(
                      'px-1 py-0.5 rounded text-2xs',
                      isActive ? 'bg-accent-primary/15' : 'bg-bg-tertiary'
                    )}>
                      {tab.count}
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        </div>
      )}
      
      {/* STATS BAR (if provided) */}
      {stats && stats.length > 0 && (
        <StatsBar 
          stats={stats} 
          isMobile={isMobile} 
          onStatClick={onStatClick}
          activeStatFilter={activeStatFilter}
        />
      )}
      
      {/* AFTER STATS (custom content) */}
      {afterStats}
      
      {/* MAIN AREA - Content + SlideOver/SplitPanel */}
      <div className="flex-1 flex overflow-hidden">
        {/* CONTENT AREA - fills available space */}
        <main className={cn(
          'min-w-0 overflow-auto bg-bg-primary',
          // In split view mode on large screens, content takes remaining space
          splitView && isLargeScreen ? 'flex-1 border-r border-border' : 'flex-1'
        )}>
          {loading ? (
            <LoadingState />
          ) : (
            children
          )}
        </main>
        
        {/* SPLIT VIEW PANEL (xl+ screens) - Always visible with resize */}
        {splitView && isLargeScreen && (
          <aside 
            ref={panelRef}
            style={{ width: panelWidth }}
            className={cn(
              'shrink-0 overflow-hidden bg-bg-secondary/30 relative',
              isResizing && 'select-none'
            )}
          >
            {/* Resize Handle */}
            <div
              className={cn(
                "absolute left-0 top-0 bottom-0 w-2 cursor-col-resize z-10 resize-handle",
                isResizing && "resizing"
              )}
              onMouseDown={handleResizeStart}
              title="Drag to resize panel"
            >
              <div className="absolute left-0 top-0 bottom-0 w-0.5 resize-handle-line" />
            </div>
            
            {slideOverOpen && slideOverContent ? (
              <div className="h-full flex flex-col overflow-hidden">
                {/* Panel header */}
                <div className="shrink-0 px-4 py-3 border-b border-border flex items-center justify-between gap-2">
                  <h3 className="text-sm font-semibold text-text-primary truncate flex-1">{slideOverTitle}</h3>
                  {slideOverActions && (
                    <div className="flex items-center gap-1 shrink-0">
                      {slideOverActions}
                    </div>
                  )}
                  {onSlideOverClose && (
                    <button
                      onClick={onSlideOverClose}
                      className="p-1 rounded hover:bg-bg-tertiary text-text-secondary hover:text-text-primary shrink-0"
                    >
                      <X size={16} />
                    </button>
                  )}
                </div>
                {/* Panel content */}
                <div className="flex-1 overflow-auto">
                  {slideOverContent}
                </div>
              </div>
            ) : (
              // Empty state when nothing selected
              splitEmptyContent || (
                <div className="h-full flex flex-col items-center justify-center p-6 text-center">
                  <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
                    <Question size={24} className="text-text-tertiary" />
                  </div>
                  <p className="text-sm text-text-secondary">Select an item to view details</p>
                </div>
              )
            )}
          </aside>
        )}
        
        {/* SLIDE-OVER PANEL (non-split mode) - Desktop: inline, Mobile: overlay */}
        {!splitView && slideOverOpen && (
          isDesktop ? (
            <DesktopSlideOver
              title={slideOverTitle}
              width={slideOverWidth}
              onClose={onSlideOverClose}
            >
              {slideOverContent}
            </DesktopSlideOver>
          ) : (
            <MobileSlideOver
              title={slideOverTitle}
              onClose={onSlideOverClose}
            >
              {slideOverContent}
            </MobileSlideOver>
          )
        )}
        
        {/* Mobile slide-over (in split mode, mobile still uses overlay) */}
        {splitView && !isLargeScreen && slideOverOpen && (
          <MobileSlideOver
            title={slideOverTitle}
            onClose={onSlideOverClose}
          >
            {slideOverContent}
          </MobileSlideOver>
        )}
      </div>
      
      {/* MOBILE FILTER DRAWER */}
      {isMobile && filters && (
        <MobileDrawer
          open={filterDrawerOpen}
          onClose={() => setFilterDrawerOpen(false)}
          title="Filters"
        >
          <FilterContent 
            filters={filters} 
            onClearFilters={onClearFilters}
            onClose={() => setFilterDrawerOpen(false)}
          />
        </MobileDrawer>
      )}
      
      {/* HELP MODAL - New contextual help system */}
      {helpPageKey && (
        <HelpModal
          isOpen={helpDrawerOpen}
          onClose={() => setHelpDrawerOpen(false)}
          pageKey={helpPageKey}
        />
      )}
      
      {/* LEGACY HELP DRAWER - For backwards compatibility with JSX content */}
      {!helpPageKey && helpContent && (
        isMobile ? (
          <MobileDrawer
            open={helpDrawerOpen}
            onClose={() => setHelpDrawerOpen(false)}
            title={helpTitle}
          >
            {helpContent}
          </MobileDrawer>
        ) : helpDrawerOpen && (
          <DesktopHelpPanel
            title={helpTitle}
            onClose={() => setHelpDrawerOpen(false)}
          >
            {helpContent}
          </DesktopHelpPanel>
        )
      )}
    </div>
  )
}

// =============================================================================
// STATS BAR - Enhanced with rich visual styling like Dashboard
// =============================================================================

function StatsBar({ stats, isMobile, onStatClick, activeStatFilter }) {
  const iconVariants = {
    primary: 'rich-stat-icon-primary',
    success: 'rich-stat-icon-success',
    warning: 'rich-stat-icon-warning',
    danger: 'rich-stat-icon-danger',
    info: 'rich-stat-icon-primary',
    secondary: 'rich-stat-icon-neutral',
    default: 'rich-stat-icon-neutral'
  }
  
  if (isMobile) {
    // Mobile: Premium pill-style stats with colored backgrounds
    return (
      <div className="flex items-center gap-1.5 px-3 py-2 overflow-x-auto scrollbar-none border-b border-border/30 bg-bg-secondary/20">
        {stats.map((stat, i) => {
          const isActive = activeStatFilter && stat.filterValue === activeStatFilter
          const isClickable = onStatClick && stat.filterValue !== undefined
          const displayLabel = stat.shortLabel || stat.label
          
          // Premium colored pills
          const pillColors = {
            success: 'stats-inline-item stats-success',
            warning: 'stats-inline-item stats-warning', 
            danger: 'stats-inline-item stats-danger',
            primary: 'stats-inline-item stats-primary',
            info: 'stats-inline-item stats-primary',
            secondary: 'stats-inline-item',
            default: 'stats-inline-item'
          }
          const pillClass = pillColors[stat.variant] || pillColors.default
          
          return (
            <button
              key={i}
              onClick={() => isClickable && onStatClick(stat.filterValue)}
              disabled={!isClickable}
              className={cn(
                pillClass,
                isActive && "ring-2 ring-offset-1 ring-offset-bg-primary ring-current",
                !isClickable && "cursor-default opacity-80"
              )}
            >
              <span className="font-bold">{stat.value}</span>
              <span className="opacity-80">{displayLabel}</span>
            </button>
          )
        })}
      </div>
    )
  }
  
  // Desktop: Enhanced card-style stats with gradient icons
  return (
    <div className="rich-stats-bar py-2.5">
      {stats.map((stat, i) => {
        const Icon = stat.icon
        const iconClass = iconVariants[stat.variant] || iconVariants.primary
        const isActive = activeStatFilter && stat.filterValue === activeStatFilter
        const isClickable = onStatClick && stat.filterValue !== undefined
        
        return (
          <div 
            key={i} 
            className={cn(
              "rich-stat-item",
              isClickable && "cursor-pointer hover:bg-bg-tertiary/50 rounded-lg transition-colors",
              isActive && "ring-2 ring-accent-primary/50 bg-accent-primary/10"
            )}
            onClick={() => isClickable && onStatClick(stat.filterValue)}
            title={isClickable ? `Click to filter by ${stat.label}` : undefined}
          >
            {Icon && (
              <div className={cn('rich-stat-icon', iconClass)}>
                <Icon size={16} weight="duotone" />
              </div>
            )}
            <div className="rich-stat-content">
              <span className="rich-stat-value text-sm">{stat.value}</span>
              <span className="rich-stat-label">{stat.label}</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// =============================================================================
// DESKTOP SLIDE-OVER (inline panel from right)
// =============================================================================

function DesktopSlideOver({ title, width, onClose, children }) {
  // Width classes based on size
  const widthClasses = {
    narrow: 'w-80',
    default: 'w-96', 
    wide: 'w-[480px]'
  }
  const widthClass = widthClasses[width] || widthClasses.default
  
  return (
    <aside className={cn(
      'shrink-0 border-l border-border bg-bg-secondary/50',
      'flex flex-col overflow-hidden shadow-lg',
      'animate-slide-in-right',
      widthClass
    )}>
      {/* Header */}
      <div className="shrink-0 flex items-center justify-between px-4 py-3 border-b border-border bg-bg-primary">
        <h2 className="font-semibold text-sm text-text-primary truncate">
          {title}
        </h2>
        <button
          onClick={onClose}
          className={cn(
            'w-8 h-8 rounded-lg flex items-center justify-center',
            'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary',
            'transition-colors'
          )}
        >
          <X size={18} />
        </button>
      </div>
      
      {/* Content */}
      <div className="flex-1 overflow-auto bg-bg-primary">
        {children}
      </div>
    </aside>
  )
}

// =============================================================================
// MOBILE SLIDE-OVER (full-screen overlay with swipe-to-close)
// =============================================================================

function MobileSlideOver({ title, onClose, children }) {
  const panelRef = useRef(null)
  const [translateX, setTranslateX] = useState(0)
  const [isDragging, setIsDragging] = useState(false)
  const startXRef = useRef(0)
  
  // Swipe gesture handling
  const handleTouchStart = useCallback((e) => {
    startXRef.current = e.touches[0].clientX
    setIsDragging(true)
  }, [])
  
  const handleTouchMove = useCallback((e) => {
    if (!isDragging) return
    const currentX = e.touches[0].clientX
    const diff = currentX - startXRef.current
    // Only allow swiping right (to close)
    if (diff > 0) {
      setTranslateX(diff)
    }
  }, [isDragging])
  
  const handleTouchEnd = useCallback(() => {
    setIsDragging(false)
    // If swiped more than 100px, close
    if (translateX > 100) {
      onClose?.()
    }
    setTranslateX(0)
  }, [translateX, onClose])
  
  // Prevent body scroll when open
  useEffect(() => {
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = ''
    }
  }, [])
  
  return (
    <div className="fixed inset-0 z-50">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black/40 animate-fade-in"
        onClick={onClose}
      />
      
      {/* Panel */}
      <div
        ref={panelRef}
        className={cn(
          'absolute inset-y-0 right-0 w-full bg-bg-primary',
          'flex flex-col animate-slide-in-right',
          !isDragging && 'transition-transform'
        )}
        style={{
          transform: `translateX(${translateX}px)`
        }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {/* Header */}
        <div className="shrink-0 flex items-center gap-3 px-4 py-3 border-b border-border">
          <button
            onClick={onClose}
            className={cn(
              'w-11 h-11 rounded-lg flex items-center justify-center',
              'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary',
              'transition-colors'
            )}
          >
            <ArrowLeft size={22} />
          </button>
          <h2 className="font-semibold text-lg text-text-primary truncate flex-1">
            {title}
          </h2>
        </div>
        
        {/* Swipe indicator */}
        <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-16 bg-border rounded-r opacity-50" />
        
        {/* Content */}
        <div className="flex-1 overflow-auto">
          {children}
        </div>
      </div>
    </div>
  )
}

// =============================================================================
// MOBILE DRAWER (from bottom - for filters, help, etc.)
// =============================================================================

function MobileDrawer({ open, onClose, title, children }) {
  const drawerRef = useRef(null)
  const [translateY, setTranslateY] = useState(0)
  const [isDragging, setIsDragging] = useState(false)
  const startYRef = useRef(0)
  
  // Swipe down to close
  const handleTouchStart = useCallback((e) => {
    startYRef.current = e.touches[0].clientY
    setIsDragging(true)
  }, [])
  
  const handleTouchMove = useCallback((e) => {
    if (!isDragging) return
    const currentY = e.touches[0].clientY
    const diff = currentY - startYRef.current
    // Only allow swiping down
    if (diff > 0) {
      setTranslateY(diff)
    }
  }, [isDragging])
  
  const handleTouchEnd = useCallback(() => {
    setIsDragging(false)
    // If swiped more than 80px, close
    if (translateY > 80) {
      onClose?.()
    }
    setTranslateY(0)
  }, [translateY, onClose])
  
  // Prevent body scroll when open
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden'
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [open])
  
  if (!open) return null
  
  return (
    <div className="fixed inset-0 z-50">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black/40 animate-fade-in"
        onClick={onClose}
      />
      
      {/* Drawer */}
      <div
        ref={drawerRef}
        className={cn(
          'absolute inset-x-0 bottom-0 bg-bg-primary rounded-t-2xl',
          'max-h-[80vh] flex flex-col animate-slide-up',
          !isDragging && 'transition-transform'
        )}
        style={{
          transform: `translateY(${translateY}px)`
        }}
      >
        {/* Handle + Header */}
        <div
          className="shrink-0 pt-3 pb-2 px-4 cursor-grab"
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
        >
          {/* Drag handle */}
          <div className="w-10 h-1 rounded-full bg-border mx-auto mb-3" />
          
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-lg text-text-primary">
              {title}
            </h2>
            <button
              onClick={onClose}
              className="w-10 h-10 rounded-lg flex items-center justify-center text-text-secondary hover:bg-bg-tertiary"
            >
              <X size={20} />
            </button>
          </div>
        </div>
        
        {/* Content */}
        <div className="flex-1 overflow-auto px-4 pb-6">
          {children}
        </div>
      </div>
    </div>
  )
}

// =============================================================================
// DESKTOP HELP PANEL (slide-over from right)
// =============================================================================

function DesktopHelpPanel({ title, onClose, children }) {
  // Close on Escape
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose?.()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])
  
  return (
    <div className="fixed inset-0 z-50">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black/20 animate-fade-in"
        onClick={onClose}
      />
      
      {/* Panel */}
      <aside className={cn(
        'absolute top-4 right-4 bottom-4 w-80 bg-bg-primary rounded-xl',
        'flex flex-col overflow-hidden shadow-2xl border border-border',
        'animate-slide-in-right'
      )}>
        {/* Header */}
        <div className="shrink-0 flex items-center justify-between px-4 py-3 border-b border-border">
          <h2 className="font-semibold text-sm text-text-primary">
            {title}
          </h2>
          <button
            onClick={onClose}
            className={cn(
              'w-7 h-7 rounded-md flex items-center justify-center',
              'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary',
              'transition-colors'
            )}
          >
            <X size={16} />
          </button>
        </div>
        
        {/* Content */}
        <div className="flex-1 overflow-auto p-4">
          {children}
        </div>
      </aside>
    </div>
  )
}

// =============================================================================
// FILTER CONTENT
// =============================================================================

function FilterContent({ filters, onClearFilters, onClose }) {
  const hasActiveFilters = filters?.some(f => f.value)
  
  return (
    <div className="space-y-4">
      {/* Filter fields */}
      {filters?.map((filter) => (
        <div key={filter.key}>
          <label className="block text-sm font-medium text-text-primary mb-1.5">
            {filter.label}
          </label>
          {filter.type === 'select' ? (
            <FilterSelect
              value={filter.value || ''}
              onChange={filter.onChange}
              options={filter.options || []}
              placeholder={filter.placeholder || 'All'}
              size="lg"
              className="w-full"
            />
          ) : (
            <input
              type={filter.type || 'text'}
              value={filter.value || ''}
              onChange={(e) => filter.onChange?.(e.target.value)}
              placeholder={filter.placeholder}
              className={cn(
                'w-full h-11 px-3 rounded-lg border border-border bg-bg-primary',
                'text-text-primary text-sm',
                'focus:outline-none focus:ring-2 focus:ring-accent-primary/50'
              )}
            />
          )}
        </div>
      ))}
      
      {/* Actions */}
      <div className="flex gap-2 pt-2">
        {hasActiveFilters && onClearFilters && (
          <button
            onClick={() => {
              onClearFilters()
              onClose?.()
            }}
            className={cn(
              'flex-1 h-11 rounded-lg border border-border',
              'text-text-secondary font-medium text-sm',
              'hover:bg-bg-tertiary transition-colors'
            )}
          >
            Clear Filters
          </button>
        )}
        <button
          onClick={onClose}
          className={cn(
            'flex-1 h-11 rounded-lg bg-accent-primary text-white',
            'font-medium text-sm hover:bg-accent-primary/90 transition-colors'
          )}
        >
          Apply
        </button>
      </div>
    </div>
  )
}

// =============================================================================
// LOADING STATE
// =============================================================================

function LoadingState() {
  return (
    <div className="flex items-center justify-center h-full min-h-[200px]">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-accent-primary/30 border-t-accent-primary rounded-full animate-spin" />
        <p className="text-sm text-text-secondary">Loading...</p>
      </div>
    </div>
  )
}

export default ResponsiveLayout
