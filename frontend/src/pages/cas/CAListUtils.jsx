/**
 * CAs Page — shared helpers and small reusable components
 */
import { Certificate, Clock } from '@phosphor-icons/react'
import { cn } from '../../lib/utils'
import { getAppTimezone } from '../../stores/timezoneStore'

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

export function formatExpiry(date, t) {
  if (!date) return null
  const d = new Date(date)
  const now = new Date()
  const diffDays = Math.ceil((d - now) / (1000 * 60 * 60 * 24))
  if (diffDays < 0) return { text: t('common.expired'), variant: 'danger' }
  if (diffDays < 30) return { text: t('cas.daysLeft', { count: diffDays }), variant: 'warning' }
  if (diffDays < 365) return { text: `${Math.floor(diffDays / 30)}mo`, variant: 'default' }
  return { text: d.toLocaleDateString('en-US', { month: 'short', year: '2-digit', timeZone: getAppTimezone() }), variant: 'default' }
}

export function getStatusBadgeClass(status) {
  return status === 'Active' ? 'status-badge-success' : status === 'Expired' ? 'status-badge-danger' : 'status-badge-warning'
}

export function getStatusDotClass(status) {
  return status === 'Active' ? 'bg-status-success' : status === 'Expired' ? 'bg-status-danger' : 'bg-status-warning'
}

// =============================================================================
// SHARED SMALL COMPONENTS
// =============================================================================

/** Reusable CA info row — used by all 3 views */
export function CAInfoLine({ ca, isMobile, t }) {
  const expiry = formatExpiry(ca.valid_to || ca.not_after, t)
  return (
    <div className="flex items-center gap-2 text-2xs text-text-tertiary flex-wrap">
      {ca.subject && (
        <span className="truncate max-w-[200px]">{ca.subject.split(',')[0]}</span>
      )}
      <span className="flex items-center gap-1">
        <Certificate size={11} weight="duotone" className="text-accent-primary" />
        <span className="font-semibold text-text-secondary">
          {t('cas.certificateCount', { count: ca.certs || 0 })}
        </span>
      </span>
      {expiry && (
        <>
          <span className="text-border">·</span>
          <span className={cn(
            'font-medium flex items-center gap-1',
            expiry.variant === 'danger' ? 'text-status-danger' :
            expiry.variant === 'warning' ? 'text-status-warning' : 'text-text-secondary'
          )}>
            <Clock size={11} weight="duotone" />
            {expiry.text}
          </span>
        </>
      )}
    </div>
  )
}

/** Status pill badge */
export function StatusBadge({ status }) {
  return (
    <span className={cn(
      'shrink-0 px-2 py-0.5 rounded-full text-2xs font-medium flex items-center gap-1',
      getStatusBadgeClass(status)
    )}>
      <span className={cn('w-1.5 h-1.5 rounded-full', getStatusDotClass(status))} />
      {status || '?'}
    </span>
  )
}

/** Type badge (Root / Intermediate) */
export function TypeBadge({ type, isMobile, t }) {
  return (
    <span className={cn(
      'shrink-0 px-1.5 py-0.5 rounded-md text-2xs font-semibold',
      type === 'root' ? 'badge-bg-amber' : 'badge-bg-blue'
    )}>
      {type === 'root' ? t('common.rootCA') : (isMobile ? 'Int.' : t('common.intermediateCA'))}
    </span>
  )
}

/** HSM badge — shown when CA's signing key is on an HSM */
export function HsmBadge({ ca, t }) {
  if (!ca?.uses_hsm) return null
  const tip = [ca.hsm_provider_name, ca.hsm_key_label].filter(Boolean).join(' / ')
  return (
    <span
      className="shrink-0 px-1.5 py-0.5 rounded-md text-2xs font-semibold badge-bg-violet"
      title={tip || t('cas.detail.hsmBacked')}
    >
      HSM
    </span>
  )
}
