/**
 * Pro Badge Component
 * Displays Pro/Enterprise badge in sidebar
 * Uses theme variables for consistent styling
 */
import { Crown, Star } from '@phosphor-icons/react'
import { useLicense } from '../hooks/useLicense'

export function ProBadge({ compact = false }) {
  const { type, loading, expiresAt } = useLicense()

  if (loading || type === 'community') return null

  const isEnterprise = type === 'enterprise'
  const Icon = isEnterprise ? Crown : Star
  const label = isEnterprise ? 'Enterprise' : 'Pro'
  
  // Use theme variable accent-pro for consistent styling
  const bgClass = isEnterprise 
    ? 'stat-card-warning status-warning-border border' 
    : 'bg-accent-pro/20 border-accent-pro/30'
  const textClass = isEnterprise ? 'status-warning-text' : 'text-accent-pro'

  if (compact) {
    return (
      <div className={`flex items-center justify-center p-1.5 rounded-lg ${bgClass} border`}>
        <Icon size={16} weight="fill" className={textClass} />
      </div>
    )
  }

  return (
    <div className={`flex items-center gap-2 px-3 py-2 rounded-lg ${bgClass} border`}>
      <Icon size={16} weight="fill" className={textClass} />
      <div className="flex-1">
        <p className={`text-xs font-semibold ${textClass}`}>{label}</p>
        {expiresAt && (
          <p className="text-[10px] text-text-tertiary">
            Expires {new Date(expiresAt).toLocaleDateString()}
          </p>
        )}
      </div>
    </div>
  )
}

export function ProFeatureGate({ feature, children, fallback = null }) {
  const { hasFeature, isPro } = useLicense()
  
  if (!isPro && !hasFeature(feature)) {
    return fallback
  }
  
  return children
}
