/**
 * IconBadge - Theme-aware icon container
 * 
 * Provides consistent icon styling across all themes, automatically
 * adjusting colors to avoid "ton sur ton" (color-on-color) issues.
 * 
 * Usage:
 *   <IconBadge icon={Certificate} color="blue" />
 *   <IconBadge icon={User} color="violet" size="lg" />
 */
import { cn } from '../lib/utils'

/**
 * Size scale for IconBadge
 * - table: Dense table rows (28px container, 14px icon)
 * - xs: Extra small (24px container, 12px icon)
 * - sm: Small (32px container, 16px icon)
 * - md: Medium/Default (40px container, 20px icon)
 * - lg: Large (48px container, 24px icon)
 * - xl: Extra large (56px container, 28px icon)
 */
const sizes = {
  table: 'w-7 h-7',   // 28px - for dense table rows
  xs: 'w-6 h-6',      // 24px
  sm: 'w-8 h-8',      // 32px
  md: 'w-10 h-10',    // 40px
  lg: 'w-12 h-12',    // 48px
  xl: 'w-14 h-14',    // 56px
}

const iconSizes = {
  table: 14,  // Dense tables
  xs: 12,
  sm: 16,
  md: 20,
  lg: 24,
  xl: 28,
}

// Color mappings using CSS variables (theme-aware)
const colorStyles = {
  // Primary colors
  blue: 'icon-bg-blue icon-text-blue',
  violet: 'icon-bg-violet icon-text-violet',
  purple: 'icon-bg-violet icon-text-violet', // alias
  emerald: 'icon-bg-emerald icon-text-emerald',
  green: 'icon-bg-emerald icon-text-emerald', // alias
  teal: 'icon-bg-teal icon-text-teal',
  orange: 'icon-bg-orange icon-text-orange',
  amber: 'icon-bg-amber icon-text-amber',
  yellow: 'icon-bg-amber icon-text-amber', // alias
  
  // Semantic colors (use accent CSS vars)
  primary: 'bg-accent-primary/15 text-accent-primary',
  success: 'bg-accent-success/15 text-accent-success',
  warning: 'bg-accent-warning/15 text-accent-warning',
  danger: 'bg-accent-danger/15 text-accent-danger',
  
  // Neutral
  slate: 'bg-bg-tertiary text-text-secondary',
  neutral: 'bg-bg-tertiary text-text-secondary',
  muted: 'bg-bg-tertiary/50 text-text-tertiary',
}

export function IconBadge({
  icon: Icon,
  color = 'primary',
  size = 'md',
  className,
  iconClassName,
  rounded = 'xl', // 'full', 'xl', 'lg', 'md', 'sm', 'none'
  weight = 'duotone',
  ...props
}) {
  const roundedClasses = {
    full: 'rounded-full',
    xl: 'rounded-xl',
    lg: 'rounded-lg',
    md: 'rounded-md',
    sm: 'rounded-sm',
    none: 'rounded-none',
  }

  return (
    <div
      className={cn(
        sizes[size],
        roundedClasses[rounded],
        'flex items-center justify-center shrink-0 transition-all duration-200',
        colorStyles[color] || colorStyles.neutral,
        className
      )}
      {...props}
    >
      {Icon && (
        <Icon 
          size={iconSizes[size]} 
          weight={weight}
          className={cn('transition-colors', iconClassName)}
        />
      )}
    </div>
  )
}

// Avatar variant for user/entity display
export function IconAvatar({
  icon: Icon,
  color = 'violet',
  size = 'md',
  initials,
  className,
  ...props
}) {
  return (
    <div
      className={cn(
        sizes[size],
        'rounded-full flex items-center justify-center shrink-0 font-medium',
        colorStyles[color] || colorStyles.neutral,
        className
      )}
      {...props}
    >
      {Icon ? (
        <Icon size={iconSizes[size]} weight="duotone" />
      ) : initials ? (
        <span className={cn(
          size === 'xs' && 'text-2xs',
          size === 'sm' && 'text-xs',
          size === 'md' && 'text-sm',
          size === 'lg' && 'text-base',
          size === 'xl' && 'text-lg',
        )}>
          {initials}
        </span>
      ) : null}
    </div>
  )
}

export default IconBadge
