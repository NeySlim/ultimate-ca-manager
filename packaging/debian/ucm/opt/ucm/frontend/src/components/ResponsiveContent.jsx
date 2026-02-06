/**
 * ResponsiveContent Components
 * Mobile-first responsive components for ContentPanel
 */
import { useState } from 'react'
import { cn } from '../lib/utils'
import { DotsThreeVertical, CaretDown } from '@phosphor-icons/react'
import { useMobile } from '../contexts'
import { Button } from './Button'

/**
 * ContentHeader - Responsive header with title and actions
 * On mobile: title on top, actions in dropdown menu or stacked
 */
export function ContentHeader({ 
  title, 
  subtitle,
  badge,
  actions,  // Array of { label, icon, onClick, variant, disabled }
  breadcrumb,
  className 
}) {
  const { isMobile } = useMobile()
  const [menuOpen, setMenuOpen] = useState(false)

  // On mobile with many actions, show in dropdown
  const showDropdown = isMobile && actions?.length > 2

  return (
    <div className={cn(
      "border-b border-border bg-bg-secondary/50",
      isMobile ? "px-4 py-3" : "px-6 py-4",
      className
    )}>
      {/* Breadcrumb */}
      {breadcrumb && (
        <p className="text-xs text-text-tertiary mb-1 truncate">
          {breadcrumb}
        </p>
      )}

      {/* Title row */}
      <div className={cn(
        "flex gap-3",
        isMobile ? "flex-col" : "items-center justify-between"
      )}>
        {/* Title section */}
        <div className="flex items-center gap-3 min-w-0">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h2 className={cn(
                "font-semibold text-text-primary truncate",
                isMobile ? "text-base" : "text-lg"
              )}>
                {title}
              </h2>
              {badge}
            </div>
            {subtitle && (
              <p className="text-xs text-text-secondary mt-0.5 truncate">
                {subtitle}
              </p>
            )}
          </div>
        </div>

        {/* Actions */}
        {actions && actions.length > 0 && (
          <div className={cn(
            "flex items-center shrink-0",
            isMobile ? "gap-2 flex-wrap" : "gap-2"
          )}>
            {showDropdown ? (
              // Mobile dropdown menu
              <div className="relative w-full">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setMenuOpen(!menuOpen)}
                  className="w-full justify-center"
                >
                  Actions
                  <CaretDown size={14} className={cn(
                    "transition-transform",
                    menuOpen && "rotate-180"
                  )} />
                </Button>
                
                {menuOpen && (
                  <>
                    <div 
                      className="fixed inset-0 z-40" 
                      onClick={() => setMenuOpen(false)} 
                    />
                    <div className="absolute right-0 top-full mt-1 w-full bg-bg-secondary border border-border rounded-lg shadow-lg z-50 py-1">
                      {actions.map((action, i) => (
                        <button
                          key={i}
                          onClick={() => {
                            setMenuOpen(false)
                            action.onClick?.()
                          }}
                          disabled={action.disabled}
                          className={cn(
                            "w-full px-3 py-2.5 text-left text-sm flex items-center gap-2",
                            "hover:bg-bg-tertiary transition-colors",
                            action.variant === 'danger' && "status-danger-text",
                            action.disabled && "opacity-50 cursor-not-allowed"
                          )}
                        >
                          {action.icon && <action.icon size={16} />}
                          {action.label}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
            ) : (
              // Desktop or few actions: show all buttons (always small)
              actions.map((action, i) => (
                <Button
                  key={i}
                  variant={action.variant || 'secondary'}
                  size="sm"
                  onClick={action.onClick}
                  disabled={action.disabled}
                  className={isMobile ? "flex-1" : ""}
                >
                  {action.icon && <action.icon size={14} />}
                  <span className={isMobile && actions.length > 2 ? "sr-only" : ""}>
                    {action.label}
                  </span>
                </Button>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  )
}

/**
 * ContentBody - Scrollable content area with proper padding
 */
export function ContentBody({ children, className, noPadding = false }) {
  const { isMobile } = useMobile()
  
  return (
    <div className={cn(
      "flex-1 overflow-auto",
      !noPadding && (isMobile ? "p-4" : "p-6"),
      className
    )}>
      {children}
    </div>
  )
}

/**
 * ContentSection - Section within ContentBody
 */
export function ContentSection({ title, description, children, className }) {
  const { isMobile } = useMobile()
  
  return (
    <section className={cn("mb-6 last:mb-0", className)}>
      {title && (
        <div className="mb-4">
          <h3 className={cn(
            "font-semibold text-text-primary uppercase tracking-wide",
            isMobile ? "text-xs" : "text-sm"
          )}>
            {title}
          </h3>
          {description && (
            <p className="text-xs text-text-secondary mt-1">{description}</p>
          )}
        </div>
      )}
      {children}
    </section>
  )
}

/**
 * DataGrid - Responsive grid for displaying key-value pairs
 * Adapts from multi-column on desktop to single/dual on mobile
 */
export function DataGrid({ children, columns = 2, className }) {
  const { isMobile } = useMobile()
  
  const gridCols = {
    1: 'grid-cols-1',
    2: isMobile ? 'grid-cols-1 sm:grid-cols-2' : 'grid-cols-2',
    3: isMobile ? 'grid-cols-1 sm:grid-cols-2' : 'grid-cols-3',
    4: isMobile ? 'grid-cols-2' : 'grid-cols-4',
  }
  
  return (
    <div className={cn(
      "grid gap-4",
      gridCols[columns] || gridCols[2],
      className
    )}>
      {children}
    </div>
  )
}

/**
 * DataField - Single field in DataGrid
 */
export function DataField({ 
  label, 
  value, 
  mono = false, 
  copyable = false,
  fullWidth = false,
  className 
}) {
  const [copied, setCopied] = useState(false)
  
  const handleCopy = () => {
    if (copyable && value) {
      navigator.clipboard.writeText(String(value))
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }
  
  return (
    <div className={cn(
      fullWidth && "col-span-full",
      className
    )}>
      <p className="text-[11px] text-text-tertiary uppercase tracking-wide mb-1">
        {label}
      </p>
      <div 
        className={cn(
          "text-sm text-text-primary",
          mono && "font-mono text-xs break-all",
          copyable && "cursor-pointer hover:text-accent-primary transition-colors"
        )}
        onClick={handleCopy}
        title={copyable ? (copied ? "Copié!" : "Cliquer pour copier") : undefined}
      >
        {value || <span className="text-text-tertiary">-</span>}
        {copied && <span className="ml-2 text-xs status-success-text">✓</span>}
      </div>
    </div>
  )
}

/**
 * InfoCard - Highlighted information card
 */
export function InfoCard({ 
  variant = 'default', 
  icon: Icon,
  title, 
  children, 
  className 
}) {
  const variants = {
    default: 'bg-bg-tertiary border-border',
    info: 'status-primary-bg status-primary-border',
    success: 'status-success-bg status-success-border',
    warning: 'status-warning-bg status-warning-border',
    danger: 'status-danger-bg status-danger-border',
  }
  
  const iconColors = {
    default: 'text-text-secondary',
    info: 'status-primary-text',
    success: 'status-success-text',
    warning: 'status-warning-text',
    danger: 'status-danger-text',
  }
  
  return (
    <div className={cn(
      "p-4 rounded-lg border",
      variants[variant],
      className
    )}>
      {(Icon || title) && (
        <div className="flex items-center gap-2 mb-2">
          {Icon && <Icon size={18} className={iconColors[variant]} />}
          {title && (
            <h4 className="text-sm font-medium text-text-primary">{title}</h4>
          )}
        </div>
      )}
      <div className="text-sm text-text-secondary">
        {children}
      </div>
    </div>
  )
}

/**
 * ActionBar - Fixed bottom bar for mobile actions
 */
export function ActionBar({ children, className }) {
  const { isMobile } = useMobile()
  
  if (!isMobile) return null
  
  return (
    <div className={cn(
      "fixed bottom-0 left-0 right-0 z-30",
      "px-4 py-3 bg-bg-secondary border-t border-border",
      "flex items-center gap-2",
      "safe-area-inset-bottom",
      className
    )}>
      {children}
    </div>
  )
}

/**
 * TabsResponsive - Horizontally scrollable tabs for mobile
 */
export function TabsResponsive({ tabs, activeTab, onChange, className }) {
  const { isMobile } = useMobile()
  
  return (
    <div className={cn(
      "border-b border-border",
      isMobile ? "-mx-4 px-4" : "",
      className
    )}>
      <div className={cn(
        "flex",
        isMobile ? "overflow-x-auto scrollbar-hide gap-1 pb-px" : "gap-1"
      )}>
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-2 text-sm font-medium whitespace-nowrap",
              "border-b-2 transition-colors",
              activeTab === tab.id
                ? "border-accent-primary text-accent-primary"
                : "border-transparent text-text-secondary hover:text-text-primary hover:border-border"
            )}
          >
            {tab.icon && <tab.icon size={16} />}
            {tab.label}
          </button>
        ))}
      </div>
    </div>
  )
}

/**
 * DetailView - Common pattern for item detail pages
 */
export function DetailView({
  header,      // ContentHeader props
  tabs,        // Array of { id, label, icon, content }
  defaultTab,
  footer,      // Optional footer content
  className
}) {
  const [activeTab, setActiveTab] = useState(defaultTab || tabs?.[0]?.id)
  const activeContent = tabs?.find(t => t.id === activeTab)?.content
  
  return (
    <div className={cn("flex flex-col h-full", className)}>
      {/* Header */}
      {header && <ContentHeader {...header} />}
      
      {/* Tabs */}
      {tabs && tabs.length > 1 && (
        <TabsResponsive
          tabs={tabs}
          activeTab={activeTab}
          onChange={setActiveTab}
        />
      )}
      
      {/* Content */}
      <ContentBody>
        {activeContent}
      </ContentBody>
      
      {/* Footer */}
      {footer}
    </div>
  )
}
