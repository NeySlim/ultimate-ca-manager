/**
 * ResponsivePageLayout - Unified layout for all UCM pages
 * 
 * SINGLE LAYOUT to replace: PageLayout, TablePageLayout, ListPageLayout,
 * UnifiedManagementLayout, ManagementLayout
 * 
 * DESKTOP (mouse + keyboard):
 * - Dense, fine interface
 * - Hover states on rows
 * - Inline slide-over panel (w-80 to w-96)
 * - Compact inputs (h-8)
 * - Keyboard shortcuts (Escape to close)
 * 
 * MOBILE (touch/fingers):
 * - 44px+ touch targets
 * - Full-screen slide-over with swipe-to-close
 * - Bottom drawer for filters
 * - Large inputs (h-11)
 * - No hover states (tap/press instead)
 * 
 * Usage:
 * <ResponsivePageLayout
 *   title="Certificates"
 *   tabs={[{ id: 'all', label: 'All' }, { id: 'expiring', label: 'Expiring' }]}
 *   activeTab={activeTab}
 *   onTabChange={setActiveTab}
 *   actions={<Button>Issue Certificate</Button>}
 *   stats={[{ label: 'Total', value: 54 }]}
 *   filters={[{ key: 'status', label: 'Status', type: 'select', options: [...] }]}
 *   helpContent={<HelpCard>...</HelpCard>}
 *   slideOverOpen={!!selectedItem}
 *   slideOverContent={<CertificateDetails cert={selectedItem} />}
 *   onSlideOverClose={() => setSelectedItem(null)}
 * >
 *   <DataTable ... />
 * </ResponsivePageLayout>
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { cn } from '../lib/utils'
import { useMobile } from '../contexts'
import { Button } from './Button'
import { Badge } from './Badge'
import { HelpModal } from './HelpModal'
import { 
  X, CaretLeft, Question, Funnel, Eraser
} from '@phosphor-icons/react'

// =============================================================================
// MAIN LAYOUT COMPONENT
// =============================================================================

export function ResponsivePageLayout({
  // Page metadata
  title,
  subtitle,
  
  // Tabs (optional)
  tabs,                // [{ id, label, icon?, badge?, pro? }]
  activeTab,
  onTabChange,
  
  // Header actions (buttons)
  actions,
  
  // Stats bar (optional)
  stats,               // [{ label, value, icon?, variant? }]
  
  // Filters (optional) - rendered in slide-over on desktop, drawer on mobile
  filters,             // [{ key, label, type, value, onChange, options? }]
  onClearFilters,
  
  // Help content (optional)
  helpContent,
  helpTitle,
  
  // Slide-over panel (details panel)
  slideOverOpen,
  slideOverTitle,
  slideOverContent,
  onSlideOverClose,
  slideOverWidth = 'default', // 'narrow' | 'default' | 'wide'
  
  // Main content
  children,
  
  // Styling
  className,
}) {
  const { isMobile, isTouch } = useMobile()
  const [helpOpen, setHelpOpen] = useState(false)
  const [filterDrawerOpen, setFilterDrawerOpen] = useState(false)
  
  // Count active filters
  const activeFilterCount = filters?.filter(f => f.value && f.value !== '').length || 0
  
  // Keyboard handler for Escape
  useEffect(() => {
    if (!slideOverOpen) return
    
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onSlideOverClose?.()
      }
    }
    
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [slideOverOpen, onSlideOverClose])
  
  // Prevent body scroll when mobile slide-over is open
  useEffect(() => {
    if (isMobile && slideOverOpen) {
      document.body.style.overflow = 'hidden'
      return () => { document.body.style.overflow = '' }
    }
  }, [isMobile, slideOverOpen])

  // =============================================================================
  // MOBILE LAYOUT
  // =============================================================================
  if (isMobile) {
    return (
      <div className={cn("flex flex-col h-full w-full bg-bg-primary", className)}>
        {/* Mobile Slide-Over (full-screen) */}
        <MobileSlideOver
          open={slideOverOpen}
          title={slideOverTitle}
          onClose={onSlideOverClose}
        >
          {slideOverContent}
        </MobileSlideOver>
        
        {/* Mobile Filter Drawer */}
        <MobileFilterDrawer
          open={filterDrawerOpen}
          onClose={() => setFilterDrawerOpen(false)}
          filters={filters}
          onClearFilters={onClearFilters}
        />
        
        {/* Header */}
        <header className="shrink-0 px-4 py-3 border-b border-border bg-bg-secondary">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 min-w-0">
              <h1 className="text-base font-semibold text-text-primary truncate">{title}</h1>
              {subtitle && <span className="text-xs text-text-tertiary hidden sm:inline">• {subtitle}</span>}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {actions}
              {helpContent && (
                <button
                  type="button"
                  onClick={() => setHelpOpen(true)}
                  className="w-10 h-10 flex items-center justify-center rounded-lg text-text-secondary active:bg-bg-tertiary"
                  aria-label="Help"
                >
                  <Question size={20} />
                </button>
              )}
            </div>
          </div>
          
          {/* Tabs (mobile) */}
          {tabs && tabs.length > 0 && (
            <div className="flex gap-1 mt-3 -mx-1 overflow-x-auto pb-1">
              {tabs.map(tab => (
                <MobileTab
                  key={tab.id}
                  tab={tab}
                  active={activeTab === tab.id}
                  onClick={() => onTabChange?.(tab.id)}
                />
              ))}
            </div>
          )}
        </header>
        
        {/* Stats bar (mobile) */}
        {stats && stats.length > 0 && (
          <div className="shrink-0 px-4 py-2 border-b border-border bg-bg-tertiary/50 flex items-center gap-4 overflow-x-auto">
            {stats.map((stat, i) => (
              <StatItem key={i} stat={stat} mobile />
            ))}
          </div>
        )}
        
        {/* Filter button bar (mobile) */}
        {filters && filters.length > 0 && (
          <div className="shrink-0 px-4 py-2 border-b border-border flex items-center justify-between">
            <button
              type="button"
              onClick={() => setFilterDrawerOpen(true)}
              className={cn(
                "flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                activeFilterCount > 0
                  ? "bg-accent-primary/15 text-accent-primary"
                  : "bg-bg-tertiary text-text-secondary"
              )}
            >
              <Funnel size={16} weight={activeFilterCount > 0 ? "fill" : "regular"} />
              Filters
              {activeFilterCount > 0 && (
                <Badge variant="primary" size="sm">{activeFilterCount}</Badge>
              )}
            </button>
            {activeFilterCount > 0 && onClearFilters && (
              <button
                type="button"
                onClick={onClearFilters}
                className="text-xs text-accent-primary font-medium"
              >
                Clear all
              </button>
            )}
          </div>
        )}
        
        {/* Main content */}
        <main className="flex-1 overflow-auto">
          {children}
        </main>
        
        {/* Help Modal */}
        <HelpModal
          open={helpOpen}
          onClose={() => setHelpOpen(false)}
          title={helpTitle || `${title} Help`}
        >
          {helpContent}
        </HelpModal>
      </div>
    )
  }

  // =============================================================================
  // DESKTOP LAYOUT
  // =============================================================================
  return (
    <div className={cn("flex h-full w-full", className)}>
      {/* Main content area */}
      <div className="flex-1 flex flex-col min-w-0 min-h-0">
        {/* Header */}
        <header className="shrink-0 px-6 py-3 border-b border-border bg-bg-secondary">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-4 min-w-0">
              <div>
                <h1 className="text-lg font-semibold text-text-primary">{title}</h1>
                {subtitle && <p className="text-xs text-text-tertiary mt-0.5">{subtitle}</p>}
              </div>
              
              {/* Tabs (desktop) */}
              {tabs && tabs.length > 0 && (
                <div className="flex gap-1 ml-2">
                  {tabs.map(tab => (
                    <DesktopTab
                      key={tab.id}
                      tab={tab}
                      active={activeTab === tab.id}
                      onClick={() => onTabChange?.(tab.id)}
                    />
                  ))}
                </div>
              )}
            </div>
            
            <div className="flex items-center gap-2 shrink-0">
              {actions}
              {helpContent && (
                <button
                  type="button"
                  onClick={() => setHelpOpen(true)}
                  className={cn(
                    "flex items-center gap-1.5 px-2.5 py-1.5 rounded-md transition-colors",
                    "bg-accent-primary/10 border border-accent-primary/30",
                    "text-accent-primary hover:bg-accent-primary/20 text-xs font-medium"
                  )}
                >
                  <Question size={14} weight="bold" />
                  Help
                </button>
              )}
            </div>
          </div>
          
          {/* Stats bar (desktop) */}
          {stats && stats.length > 0 && (
            <div className="flex items-center gap-4 mt-2">
              {stats.map((stat, i) => (
                <StatItem key={i} stat={stat} />
              ))}
            </div>
          )}
        </header>
        
        {/* Main content */}
        <main className="flex-1 overflow-auto">
          {children}
        </main>
      </div>
      
      {/* Desktop Slide-Over Panel */}
      <DesktopSlideOver
        open={slideOverOpen}
        title={slideOverTitle}
        width={slideOverWidth}
        onClose={onSlideOverClose}
        filters={filters}
        onClearFilters={onClearFilters}
      >
        {slideOverContent}
      </DesktopSlideOver>
      
      {/* Help Modal */}
      <HelpModal
        open={helpOpen}
        onClose={() => setHelpOpen(false)}
        title={helpTitle || `${title} Help`}
      >
        {helpContent}
      </HelpModal>
    </div>
  )
}

// =============================================================================
// DESKTOP SLIDE-OVER (inline panel)
// =============================================================================

function DesktopSlideOver({ 
  open, 
  title, 
  width = 'default',
  onClose, 
  filters,
  onClearFilters,
  children 
}) {
  const widthClasses = {
    narrow: 'w-72 xl:w-80',
    default: 'w-80 xl:w-96',
    wide: 'w-96 xl:w-[420px] 2xl:w-[480px]'
  }
  
  const activeFilterCount = filters?.filter(f => f.value && f.value !== '').length || 0
  
  return (
    <aside
      className={cn(
        "border-l border-border bg-bg-secondary flex flex-col shrink-0 transition-all duration-200 ease-out overflow-hidden",
        open ? widthClasses[width] : "w-0 border-l-0"
      )}
    >
      {open && (
        <>
          {/* Panel Header */}
          <div className="px-4 py-2.5 border-b border-border flex items-center justify-between shrink-0 bg-bg-tertiary/30">
            <h2 className="text-sm font-semibold text-text-primary">{title || 'Details'}</h2>
            <button
              type="button"
              onClick={onClose}
              className="p-1 rounded hover:bg-bg-tertiary text-text-tertiary hover:text-text-primary transition-colors"
              aria-label="Close panel"
            >
              <X size={16} />
            </button>
          </div>
          
          {/* Panel Content */}
          <div className="flex-1 overflow-auto">
            {children}
          </div>
          
          {/* Filters Section (if provided) */}
          {filters && filters.length > 0 && (
            <div className="border-t border-border p-3 space-y-3 bg-bg-tertiary/20">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-text-secondary uppercase tracking-wide">
                  Filters
                </span>
                {activeFilterCount > 0 && onClearFilters && (
                  <button
                    type="button"
                    onClick={onClearFilters}
                    className="text-xs text-accent-primary hover:text-accent-primary/80 font-medium flex items-center gap-1"
                  >
                    <Eraser size={12} />
                    Clear
                  </button>
                )}
              </div>
              {filters.map(filter => (
                <FilterInput key={filter.key} filter={filter} />
              ))}
            </div>
          )}
        </>
      )}
    </aside>
  )
}

// =============================================================================
// MOBILE SLIDE-OVER (full-screen with swipe)
// =============================================================================

function MobileSlideOver({ open, title, onClose, children }) {
  const panelRef = useRef(null)
  const touchStartX = useRef(0)
  const touchDeltaX = useRef(0)
  const isDragging = useRef(false)
  
  // Swipe-to-close handler
  const handleTouchStart = useCallback((e) => {
    // Only handle touch near left edge (50px) for swipe-back
    if (e.touches[0].clientX > 50) return
    touchStartX.current = e.touches[0].clientX
    touchDeltaX.current = 0
    isDragging.current = true
  }, [])
  
  const handleTouchMove = useCallback((e) => {
    if (!isDragging.current) return
    const currentX = e.touches[0].clientX
    const delta = currentX - touchStartX.current
    
    // Only allow dragging right (positive delta)
    if (delta > 0) {
      touchDeltaX.current = delta
      if (panelRef.current) {
        panelRef.current.style.transform = `translateX(${delta}px)`
        panelRef.current.style.transition = 'none'
      }
    }
  }, [])
  
  const handleTouchEnd = useCallback(() => {
    if (!isDragging.current) return
    isDragging.current = false
    
    if (panelRef.current) {
      panelRef.current.style.transition = ''
      panelRef.current.style.transform = ''
    }
    
    // Close if swiped more than 100px right
    if (touchDeltaX.current > 100) {
      onClose?.()
    }
  }, [onClose])
  
  return (
    <div
      ref={panelRef}
      role="dialog"
      aria-modal="true"
      aria-label={title}
      className={cn(
        "fixed inset-0 z-50 bg-bg-primary flex flex-col transition-transform duration-300 ease-out",
        open ? "translate-x-0" : "translate-x-full"
      )}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
    >
      {/* Header */}
      <div className="shrink-0 h-14 px-4 flex items-center gap-3 border-b border-border bg-bg-secondary">
        <button
          type="button"
          onClick={onClose}
          className="w-10 h-10 -ml-2 flex items-center justify-center rounded-lg text-text-secondary active:bg-bg-tertiary"
          aria-label="Back"
        >
          <CaretLeft size={24} />
        </button>
        <h2 className="text-base font-semibold text-text-primary flex-1 truncate">
          {title || 'Details'}
        </h2>
      </div>
      
      {/* Content */}
      <div className="flex-1 overflow-auto">
        {children}
      </div>
    </div>
  )
}

// =============================================================================
// MOBILE FILTER DRAWER (bottom sheet)
// =============================================================================

function MobileFilterDrawer({ open, onClose, filters, onClearFilters }) {
  const drawerRef = useRef(null)
  const touchStartY = useRef(0)
  const touchDeltaY = useRef(0)
  const isDragging = useRef(false)
  
  const activeFilterCount = filters?.filter(f => f.value && f.value !== '').length || 0
  
  // Prevent body scroll when open
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden'
      return () => { document.body.style.overflow = '' }
    }
  }, [open])
  
  // Swipe-down-to-close handler
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
      onClose?.()
    }
  }, [onClose])
  
  if (!filters || filters.length === 0) return null
  
  return (
    <>
      {/* Backdrop */}
      <div
        className={cn(
          "fixed inset-0 z-40 bg-black/40 transition-opacity duration-200",
          open ? "opacity-100" : "opacity-0 pointer-events-none"
        )}
        onClick={onClose}
        aria-hidden="true"
      />
      
      {/* Drawer */}
      <div
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-label="Filters"
        className={cn(
          "fixed left-0 right-0 bottom-0 z-50 bg-bg-secondary rounded-t-2xl shadow-2xl",
          "max-h-[80vh] flex flex-col transition-transform duration-200 ease-out",
          open ? "translate-y-0" : "translate-y-full"
        )}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {/* Drag handle */}
        <div className="flex justify-center py-3 shrink-0">
          <div className="w-10 h-1 bg-border rounded-full" />
        </div>
        
        {/* Header */}
        <div className="px-4 pb-3 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            <Funnel size={20} className="text-accent-primary" weight="bold" />
            <span className="text-base font-semibold text-text-primary">Filters</span>
            {activeFilterCount > 0 && (
              <Badge variant="primary" size="sm">{activeFilterCount}</Badge>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-10 h-10 flex items-center justify-center rounded-lg text-text-secondary active:bg-bg-tertiary"
            aria-label="Close"
          >
            <X size={22} />
          </button>
        </div>
        
        {/* Filters */}
        <div className="flex-1 overflow-auto px-4 pb-4 space-y-4">
          {filters.map(filter => (
            <FilterInput key={filter.key} filter={filter} mobile />
          ))}
        </div>
        
        {/* Footer */}
        <div className="shrink-0 border-t border-border p-4 flex gap-3 bg-bg-secondary">
          {activeFilterCount > 0 && onClearFilters && (
            <Button
              variant="ghost"
              size="md"
              onClick={() => { onClearFilters(); onClose?.(); }}
              className="flex-1"
            >
              <Eraser size={18} />
              Clear All
            </Button>
          )}
          <Button
            variant="primary"
            size="md"
            onClick={onClose}
            className="flex-1"
          >
            Apply
          </Button>
        </div>
      </div>
    </>
  )
}

// =============================================================================
// HELPER COMPONENTS
// =============================================================================

function DesktopTab({ tab, active, onClick }) {
  const Icon = tab.icon
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md transition-colors",
        active
          ? "bg-accent-primary/15 text-accent-primary"
          : "text-text-secondary hover:text-text-primary hover:bg-bg-tertiary"
      )}
    >
      {Icon && <Icon size={14} />}
      {tab.label}
      {tab.badge && <Badge variant="secondary" size="sm">{tab.badge}</Badge>}
      {tab.pro && <Badge variant="info" size="sm">Pro</Badge>}
    </button>
  )
}

function MobileTab({ tab, active, onClick }) {
  const Icon = tab.icon
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-lg transition-colors shrink-0",
        active
          ? "bg-accent-primary/15 text-accent-primary"
          : "text-text-secondary active:bg-bg-tertiary"
      )}
    >
      {Icon && <Icon size={18} />}
      {tab.label}
      {tab.badge && <Badge variant="secondary" size="sm">{tab.badge}</Badge>}
      {tab.pro && <Badge variant="info" size="sm">Pro</Badge>}
    </button>
  )
}

function StatItem({ stat, mobile }) {
  const Icon = stat.icon
  return (
    <div className="flex items-center gap-2 shrink-0">
      {Icon && <Icon size={mobile ? 16 : 14} className="text-text-tertiary" />}
      <span className={cn("text-text-tertiary", mobile ? "text-xs" : "text-xs")}>{stat.label}:</span>
      <Badge variant={stat.variant || 'secondary'} size="sm">
        {stat.value}
      </Badge>
    </div>
  )
}

function FilterInput({ filter, mobile }) {
  const { key, label, type, value, onChange, options, placeholder } = filter
  
  const inputClass = cn(
    "w-full bg-bg-tertiary border border-border rounded text-text-primary",
    "focus:outline-none focus:ring-2 focus:ring-accent-primary/50 focus:border-accent-primary",
    "transition-colors",
    mobile ? "h-11 px-3 text-base" : "h-8 px-2.5 text-sm"
  )
  
  return (
    <div className={cn(mobile ? "space-y-2" : "space-y-1.5")}>
      <label className={cn(
        "font-medium text-text-secondary uppercase tracking-wider block",
        mobile ? "text-xs" : "text-[11px]"
      )}>
        {label}
      </label>
      
      {type === 'select' && (
        <select
          value={value || ''}
          onChange={(e) => onChange(e.target.value)}
          className={cn(inputClass, "appearance-none cursor-pointer")}
        >
          <option value="">{placeholder || `All ${label}`}</option>
          {options?.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      )}
      
      {type === 'date' && (
        <input
          type="date"
          value={value || ''}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className={inputClass}
        />
      )}
      
      {type === 'text' && (
        <input
          type="text"
          value={value || ''}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder || `Filter by ${label.toLowerCase()}...`}
          className={inputClass}
        />
      )}
    </div>
  )
}

export default ResponsivePageLayout
