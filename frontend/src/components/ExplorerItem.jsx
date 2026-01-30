/**
 * ExplorerItem Component - Consistent list item for ExplorerPanel
 */
import { cn } from '../lib/utils'
import { useMobile } from '../contexts'

export function ExplorerItem({ 
  icon: Icon,
  title,
  subtitle,
  badge,
  active = false,
  onClick,
  className
}) {
  const { closeOnSelect } = useMobile()

  const handleClick = () => {
    onClick?.()
    closeOnSelect() // Auto-close bottom sheet on mobile
  }

  return (
    <button
      onClick={handleClick}
      className={cn(
        'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-all',
        active
          ? 'bg-accent-primary/15 text-accent-primary border border-accent-primary/30'
          : 'text-text-secondary hover:bg-bg-tertiary hover:text-text-primary border border-transparent',
        className
      )}
    >
      {Icon && (
        <Icon size={18} weight={active ? 'duotone' : 'regular'} className="flex-shrink-0" />
      )}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{title}</p>
        {subtitle && (
          <p className="text-xs text-text-tertiary truncate">{subtitle}</p>
        )}
      </div>
      {badge}
    </button>
  )
}

/**
 * ExplorerSection - Section header for grouped content
 */
export function ExplorerSection({ title, children, className }) {
  return (
    <div className={cn('space-y-2', className)}>
      <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wide px-1">
        {title}
      </h3>
      <div className="space-y-1">
        {children}
      </div>
    </div>
  )
}

/**
 * ExplorerStat - Stat card for explorer panel
 */
export function ExplorerStat({ icon: Icon, label, value, color = 'primary', className }) {
  const colors = {
    primary: 'from-accent-primary/10 to-accent-primary/5 border-accent-primary/20 text-accent-primary',
    success: 'from-green-500/10 to-green-500/5 border-green-500/20 text-green-500',
    warning: 'from-yellow-500/10 to-yellow-500/5 border-yellow-500/20 text-yellow-500',
    danger: 'from-red-500/10 to-red-500/5 border-red-500/20 text-red-500',
    info: 'from-blue-500/10 to-blue-500/5 border-blue-500/20 text-blue-500',
  }
  
  return (
    <div className={cn(
      'p-3 bg-gradient-to-br border rounded-lg',
      colors[color],
      className
    )}>
      <div className="flex items-center gap-2">
        {Icon && <Icon size={16} weight="duotone" />}
        <span className="text-xs text-text-secondary">{label}</span>
      </div>
      <p className="text-lg font-bold mt-1">{value}</p>
    </div>
  )
}

/**
 * ExplorerInfo - Key/value info row
 */
export function ExplorerInfo({ label, value, className }) {
  return (
    <div className={cn('flex items-center justify-between text-xs', className)}>
      <span className="text-text-secondary">{label}</span>
      <span className="text-text-primary font-medium">{value}</span>
    </div>
  )
}
