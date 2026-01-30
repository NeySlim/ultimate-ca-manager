/**
 * Status Indicator Component
 * Dot indicator with optional label
 */
import { cn } from '../lib/utils'

export function StatusIndicator({ status, pulse = false, size = 'md', children }) {
  const statusColors = {
    valid: 'bg-green-500',
    success: 'bg-green-500',
    expiring: 'bg-orange-500',
    warning: 'bg-orange-500',
    expired: 'bg-red-500',
    danger: 'bg-red-500',
    error: 'bg-red-500',
    revoked: 'bg-gray-500',
    pending: 'bg-yellow-500',
    active: 'bg-green-500',
    inactive: 'bg-gray-500',
    disabled: 'bg-gray-500',
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
          statusColors[status] || 'bg-gray-500',
          sizes[size]
        )} />
        {pulse && (
          <div className={cn(
            "absolute inset-0 rounded-full animate-ping opacity-75",
            statusColors[status] || 'bg-gray-500'
          )} />
        )}
      </div>
      {children && (
        <span className="text-sm text-text-primary">{children}</span>
      )}
    </div>
  )
}
