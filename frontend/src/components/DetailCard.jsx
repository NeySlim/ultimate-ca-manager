/**
 * DetailCard Components - Mix of Header A + Sections B
 * Modern card header with clean minimal sections
 * Theme-aware soft color palette
 */
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '../lib/utils'
import { 
  Copy, Check, CaretDown,
  // Auto-icon mapping
  Globe, MapPin, Buildings, Flag, Key, ShieldCheck, 
  Hash, Calendar, Clock, Fingerprint, Envelope, User,
  Certificate, FileText, Database, Lock, Lightning,
  Link, Shield, ListBullets, Eye, Warning, ArrowsClockwise
} from '@phosphor-icons/react'
import { useMobile } from '../contexts'
import { useClipboard } from '../hooks/useClipboard'
import { Badge } from './Badge'
import { Button } from './Button'

// Auto-icon mapping by i18n key (language-independent)
const FIELD_ICONS = {
  // Location
  'country': Flag, 'state': MapPin, 'province': MapPin,
  'locality': MapPin, 'city': MapPin, 'stateProvince': MapPin,
  'organization': Buildings, 'orgUnit': Buildings,
  // Certificate / Identity
  'commonName': Globe, 'cn': Globe, 'name': Globe,
  'serial': Hash, 'serialNumber': Hash,
  'keyType': Key, 'keyAlgorithm': Key, 'keySize': Key,
  'algorithm': Key, 'signature': ShieldCheck,
  'signatureAlgorithm': ShieldCheck,
  'issuerSignatureAlgorithm': ShieldCheck,
  'certType': Certificate, 'certificateType': Certificate, 'type': FileText,
  // Security / Fingerprints
  'fingerprint': Fingerprint, 'thumbprint': Fingerprint,
  'sha-1': Fingerprint, 'sha-256': Fingerprint, 'sha1': Fingerprint, 'sha256': Fingerprint,
  // Time
  'validFrom': Calendar, 'validUntil': Calendar, 'validTo': Calendar,
  'notBefore': Calendar, 'notAfter': Calendar,
  'expires': Clock, 'expiry': Clock, 'expiryDate': Clock,
  'created': Calendar, 'createdAt': Calendar, 'updated': Calendar, 'updatedAt': Calendar,
  'signedAt': Calendar, 'lastLogin': Clock, 'lastUpdate': Calendar, 'nextUpdate': Calendar,
  'revokedAt': Calendar, 'issued': Calendar,
  // Contact / Users
  'email': Envelope, 'user': User, 'username': User,
  'createdBy': User, 'signedBy': User, 'requester': User,
  'account': User,
  // Technical
  'issuer': Certificate, 'ca': Certificate,
  'caReference': Database, 'caref': Database,
  'referenceId': Hash, 'refid': Hash,
  'subjectDN': FileText, 'issuerDN': FileText, 'importedFrom': Database,
  'subject': Globe, 'transactionId': Hash,
  // Status / Role
  'status': ShieldCheck, 'role': User, 'description': FileText,
  'purpose': FileText, 'notes': FileText, 'version': Hash,
  'default': Calendar, 'maximum': Clock,
  // Revocation
  'reason': Warning, 'revokedCount': Warning,
  'crlNumber': Hash, 'caName': Certificate,
  // Network / TLS
  'tlsVersion': Lock, 'cipher': Lock, 'daysLeft': Clock,
  'signatureValid': ShieldCheck,
  // ACME
  'environment': Globe, 'method': Key, 'provider': Database,
  'orderStatus': ShieldCheck, 'orderId': Hash,
  'dnsRecordName': FileText, 'dnsRecordValue': FileText,
  'challengeUrl': Link, 'challengeFileContent': FileText,
  // HSM
  'slotId': Hash, 'token': Key, 'clusterId': Database,
  'region': MapPin, 'cryptoUser': User,
  'tenant': Database, 'client': Database,
  'project': Database, 'location': MapPin, 'keyRing': Key,
  // MFA
  'enable2FA': Shield, 'totp': Shield,
  // Key usage
  'keyUsage': Key, 'extKeyUsage': Key,
  // Source
  'source': Database,
  // Cache
  'totalRequests': Lightning, 'cacheHits': Lightning, 'hitRate': Lightning,
  // Custom role
  'customRole': User, 'inheritsFrom': User,
  // Tools
  'subjectCn': Globe, 'issuerCn': Certificate, 'issuerOrg': Buildings,
}

/**
 * DetailHeader - Soft gradient card header with icon (Style A)
 * Uses CSS variables for theme compatibility
 * Now supports compact mode for simpler layouts
 */
export function DetailHeader({
  icon: Icon,
  title,
  subtitle,
  badge,
  stats,      // Array of { icon, label, value }
  actions,    // Array of { label, icon, onClick, variant }
  compact,    // If true, renders a simpler inline header without card background
  className
}) {
  const { isMobile } = useMobile()
  const { t } = useTranslation()
  const [menuOpen, setMenuOpen] = useState(false)
  // Use dropdown when: mobile with 2+ actions OR desktop with 3+ actions (narrow panels)
  const showDropdown = (isMobile && actions?.length > 1) || actions?.length > 2

  // Compact mode - simple inline header without gradient card
  if (compact) {
    return (
      <div className={cn("flex items-center justify-between gap-4 mb-4", className)}>
        <div className="flex items-center gap-2 min-w-0">
          {Icon && <Icon size={18} className="text-accent-primary shrink-0" weight="duotone" />}
          <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
          {badge}
        </div>
        {actions && actions.length > 0 && (
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
        )}
      </div>
    )
  }

  return (
    <div className={cn("ui-detail-head", className)}>
      {/* Main row */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3 md:gap-4 min-w-0">
          {Icon && <Icon size={19} className="text-accent-primary shrink-0" aria-hidden="true" />}
          <div className="min-w-0">
            <h2 className="ui-detail-title truncate">
              {title}
            </h2>
            {subtitle && (
              <p className="text-xs text-text-secondary mt-0.5 truncate">
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
                  {t('common.actions')}
                  <CaretDown size={12} className={cn("transition-transform", menuOpen && "rotate-180")} />
                </Button>
                
                {menuOpen && (
                  <>
                    <div className="fixed inset-0 z-40" role="presentation" onClick={() => setMenuOpen(false)} />
                    <div className="ui-pop absolute right-0 top-full mt-1 z-50" role="menu">
                      {actions.map((action, i) => (
                        <button
                          key={i}
                          onClick={() => { setMenuOpen(false); action.onClick?.() }}
                          disabled={action.disabled}
                          type="button"
                          role="menuitem"
                          className={cn('ui-pop-item', action.variant === 'danger' && 'is-danger')}
                        >
                          {action.icon && <span className="ui-pop-icon" aria-hidden="true"><action.icon /></span>}
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
          "flex flex-wrap gap-4 md:gap-6 mt-3 pt-3 border-t border-border",
        )}>
          {stats.map((stat, i) => (
            <div key={i} className="flex items-center gap-2">
              {stat.icon && <stat.icon size={14} className="text-text-secondary" aria-hidden="true" />}
              <span className="text-xs text-text-secondary">
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
 * @param {Component} icon - Optional icon component
 * @param {string} iconClass - Optional icon background class (e.g., 'icon-bg-blue')
 */
// eslint-disable-next-line no-unused-vars
export function DetailSection({ title, description, subtitle, actions, children, className, noBorder = false, compact = false, icon: Icon, iconClass, badge }) {
  
  return (
    <section className={cn(compact ? "py-1.5" : "py-2.5", className)}>
      {title && (
        <div className="mb-2.5 flex items-center gap-2">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="ui-section-title !mb-0">
                {Icon && <Icon aria-hidden="true" />}
                {title}
              </h2>
              {badge}
            </div>
            {description && (
              <p className="text-xs text-text-tertiary mt-1">{description}</p>
            )}
          </div>
        </div>
      )}
      {/* Content in a framed card - uses theme-aware class */}
      <div className={cn(!noBorder && 'ui-detail-frame', !noBorder && compact && 'is-compact')}>
        {(subtitle || actions) && (
          <div className="flex items-center justify-between gap-4 mb-3">
            {subtitle && <p className="text-xs text-text-secondary">{subtitle}</p>}
            {actions && <div className="flex gap-2 shrink-0">{actions}</div>}
          </div>
        )}
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
  compact: _compact = false,
  className 
}) {
  // useClipboard owns both the "did it work" answer and the reset timer.
  const { copy, isCopied } = useClipboard()
  const copied = isCopied()
  const { t } = useTranslation()
  
  const handleCopy = () => {
    if (copyable && value) copy(String(value))
  }
  
  return (
    <div className={cn(
      "ui-detail-field",
      fullWidth && "col-span-full",
      className
    )}>
      <dt>{label}</dt>
      <dd 
        className={cn(
          mono && "font-mono",
          copyable && "cursor-pointer hover:text-accent-primary transition-colors flex items-center gap-2"
        )}
        onClick={copyable ? handleCopy : undefined}
        title={copyable ? (copied ? t('common.copied') : t('common.clickToCopy')) : undefined}
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
  return <div className={cn("h-px bg-border-op30 my-1", className)} />
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
    <div className={className}>
      <div className={cn(
        "ui-tabs-list",
        isMobile ? "overflow-x-auto scrollbar-hide px-4" : "px-6"
      )}>
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            type="button"
            data-state={activeTab === tab.id ? 'active' : 'inactive'}
            className="ui-tab whitespace-nowrap"
          >
            {tab.icon && <tab.icon aria-hidden="true" />}
            {tab.label}
            {tab.count !== undefined && (
              <span className="lv-counter">{tab.count}</span>
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
// eslint-disable-next-line no-unused-vars
export function CompactSection({ title, children, className, collapsible = false, defaultOpen = true, icon: Icon, iconClass, onToggle }) {
  const [isOpen, setIsOpen] = useState(defaultOpen)
  const rootRef = useRef(null)
  const openRef = useRef(isOpen)
  openRef.current = isOpen

  // A form refusing to submit fires `invalid` on each invalid field: a closed section holding one opens
  useEffect(() => {
    const root = rootRef.current
    if (!collapsible || !root) return undefined
    const reveal = () => {
      if (!openRef.current) { setIsOpen(true); onToggle?.(true) }
    }
    root.addEventListener('invalid', reveal, true)
    return () => root.removeEventListener('invalid', reveal, true)
  }, [collapsible, onToggle])

  return (
    <div ref={rootRef} className={cn("ui-compact", className)}>
      <button
        type="button"
        onClick={() => { if (collapsible) { setIsOpen(!isOpen); onToggle?.(!isOpen) } }}
        className={cn("ui-compact-head", isOpen && "is-open", !collapsible && "is-static")}
        disabled={!collapsible}
        aria-expanded={collapsible ? isOpen : undefined}
      >
        <span className="flex items-center gap-2 min-w-0">
          {Icon && <Icon size={15} className="text-text-secondary shrink-0" aria-hidden="true" />}
          <h4>{title}</h4>
        </span>
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
          <div className="ui-compact-body">
            {children}
          </div>
        </div>
      </div>
    </div>
  )
}

/**
 * CompactGrid - Responsive grid for compact key-value pairs
 * - Mobile: 1 column
 * - Desktop: 2-3 columns based on cols prop
 */
export function CompactGrid({ children, cols = 2, className }) {
  return (
    <div className={cn(
      "grid gap-x-3 gap-y-1.5 text-xs",
      // Mobile: always 1 column for readability
      "grid-cols-1",
      // Desktop: respect cols prop
      cols === 2 ? "sm:grid-cols-2" : cols === 3 ? "sm:grid-cols-3" : "sm:grid-cols-1",
      className
    )}>
      {children}
    </div>
  )
}

/**
 * CompactField - Inline label:value for compact display
 * @param {icon} icon - Optional icon component
 * @param {string} autoIcon - i18n key for auto icon lookup (e.g. 'keyType', 'validFrom')
 * @param {boolean} copyable - Show copy button
 */
export function CompactField({ 
  label, 
  value, 
  icon: IconProp,
  autoIcon,
  mono,
  copyable,
  hint,
  className,
  children
}) {
  const { copy, isCopied } = useClipboard()
  const copied = isCopied()
  // children take precedence over value (rich content, e.g. value + action button)
  const content = children ?? value

  if (content === undefined || content === null || content === '') {
    return null // Don't render empty fields
  }
  
  // Resolve icon: explicit > autoIcon key lookup
  let Icon = IconProp
  if (!Icon && autoIcon) {
    Icon = FIELD_ICONS[autoIcon]
  }
  
  const handleCopy = () => {
    if (copyable && value) copy(String(value))
  }
  
  // If icon provided/detected, use layout with subtle icon
  if (Icon) {
    return (
      <div className={cn(
        "flex items-start gap-2 group p-1.5 -m-1.5 rounded-md transition-colors duration-150",
        "hover:bg-tertiary-op30",
        className
      )}>
        <Icon size={14} className="text-text-tertiary shrink-0 mt-0.5" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <div className="text-xs text-text-tertiary" title={hint}>{label}</div>
          <div className={cn("text-xs text-text-primary break-all", mono && "font-mono")}>
            {content}
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
        copyable && "cursor-pointer group",
        className
      )}
      onClick={copyable ? handleCopy : undefined}
    >
      <span className="text-text-tertiary" title={hint}>{label}:</span>
      <span className={cn("ml-1 text-xs text-text-primary", mono && "font-mono")}>
        {content}
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
      "rounded-[5px] px-3 py-2 border border-border",
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
  iconClass: _iconClass,
  title, 
  subtitle, 
  badge,
  className 
}) {
  return (
    <div className={cn("flex items-start gap-3 pb-3 border-b border-border", className)}>
      {Icon && (
        <Icon size={19} className="text-accent-primary shrink-0 mt-0.5" aria-hidden="true" />
      )}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <h3 className="ui-detail-title truncate">{title}</h3>
          {badge}
        </div>
        {subtitle && (
          <p className="text-xs text-text-tertiary truncate">{subtitle}</p>
        )}
      </div>
    </div>
  )
}
