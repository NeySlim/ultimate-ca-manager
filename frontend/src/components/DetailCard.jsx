/**
 * DetailCard Components - Mix of Header A + Sections B
 * Modern card header with clean minimal sections
 * Theme-aware soft color palette
 */
import { useState } from 'react'
import { cn } from '../lib/utils'
import { Copy, Check, CaretDown } from '@phosphor-icons/react'
import { useMobile } from '../contexts'
import { Badge } from './Badge'
import { Button } from './Button'

/**
 * DetailHeader - Soft gradient card header with icon (Style A)
 * Uses CSS variables for theme compatibility
 */
export function DetailHeader({
  icon: Icon,
  title,
  subtitle,
  badge,
  stats,      // Array of { icon, label, value }
  actions,    // Array of { label, icon, onClick, variant }
  className
}) {
  const { isMobile } = useMobile()
  const [menuOpen, setMenuOpen] = useState(false)
  const showDropdown = isMobile && actions?.length > 2

  return (
    <div className={cn(
      "relative overflow-hidden rounded-xl detail-header-gradient",
      isMobile ? "p-4" : "p-5",
      className
    )}>
      {/* Main row */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3 md:gap-4 min-w-0">
          {Icon && (
            <div className={cn(
              "rounded-xl detail-icon-gradient",
              "flex items-center justify-center shrink-0",
              isMobile ? "w-11 h-11" : "w-14 h-14"
            )}>
              <Icon size={isMobile ? 22 : 28} className="text-white" weight="duotone" />
            </div>
          )}
          <div className="min-w-0">
            <h2 className={cn(
              "font-bold text-text-primary truncate",
              isMobile ? "text-base" : "text-xl"
            )}>
              {title}
            </h2>
            {subtitle && (
              <p className="text-xs md:text-sm text-text-secondary mt-0.5 truncate">
                {subtitle}
              </p>
            )}
          </div>
        </div>
        
        <div className="flex items-center gap-2 shrink-0">
          {badge}
          
          {/* Actions */}
          {actions && actions.length > 0 && (
            showDropdown ? (
              <div className="relative">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setMenuOpen(!menuOpen)}
                >
                  Actions
                  <CaretDown size={12} className={cn("transition-transform", menuOpen && "rotate-180")} />
                </Button>
                
                {menuOpen && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setMenuOpen(false)} />
                    <div className="absolute right-0 top-full mt-1 w-40 bg-bg-secondary border border-border rounded-lg shadow-lg z-50 py-1">
                      {actions.map((action, i) => (
                        <button
                          key={i}
                          onClick={() => { setMenuOpen(false); action.onClick?.() }}
                          disabled={action.disabled}
                          className={cn(
                            "w-full px-3 py-2 text-left text-sm flex items-center gap-2",
                            "hover:bg-bg-tertiary transition-colors",
                            action.variant === 'danger' && "text-red-500",
                            action.disabled && "opacity-50"
                          )}
                        >
                          {action.icon && <action.icon size={14} />}
                          {action.label}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
            ) : (
              <div className="hidden md:flex items-center gap-2">
                {actions.map((action, i) => (
                  <Button
                    key={i}
                    variant={action.variant || 'secondary'}
                    size="sm"
                    onClick={action.onClick}
                    disabled={action.disabled}
                  >
                    {action.icon && <action.icon size={14} />}
                    {action.label}
                  </Button>
                ))}
              </div>
            )
          )}
        </div>
      </div>

      {/* Stats row */}
      {stats && stats.length > 0 && (
        <div className={cn(
          "flex flex-wrap gap-4 md:gap-6 mt-4 pt-4 border-t detail-stats-border",
        )}>
          {stats.map((stat, i) => (
            <div key={i} className="flex items-center gap-2">
              {stat.icon && <stat.icon size={16} className="text-accent-primary" />}
              <span className="text-xs md:text-sm text-text-secondary">
                {stat.label} <strong className="text-text-primary">{stat.value}</strong>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * DetailSection - Clean minimal section with card frame (Style B + frames)
 * Theme-aware styling
 */
export function DetailSection({ title, description, children, className, noBorder = false }) {
  const { isMobile } = useMobile()
  
  return (
    <section className={cn("py-4 md:py-5", className)}>
      {title && (
        <div className="mb-3">
          <h2 className={cn(
            "font-bold text-text-tertiary uppercase tracking-widest",
            isMobile ? "text-[10px]" : "text-xs"
          )}>
            {title}
          </h2>
          {description && (
            <p className="text-xs text-text-secondary mt-1">{description}</p>
          )}
        </div>
      )}
      {/* Content in a framed card - uses theme-aware class */}
      <div className={cn(
        "rounded-lg p-4",
        !noBorder && "detail-section-frame"
      )}>
        {children}
      </div>
    </section>
  )
}

/**
 * DetailGrid - Responsive grid for key-value pairs (Style B)
 */
export function DetailGrid({ children, columns = 2, className }) {
  const { isMobile } = useMobile()
  
  return (
    <dl className={cn(
      "grid gap-3",
      isMobile ? "grid-cols-1" : columns === 2 ? "grid-cols-2" : columns === 3 ? "grid-cols-3" : "grid-cols-1",
      className
    )}>
      {children}
    </dl>
  )
}

/**
 * DetailField - Single field in DetailGrid with subtle frame
 * Theme-aware styling
 */
export function DetailField({ 
  label, 
  value, 
  mono = false, 
  copyable = false,
  fullWidth = false,
  className 
}) {
  const [copied, setCopied] = useState(false)
  const { isMobile } = useMobile()
  
  const handleCopy = () => {
    if (copyable && value) {
      navigator.clipboard.writeText(String(value))
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }
  
  return (
    <div className={cn(
      "rounded-md p-3 detail-field-frame",
      fullWidth && "col-span-full",
      className
    )}>
      <dt className="text-[10px] md:text-xs text-text-tertiary uppercase tracking-wide mb-1">{label}</dt>
      <dd 
        className={cn(
          mono 
            ? "font-mono text-xs text-text-primary break-all" 
            : "text-sm text-text-primary font-medium",
          copyable && "cursor-pointer hover:text-accent-primary transition-colors flex items-center gap-2"
        )}
        onClick={copyable ? handleCopy : undefined}
        title={copyable ? (copied ? "Copié!" : "Cliquer pour copier") : undefined}
      >
        {value || <span className="text-text-tertiary">—</span>}
        {copyable && (
          copied 
            ? <Check size={14} className="text-emerald-500" /> 
            : <Copy size={14} className="text-text-tertiary opacity-30" />
        )}
      </dd>
    </div>
  )
}

/**
 * DetailDivider - Section separator (subtle)
 */
export function DetailDivider({ className }) {
  return <div className={cn("h-px bg-border/30 my-1", className)} />
}

/**
 * DetailContent - Main content wrapper with proper spacing
 */
export function DetailContent({ children, className }) {
  const { isMobile } = useMobile()
  
  return (
    <div className={cn(
      "flex-1 overflow-auto",
      isMobile ? "p-4" : "p-6",
      className
    )}>
      {children}
    </div>
  )
}

/**
 * DetailTabs - Responsive tabs for detail view
 */
export function DetailTabs({ tabs, activeTab, onChange, className }) {
  const { isMobile } = useMobile()
  
  return (
    <div className={cn("border-b border-border bg-bg-secondary/30", className)}>
      <div className={cn(
        "flex",
        isMobile ? "overflow-x-auto scrollbar-hide gap-0 px-4" : "gap-0 px-6"
      )}>
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            className={cn(
              "flex items-center gap-1.5 px-4 py-3 text-sm font-medium whitespace-nowrap",
              "border-b-2 transition-all -mb-px",
              activeTab === tab.id
                ? "border-accent-primary text-accent-primary bg-accent-primary/5"
                : "border-transparent text-text-secondary hover:text-text-primary hover:bg-bg-tertiary/50"
            )}
          >
            {tab.icon && <tab.icon size={16} />}
            {tab.label}
            {tab.count !== undefined && (
              <span className={cn(
                "ml-1 px-1.5 py-0.5 rounded text-xs",
                activeTab === tab.id ? "bg-accent-primary/20" : "bg-bg-tertiary"
              )}>
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  )
}
