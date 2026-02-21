/**
 * UnifiedPageHeader - Global header component for all pages
 * Based on Settings page design (the reference)
 * 
 * Features:
 * - Icon with gradient background
 * - Title + subtitle
 * - Tabs (optional) - Settings style with underline
 * - Filters (optional) - inline on desktop, button on mobile
 * - Actions (optional) - help button, custom actions
 * - Mobile responsive
 */
import { cn } from '../../lib/utils'
import { Question, Funnel } from '@phosphor-icons/react'
import { Badge } from '../Badge'
import { FilterSelect } from './Select'

export function UnifiedPageHeader({
  // Title section
  icon: Icon,
  title,
  subtitle,
  badge,
  
  // Tabs (optional)
  tabs,
  activeTab,
  onTabChange,
  
  // Filters (optional)
  filters,
  activeFilters = 0,
  onClearFilters,
  onOpenFilters,
  
  // Actions (optional)
  actions,
  onHelpClick,
  showHelp = false,
  
  // Mobile
  isMobile = false,
  
  // Custom className
  className
}) {
  const hasTabs = tabs && tabs.length > 0
  const hasFilters = filters && filters.length > 0

  return (
    <div className={cn(
      'shrink-0 border-b border-border-op60 bg-bg-secondary shadow-[inset_0_-1px_0_rgba(255,255,255,0.03)]',
      className
    )}>
      {/* Title row - HIDDEN on mobile (title already in AppShell navbar) */}
      {!isMobile && (
      <div className={cn(
        'flex items-center justify-between',
        isMobile ? 'px-3 py-2' : 'px-6 py-3'
      )}>
        {/* Left: Icon + Title */}
        <div className="flex items-center gap-2 min-w-0">
          {Icon && (
            <div className={cn(
              "rounded-lg bg-gradient-to-br from-accent-primary to-accent-primary-op70 flex items-center justify-center shrink-0 shadow-sm",
              isMobile ? "w-7 h-7" : "w-9 h-9"
            )}>
              <Icon size={isMobile ? 14 : 18} weight="bold" className="text-white" />
            </div>
          )}
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className={cn(
                "font-semibold text-text-primary truncate",
                isMobile ? "text-sm" : "text-lg"
              )}>
                {title}
              </h1>
              {badge}
            </div>
            {subtitle && !isMobile && (
              <p className="text-sm text-text-secondary truncate">
                {subtitle}
              </p>
            )}
          </div>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-1.5 shrink-0">
          {/* Desktop: Inline filters */}
          {!isMobile && hasFilters && (
            <div className="flex items-center gap-2">
              {filters.slice(0, 3).map((filter) => (
                <FilterSelect
                  key={filter.key}
                  value={filter.value || ''}
                  onChange={filter.onChange}
                  placeholder={filter.placeholder || `All ${filter.label}`}
                  options={filter.options || []}
                  size="sm"
                />
              ))}
              {activeFilters > 0 && (
                <button
                  onClick={onClearFilters}
                  className="text-xs text-accent-primary hover:underline"
                >
                  Clear
                </button>
              )}
            </div>
          )}
          
          {/* Mobile: Filter button */}
          {isMobile && hasFilters && (
            <button
              onClick={onOpenFilters}
              className={cn(
                'relative flex items-center justify-center rounded-lg',
                'bg-bg-tertiary hover:bg-bg-hover border border-border',
                'h-8 w-8',
                'transition-colors'
              )}
            >
              <Funnel size={16} className="text-text-secondary" />
              {activeFilters > 0 && (
                <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-accent-primary text-white text-2xs flex items-center justify-center">
                  {activeFilters}
                </span>
              )}
            </button>
          )}
          
          {/* Custom actions */}
          {actions}
          
          {/* Help button */}
          {showHelp && onHelpClick && (
            isMobile ? (
              <button
                onClick={onHelpClick}
                className={cn(
                  'flex items-center justify-center rounded-lg',
                  'bg-bg-tertiary hover:bg-bg-hover border border-border',
                  'h-8 w-8',
                  'transition-colors'
                )}
              >
                <Question size={16} className="text-text-secondary" />
              </button>
            ) : (
              <button
                onClick={onHelpClick}
                className={cn(
                  "flex items-center gap-1.5 px-2.5 py-1.5 rounded-md transition-all",
                  "bg-accent-primary-op10 border border-accent-primary-op30",
                  "text-accent-primary hover:bg-accent-primary-op20",
                  "text-xs font-medium"
                )}
              >
                <Question size={14} weight="bold" />
                <span className="hidden sm:inline">Help</span>
              </button>
            )
          )}
        </div>
      </div>
      )}

      {/* Tabs row (if provided) */}
      {hasTabs && (
        <div className={cn(
          'overflow-x-auto scrollbar-hide',
          isMobile ? 'px-3' : 'px-6'
        )}>
          <div className="flex gap-0.5 min-w-max pb-0">
            {tabs.map((tab) => {
              const TabIcon = tab.icon
              const isActive = activeTab === tab.id
              return (
                <button
                  key={tab.id}
                  onClick={() => onTabChange?.(tab.id)}
                  className={cn(
                    "flex items-center gap-1.5 rounded-t-lg text-sm font-medium transition-all",
                    "border-b-2 -mb-px",
                    isMobile ? "px-2.5 py-1.5" : "px-3 py-2",
                    isActive
                      ? "border-accent-primary text-accent-primary bg-bg-primary"
                      : "border-transparent text-text-secondary hover:text-text-primary hover:bg-tertiary-op50"
                  )}
                >
                  {TabIcon && (
                    <TabIcon size={isMobile ? 14 : 16} weight={isActive ? "fill" : "regular"} />
                  )}
                  <span className={isMobile && !isActive ? "hidden" : ""}>
                    {tab.label}
                  </span>
                  {tab.count !== undefined && (
                    <span className={cn(
                      'px-1.5 py-0.5 rounded-full text-2xs font-medium',
                      isActive
                        ? 'bg-accent-primary-op15 text-accent-primary'
                        : 'bg-bg-tertiary text-text-tertiary'
                    )}>
                      {tab.count}
                    </span>
                  )}
                  {tab.badge && (
                    <Badge variant={tab.badge.variant || 'info'} size="sm">
                      {tab.badge.label}
                    </Badge>
                  )}
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

export default UnifiedPageHeader
