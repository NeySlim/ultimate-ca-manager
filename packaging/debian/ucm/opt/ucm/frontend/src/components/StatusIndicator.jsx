/**
 * Status Indicator Component
 * Dot indicator with optional label - uses theme colors
 */
import { cn } from '../lib/utils'

export function StatusIndicator({ status, pulse = false, size = 'md', children }) {
  // Theme-aware status colors using CSS classes
  const statusColors = {
    valid: 'status-success-bg-solid',
    success: 'status-success-bg-solid',
    expiring: 'status-warning-bg-solid',
    warning: 'status-warning-bg-solid',
    expired: 'status-danger-bg-solid',
    danger: 'status-danger-bg-solid',
    error: 'status-danger-bg-solid',
    revoked: 'bg-text-tertiary',
    pending: 'status-warning-bg-solid',
    active: 'status-success-bg-solid',
    inactive: 'bg-text-tertiary',
    disabled: 'bg-text-tertiary',
    online: 'status-success-bg-solid',
    offline: 'bg-text-tertiary',
  }

  const sizes = {
    sm: 'w-2 h-2',
    md: 'w-2.5 h-2.5',
    lg: 'w-3 h-3',
  }

  return (
    <div className="inline-flex items-center gap-2">
      <div className="relative inline-flex">
        <div className={cn(
          "rounded-full",
          statusColors[status] || 'bg-text-tertiary',
          sizes[size]
        )} />
        {pulse && (
          <div className={cn(
            "absolute inset-0 rounded-full animate-ping opacity-75",
            statusColors[status] || 'bg-text-tertiary'
          )} />
        )}
      </div>
      {children && (
        <span className="text-sm text-text-primary">{children}</span>
      )}
    </div>
  )
}
