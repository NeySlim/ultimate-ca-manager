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
  table: 'w-6 h-6',   // 28px - for dense table rows
  xs: 'w-6 h-6',      // 24px
  sm: 'w-8 h-8',      // 32px
  md: 'w-10 h-10',    // 40px
  lg: 'w-12 h-12',    // 48px
  xl: 'w-14 h-14',    // 56px
}

// The mockup draws an icon bare, in its tone: no tile behind it (the box keeps its room)
const iconSizes = {
  table: 14,
  xs: 12,
  sm: 16,
  md: 17,
  lg: 20,
  xl: 24,
}

const colorStyles = {
  blue: 'is-accent',
  violet: 'is-accent',
  purple: 'is-accent',
  emerald: 'is-good',
  green: 'is-good',
  teal: 'is-accent',
  orange: 'is-warn',
  amber: 'is-warn',
  yellow: 'is-warn',
  primary: 'is-accent',
  success: 'is-good',
  warning: 'is-warn',
  danger: 'is-bad',
  slate: '',
  neutral: '',
  muted: '',
}

export function IconBadge({
  icon: Icon,
  color = 'primary',
  size = 'md',
  className,
  iconClassName,
  // eslint-disable-next-line no-unused-vars
  rounded,
  weight = 'regular',
  ...props
}) {
  return (
    <div
      className={cn('ui-icon', sizes[size], colorStyles[color] ?? '', className)}
      {...props}
    >
      {Icon && (
        <Icon
          size={iconSizes[size]}
          weight={weight}
          aria-hidden="true"
          className={iconClassName}
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
        'ui-icon rounded-full border border-border text-xs',
        colorStyles[color] ?? '',
        className
      )}
      {...props}
    >
      {Icon ? (
        <Icon size={iconSizes[size]} aria-hidden="true" />
      ) : initials ? (
        <span>{initials}</span>
      ) : null}
    </div>
  )
}

export default IconBadge
