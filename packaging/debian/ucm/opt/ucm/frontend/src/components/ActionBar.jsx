/**
 * ActionBar Component - Responsive action buttons container
 * 
 * DESKTOP:
 * - Compact inline buttons
 * - Icon + text for primary actions
 * - Icon-only for secondary actions
 * - Grouped with dividers
 * 
 * MOBILE:
 * - Full-width buttons or FAB
 * - Larger touch targets (44px min)
 * - Sticky at bottom or in header
 * - Overflow menu for many actions
 * 
 * Usage:
 * <ActionBar
 *   primary={<Button onClick={create}>New Certificate</Button>}
 *   secondary={[
 *     <Button variant="secondary" onClick={refresh}>Refresh</Button>,
 *     <Button variant="secondary" onClick={export}>Export</Button>
 *   ]}
 *   position="header" // 'header' | 'footer' | 'floating'
 * />
 */
import { useState, useRef } from 'react'
import { DotsThree, X } from '@phosphor-icons/react'
import { cn } from '../lib/utils'
import { useMobile } from '../contexts'
import { Button } from './Button'

export function ActionBar({
  // Primary action (always visible)
  primary,
  // Secondary actions (may be in overflow on mobile)
  secondary = [],
  // Position: 'header' (inline), 'footer' (sticky bottom), 'floating' (FAB)
  position = 'header',
  // Show divider between groups
  divider = true,
  // Custom className
  className
}) {
  const { isMobile } = useMobile()
  const [overflowOpen, setOverflowOpen] = useState(false)
  const overflowRef = useRef(null)

  // Close overflow when clicking outside
  const handleClickOutside = (e) => {
    if (overflowRef.current && !overflowRef.current.contains(e.target)) {
      setOverflowOpen(false)
    }
  }

  // Convert secondary to array if single element
  const secondaryActions = Array.isArray(secondary) ? secondary : [secondary].filter(Boolean)
  const hasSecondary = secondaryActions.length > 0

  // ============================================
  // DESKTOP LAYOUT
  // ============================================
  if (!isMobile) {
    return (
      <div className={cn("flex items-center gap-2", className)}>
        {/* Primary action */}
        {primary}
        
        {/* Divider */}
        {divider && primary && hasSecondary && (
          <div className="w-px h-5 bg-border mx-1" />
        )}
        
        {/* Secondary actions */}
        {secondaryActions}
      </div>
    )
  }

  // ============================================
  // MOBILE: Header position
  // ============================================
  if (position === 'header') {
    // Show primary + overflow menu if many secondary
    const showOverflow = secondaryActions.length > 2
    const visibleSecondary = showOverflow ? secondaryActions.slice(0, 1) : secondaryActions
    const overflowSecondary = showOverflow ? secondaryActions.slice(1) : []

    return (
      <div className={cn("flex items-center gap-2", className)}>
        {/* Primary action */}
        {primary}
        
        {/* Visible secondary */}
        {visibleSecondary}
        
        {/* Overflow menu */}
        {overflowSecondary.length > 0 && (
          <div className="relative" ref={overflowRef}>
            <Button
              variant="ghost"
              size="md"
              onClick={() => setOverflowOpen(!overflowOpen)}
              className="w-11 h-11 p-0"
            >
              {overflowOpen ? <X size={20} /> : <DotsThree size={24} weight="bold" />}
            </Button>
            
            {/* Dropdown */}
            {overflowOpen && (
              <>
                <div 
                  className="fixed inset-0 z-40" 
                  onClick={() => setOverflowOpen(false)} 
                />
                <div className="absolute right-0 top-full mt-1 z-50 bg-bg-secondary border border-border rounded-lg shadow-lg py-1 min-w-[160px]">
                  {overflowSecondary.map((action, i) => (
                    <div 
                      key={i} 
                      className="px-2 py-1"
                      onClick={() => setOverflowOpen(false)}
                    >
                      {action}
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    )
  }

  // ============================================
  // MOBILE: Footer position (sticky bottom)
  // ============================================
  if (position === 'footer') {
    return (
      <div className={cn(
        "fixed left-0 right-0 bottom-0 z-30",
        "bg-bg-secondary border-t border-border",
        "p-4 flex gap-3",
        "safe-area-inset-bottom",
        className
      )}>
        {/* Secondary actions (smaller) */}
        {hasSecondary && (
          <div className="flex gap-2">
            {secondaryActions.map((action, i) => (
              <div key={i} className="shrink-0">
                {action}
              </div>
            ))}
          </div>
        )}
        
        {/* Primary action (grows to fill) */}
        {primary && (
          <div className="flex-1">
            {primary}
          </div>
        )}
      </div>
    )
  }

  // ============================================
  // MOBILE: Floating position (FAB)
  // ============================================
  if (position === 'floating') {
    return (
      <div className={cn(
        "fixed right-4 bottom-4 z-30",
        "safe-area-inset-bottom",
        className
      )}>
        {/* FAB button */}
        <div className="relative">
          {/* Secondary actions (expand upward when clicked) */}
          {hasSecondary && overflowOpen && (
            <div className="absolute bottom-full right-0 mb-2 flex flex-col gap-2">
              {secondaryActions.map((action, i) => (
                <div 
                  key={i} 
                  className="animate-in slide-in-from-bottom-2 fade-in duration-150"
                  style={{ animationDelay: `${i * 50}ms` }}
                  onClick={() => setOverflowOpen(false)}
                >
                  {action}
                </div>
              ))}
            </div>
          )}
          
          {/* Main FAB */}
          {hasSecondary ? (
            <Button
              variant="primary"
              size="lg"
              onClick={() => setOverflowOpen(!overflowOpen)}
              className="w-14 h-14 rounded-full shadow-lg p-0"
            >
              {overflowOpen ? <X size={24} /> : <DotsThree size={28} weight="bold" />}
            </Button>
          ) : (
            primary
          )}
        </div>
      </div>
    )
  }

  // Default: just render primary
  return primary
}

// ============================================
// HEADER BAR: Complete page header with title, tabs, and actions
// ============================================

export function HeaderBar({
  // Title
  title,
  // Subtitle or breadcrumb
  subtitle,
  // Tabs (optional)
  tabs,           // [{ id, label, icon, badge }]
  activeTab,
  onTabChange,
  // Actions
  actions,
  // Help button
  helpContent,
  onHelpClick,
  // Stats (shown below title on mobile)
  stats,
  // Custom className
  className
}) {
  const { isMobile } = useMobile()

  // ============================================
  // MOBILE HEADER
  // ============================================
  if (isMobile) {
    return (
      <header className={cn("shrink-0 bg-bg-secondary border-b border-border", className)}>
        {/* Top row: Title + Actions */}
        <div className="h-14 px-4 flex items-center justify-between gap-3">
          <div className="flex-1 min-w-0">
            <h1 className="text-base font-semibold text-text-primary truncate">{title}</h1>
            {subtitle && !tabs && (
              <p className="text-xs text-text-tertiary truncate">{subtitle}</p>
            )}
          </div>
          
          <div className="flex items-center gap-2 shrink-0">
            {actions}
          </div>
        </div>
        
        {/* Tabs row (if present) */}
        {tabs && tabs.length > 0 && (
          <div className="px-4 pb-2 flex gap-1 overflow-x-auto">
            {tabs.map(tab => {
              const Icon = tab.icon
              const isActive = activeTab === tab.id
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => onTabChange?.(tab.id)}
                  className={cn(
                    "flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg transition-colors whitespace-nowrap",
                    isActive 
                      ? "bg-accent-primary/15 text-accent-primary" 
                      : "text-text-secondary hover:text-text-primary hover:bg-bg-tertiary"
                  )}
                >
                  {Icon && <Icon size={16} />}
                  {tab.label}
                  {tab.badge && (
                    <span className="ml-1 px-1.5 py-0.5 text-2xs bg-accent-primary/20 rounded-full">
                      {tab.badge}
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        )}
        
        {/* Stats row (if present) */}
        {stats && stats.length > 0 && (
          <div className="px-4 pb-3 flex flex-wrap gap-3">
            {stats.map((stat, i) => (
              <div key={i} className="flex items-center gap-1.5 text-xs">
                <span className="text-text-tertiary">{stat.label}:</span>
                <span className={cn("font-medium", stat.color || "text-text-primary")}>
                  {stat.value}
                </span>
              </div>
            ))}
          </div>
        )}
      </header>
    )
  }

  // ============================================
  // DESKTOP HEADER
  // ============================================
  return (
    <header className={cn(
      "shrink-0 px-6 py-4 bg-bg-secondary border-b border-border",
      className
    )}>
      <div className="flex items-center justify-between gap-4">
        {/* Left: Title + Tabs */}
        <div className="flex items-center gap-4 min-w-0">
          <div>
            <h1 className="text-lg font-semibold text-text-primary">{title}</h1>
            {subtitle && !tabs && (
              <p className="text-xs text-text-tertiary mt-0.5">{subtitle}</p>
            )}
          </div>
          
          {/* Tabs */}
          {tabs && tabs.length > 0 && (
            <div className="flex gap-1 ml-2">
              {tabs.map(tab => {
                const Icon = tab.icon
                const isActive = activeTab === tab.id
                return (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => onTabChange?.(tab.id)}
                    className={cn(
                      "flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md transition-colors",
                      isActive 
                        ? "bg-accent-primary/15 text-accent-primary" 
                        : "text-text-secondary hover:text-text-primary hover:bg-bg-tertiary"
                    )}
                  >
                    {Icon && <Icon size={14} />}
                    {tab.label}
                    {tab.badge && (
                      <span className="ml-1 px-1.5 py-0.5 text-2xs bg-accent-primary/20 rounded-full">
                        {tab.badge}
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          )}
        </div>
        
        {/* Right: Stats + Actions */}
        <div className="flex items-center gap-4 shrink-0">
          {/* Stats */}
          {stats && stats.length > 0 && (
            <div className="flex items-center gap-4 text-xs">
              {stats.map((stat, i) => (
                <div key={i} className="flex items-center gap-1.5">
                  <span className="text-text-tertiary">{stat.label}:</span>
                  <span className={cn("font-medium", stat.color || "text-text-primary")}>
                    {stat.value}
                  </span>
                </div>
              ))}
            </div>
          )}
          
          {/* Divider between stats and actions */}
          {stats && stats.length > 0 && actions && (
            <div className="w-px h-5 bg-border" />
          )}
          
          {/* Actions */}
          {actions}
        </div>
      </div>
    </header>
  )
}

export default ActionBar
