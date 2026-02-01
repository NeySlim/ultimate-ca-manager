/**
 * DetailCard Components - Mix of Header A + Sections B
 * Modern card header with clean minimal sections
 * Theme-aware soft color palette
 */
import { useState } from 'react'
import { cn } from '../lib/utils'
import { 
  Copy, Check, CaretDown,
  // Auto-icon mapping
  Globe, MapPin, Buildings, Flag, Key, Lock, ShieldCheck, 
  Hash, Calendar, Clock, Fingerprint, Envelope, User,
  Certificate, FileText, Code, Database
} from '@phosphor-icons/react'
import { useMobile } from '../contexts'
import { Badge } from './Badge'
import { Button } from './Button'

// Auto-icon mapping for common field labels
const FIELD_ICONS = {
  // Location
  'country': Flag,
  'state': MapPin,
  'province': MapPin,
  'locality': MapPin,
  'city': MapPin,
  'organization': Buildings,
  'org': Buildings,
  'org unit': Buildings,
  'organizational unit': Buildings,
  'ou': Buildings,
  
  // Certificate fields
  'common name': Globe,
  'cn': Globe,
  'serial': Hash,
  'serial number': Hash,
  'key type': Key,
  'key algorithm': Key,
  'key size': Key,
  'sig algo': ShieldCheck,
  'signature algorithm': ShieldCheck,
  'signature': ShieldCheck,
  'cert type': Certificate,
  'certificate type': Certificate,
  'type': FileText,
  
  // Security
  'fingerprint': Fingerprint,
  'thumbprint': Fingerprint,
  'sha-1': Fingerprint,
  'sha-256': Fingerprint,
  'sha1': Fingerprint,
  'sha256': Fingerprint,
  
  // Time
  'valid from': Calendar,
  'valid until': Calendar,
  'not before': Calendar,
  'not after': Calendar,
  'expires': Clock,
  'expiry': Clock,
  'created': Calendar,
  'updated': Calendar,
  
  // Contact
  'email': Envelope,
  'user': User,
  'username': User,
  'created by': User,
  
  // Technical
  'issuer': Certificate,
  'ca': Certificate,
  'ca reference': Database,
  'caref': Database,
  'reference id': Hash,
  'refid': Hash,
}

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
  // Use dropdown when: mobile with 2+ actions OR desktop with 3+ actions (narrow panels)
  const showDropdown = (isMobile && actions?.length > 1) || actions?.length > 2

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
                            action.variant === 'danger' && "status-danger-text",
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
              <div className="flex items-center gap-2">
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
 * @param {boolean} compact - Use compact layout with less padding
 */
export function DetailSection({ title, description, children, className, noBorder = false, compact = false }) {
  const { isMobile } = useMobile()
  
  return (
    <section className={cn(compact ? "py-1.5" : "py-2.5", className)}>
      {title && (
        <div className="mb-2">
          <h2 className={cn(
            "font-semibold text-text-secondary tracking-wide",
            isMobile ? "text-xs" : "text-sm"
          )}>
            {title}
          </h2>
          {description && (
            <p className="text-xs text-text-tertiary mt-0.5">{description}</p>
          )}
        </div>
      )}
      {/* Content in a framed card - uses theme-aware class */}
      <div className={cn(
        "rounded-lg",
        compact ? "p-2" : "p-2.5",
        !noBorder && "detail-section-frame"
      )}>
        {children}
      </div>
    </section>
  )
}

/**
 * DetailGrid - Responsive grid for key-value pairs (Style B)
 * Always uses 3 columns on desktop for better space utilization
 * Use columns={1} for single-column content like URLs
 */
export function DetailGrid({ children, columns = 2, className }) {
  const { isMobile } = useMobile()
  
  // 1 column = single column, anything else = 3 columns on desktop
  const gridClasses = isMobile 
    ? "grid-cols-1" 
    : columns === 1 
      ? "grid-cols-1"
      : "grid-cols-3"
  
  return (
    <dl className={cn(
      "grid gap-1.5",
      gridClasses,
      className
    )}>
      {children}
    </dl>
  )
}

/**
 * DetailField - Single field in DetailGrid with subtle frame
 * Theme-aware styling
 * @param {boolean} compact - Use compact layout with less padding
 */
export function DetailField({ 
  label, 
  value, 
  mono = false, 
  copyable = false,
  fullWidth = false,
  compact = false,
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
      "rounded-md detail-field-frame",
      compact ? "p-1.5" : "p-2",
      fullWidth && "col-span-full",
      className
    )}>
      <dt className={cn(
        "text-text-tertiary uppercase tracking-wide",
        compact ? "text-[9px] mb-0.5" : "text-[10px] mb-0.5"
      )}>{label}</dt>
      <dd 
        className={cn(
          mono 
            ? cn("font-mono text-text-primary break-all", compact ? "text-[11px]" : "text-xs")
            : cn("text-text-primary font-medium", compact ? "text-xs" : "text-sm"),
          copyable && "cursor-pointer hover:text-accent-primary transition-colors flex items-center gap-2"
        )}
        onClick={copyable ? handleCopy : undefined}
        title={copyable ? (copied ? "Copié!" : "Cliquer pour copier") : undefined}
      >
        {value !== undefined && value !== null && value !== '' ? value : <span className="text-text-tertiary">—</span>}
        {copyable && (
          copied 
            ? <Check size={14} className="status-success-text" /> 
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
export function DetailContent({ children, className, fullWidth = true }) {
  const { isMobile } = useMobile()
  
  return (
    <div className={cn(
      "flex-1 overflow-auto",
      isMobile ? "p-4" : "p-4",
      className
    )}>
      <div className={cn(!fullWidth && "max-w-5xl")}>
        {children}
      </div>
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

// ===========================================
// COMPACT DETAIL COMPONENTS (for slide-over panels)
// ===========================================

/**
 * CompactSection - Bordered section with header
 * For use in slide-over detail panels
 * @param {boolean} collapsible - Allow expand/collapse
 * @param {boolean} defaultOpen - Initial state if collapsible
 */
export function CompactSection({ title, children, className, collapsible = false, defaultOpen = true, icon: Icon }) {
  const [isOpen, setIsOpen] = useState(defaultOpen)
  
  return (
    <div className={cn(
      "border border-border rounded-lg overflow-hidden",
      className
    )}>
      <button
        type="button"
        onClick={() => collapsible && setIsOpen(!isOpen)}
        className={cn(
          "w-full px-3 py-2 flex items-center justify-between text-left",
          "bg-bg-tertiary/40 border-b border-border/30",
          collapsible && "cursor-pointer hover:bg-bg-tertiary/60 transition-colors",
          !collapsible && "cursor-default"
        )}
        disabled={!collapsible}
      >
        <div className="flex items-center gap-2">
          {Icon && (
            <div className="w-5 h-5 rounded bg-bg-tertiary flex items-center justify-center">
              <Icon size={12} className="text-text-secondary" weight="bold" />
            </div>
          )}
          <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
            {title}
          </h4>
        </div>
        {collapsible && (
          <CaretDown 
            size={14} 
            className={cn(
              "text-text-tertiary transition-transform duration-200",
              isOpen && "rotate-180"
            )} 
          />
        )}
      </button>
      <div className={cn(
        "grid transition-all duration-200 ease-out",
        isOpen ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
      )}>
        <div className="overflow-hidden">
          <div className="p-3">
            {children}
          </div>
        </div>
      </div>
    </div>
  )
}

/**
 * CompactGrid - 2-column grid for compact key-value pairs
 */
export function CompactGrid({ children, cols = 2, className }) {
  return (
    <div className={cn(
      "grid gap-x-3 gap-y-1.5 text-xs",
      cols === 2 ? "grid-cols-2" : cols === 3 ? "grid-cols-3" : "grid-cols-1",
      className
    )}>
      {children}
    </div>
  )
}

/**
 * CompactField - Inline label:value for compact display
 * @param {icon} icon - Optional icon component (or auto-detected from label)
 * @param {boolean} autoIcon - Auto-detect icon from label (default: false)
 * @param {boolean} copyable - Show copy button
 * @param {boolean} mono - Use monospace font
 */
export function CompactField({ 
  label, 
  value, 
  icon: IconProp,
  autoIcon = false,
  mono, 
  copyable,
  className, 
  colSpan 
}) {
  const [copied, setCopied] = useState(false)
  
  if (value === undefined || value === null || value === '') {
    return null // Don't render empty fields
  }
  
  // Auto-detect icon from label if autoIcon is true and no icon provided
  let Icon = IconProp
  if (!Icon && autoIcon && label) {
    const normalizedLabel = label.toLowerCase().trim()
    Icon = FIELD_ICONS[normalizedLabel]
  }
  
  const handleCopy = () => {
    if (copyable && value) {
      navigator.clipboard.writeText(String(value))
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }
  
  // If icon provided/detected, use layout with subtle icon
  if (Icon) {
    return (
      <div className={cn(
        "flex items-start gap-2 group p-1.5 -m-1.5 rounded-md transition-colors hover:bg-bg-tertiary/30",
        colSpan && `col-span-${colSpan}`,
        className
      )}>
        <div className="w-5 h-5 rounded bg-bg-tertiary/50 flex items-center justify-center shrink-0 mt-0.5">
          <Icon size={11} className="text-text-tertiary" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[10px] text-text-tertiary uppercase tracking-wider">{label}</div>
          <div className={cn(
            "text-sm text-text-primary break-all",
            mono && "font-mono text-xs"
          )}>
            {value}
          </div>
        </div>
        {copyable && (
          <button
            type="button"
            onClick={handleCopy}
            className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-bg-tertiary rounded"
            title="Copy"
          >
            {copied ? (
              <Check size={14} className="text-accent-success" />
            ) : (
              <Copy size={14} className="text-text-tertiary" />
            )}
          </button>
        )}
      </div>
    )
  }
  
  // Standard inline layout (no icon)
  return (
    <div 
      className={cn(
        colSpan && `col-span-${colSpan}`, 
        copyable && "cursor-pointer group",
        className
      )}
      onClick={copyable ? handleCopy : undefined}
    >
      <span className="text-text-tertiary">{label}:</span>
      <span className={cn("ml-1 text-text-primary", mono && "font-mono text-xs")}>
        {value}
      </span>
      {copyable && (
        <span className="inline-flex ml-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {copied ? (
            <Check size={12} className="text-status-success" />
          ) : (
            <Copy size={12} className="text-text-tertiary" />
          )}
        </span>
      )}
    </div>
  )
}

/**
 * CompactStats - Horizontal stats bar
 */
export function CompactStats({ stats, className }) {
  return (
    <div className={cn(
      "flex items-center justify-between text-xs",
      "bg-bg-tertiary/50 rounded-lg px-3 py-2 border border-border",
      className
    )}>
      {stats.map((stat, i) => (
        <div key={i} className="flex items-center gap-1.5">
          {stat.icon && <stat.icon size={14} className={stat.iconClass || "text-text-tertiary"} />}
          <span className="text-text-secondary">{stat.value}</span>
          {stat.badge && (
            <Badge variant={stat.badgeVariant || 'secondary'} size="sm">
              {stat.badge}
            </Badge>
          )}
        </div>
      ))}
    </div>
  )
}

/**
 * CompactActions - Action buttons row
 */
export function CompactActions({ children, className }) {
  return (
    <div className={cn("flex gap-2", className)}>
      {children}
    </div>
  )
}

/**
 * CompactHeader - Minimal header with icon, title, badge
 */
export function CompactHeader({ 
  icon: Icon, 
  iconClass,
  title, 
  subtitle, 
  badge,
  className 
}) {
  return (
    <div className={cn("flex items-start gap-3 pb-3 border-b border-border", className)}>
      {Icon && (
        <div className={cn(
          "w-10 h-10 rounded-lg flex items-center justify-center shrink-0",
          iconClass || "bg-accent-primary/20"
        )}>
          <Icon size={20} className="text-accent-primary" />
        </div>
      )}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <h3 className="font-semibold text-text-primary truncate">{title}</h3>
          {badge}
        </div>
        {subtitle && (
          <p className="text-xs text-text-tertiary truncate">{subtitle}</p>
        )}
      </div>
    </div>
  )
}
