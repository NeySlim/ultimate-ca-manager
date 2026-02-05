import { cn } from '../lib/utils'

export function Badge({ 
  children, 
  variant = 'default', 
  size = 'default', 
  dot = false, 
  pulse = false,  // Animated dot
  icon: Icon,     // Optional icon
  className, 
  ...props 
}) {
  // Theme-aware variants using CSS classes defined in index.css
  const variants = {
    default: 'bg-bg-tertiary/80 text-text-primary border-transparent',
    primary: 'status-primary-bg status-primary-text border-transparent',
    secondary: 'bg-bg-tertiary/60 text-text-secondary border-transparent',
    success: 'status-success-bg status-success-text border-transparent',
    warning: 'status-warning-bg status-warning-text border-transparent',
    danger: 'status-danger-bg status-danger-text border-transparent',
    info: 'status-primary-bg status-primary-text border-transparent',
    outline: 'bg-transparent text-text-primary border-border hover:bg-bg-tertiary/50',
    // Named color variants (still theme-aware through CSS)
    emerald: 'status-success-bg status-success-text border-transparent',
    red: 'status-danger-bg status-danger-text border-transparent',
    blue: 'status-primary-bg status-primary-text border-transparent',
    yellow: 'status-warning-bg status-warning-text border-transparent',
    purple: 'bg-purple-500/15 text-purple-600 dark:text-purple-400 border-transparent',
    violet: 'bg-violet-500/15 text-violet-600 dark:text-violet-400 border-transparent',
    amber: 'status-warning-bg status-warning-text border-transparent',
    orange: 'bg-orange-500/15 text-orange-600 dark:text-orange-400 border-transparent',
    cyan: 'bg-cyan-500/15 text-cyan-600 dark:text-cyan-400 border-transparent',
    teal: 'bg-teal-500/15 text-teal-600 dark:text-teal-400 border-transparent',
    gray: 'bg-bg-tertiary/60 text-text-secondary border-transparent',
  }
  
  const dotColors = {
    default: 'bg-text-secondary',
    primary: 'status-primary-bg-solid',
    success: 'status-success-bg-solid',
    warning: 'status-warning-bg-solid',
    danger: 'status-danger-bg-solid',
    info: 'status-primary-bg-solid',
    violet: 'bg-violet-500',
    purple: 'bg-purple-500',
    cyan: 'bg-cyan-500',
    teal: 'bg-teal-500',
    orange: 'bg-orange-500',
    amber: 'bg-amber-500',
  }
  
  // Sizes: sm is pill-shaped, others are rounded
  const sizes = {
    sm: 'px-2 py-px text-[10px] gap-1 rounded-full',
    default: 'px-2.5 py-0.5 text-xs gap-1.5 rounded-md',
    lg: 'px-3 py-1 text-sm gap-2 rounded-md',
  }
  
  const iconSizes = {
    sm: 10,
    default: 12,
    lg: 14,
  }
  
  return (
    <span
      className={cn(
        'inline-flex items-center font-semibold border badge-enhanced',
        'transition-all duration-200 whitespace-nowrap',
        sizes[size],
        variants[variant],
        className
      )}
      {...props}
    >
      {dot && (
        <span className={cn(
          'w-1.5 h-1.5 rounded-full shrink-0',
          dotColors[variant] || dotColors.default,
          pulse && 'animate-pulse'
        )} />
      )}
      {Icon && <Icon size={iconSizes[size]} weight="bold" className="shrink-0" />}
      {children}
    </span>
  )
}

/**
 * CATypeIcon - Consistent icon for Root/Intermediate CA
 * Reusable across CAsPage tree view and CADetails panel
 */
import { Crown, ShieldCheck } from '@phosphor-icons/react'

export function CATypeIcon({ isRoot, size = 'md', className }) {
  const sizes = {
    sm: { container: 'w-5 h-5', icon: 14 },
    md: { container: 'w-7 h-7', icon: 16 },
    lg: { container: 'w-8 h-8', icon: 18 }
  }
  
  const { container, icon } = sizes[size] || sizes.md
  
  return (
    <div className={cn(
      container,
      'rounded-lg flex items-center justify-center shrink-0',
      isRoot 
        ? 'bg-gradient-to-br from-amber-500/20 to-orange-500/10 border border-amber-500/30'
        : 'bg-gradient-to-br from-blue-500/20 to-cyan-500/10 border border-blue-500/30',
      className
    )}>
      {isRoot ? (
        <Crown size={icon} weight="duotone" className="text-amber-500" />
      ) : (
        <ShieldCheck size={icon} weight="duotone" className="text-blue-500" />
      )}
    </div>
  )
}
