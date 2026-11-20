import { cn } from '../lib/utils'
import { Crown, ShieldCheck, Flask } from '@phosphor-icons/react'
import { useTranslation } from 'react-i18next'

// A badge is the mockup's `.badge` (and the list's state pill): 12 px text and icon in the
// tone's colour, nothing behind; Aurore gives it its pill. `outline` is the bordered `.chip`.
export const BADGE_VARIANTS = {
  default: '',
  primary: 'is-accent',
  secondary: 'is-muted',
  success: 'is-good',
  warning: 'is-warn',
  danger: 'is-bad',
  info: 'is-accent',
  outline: 'is-chip',
  emerald: 'is-good',
  green: 'is-good',
  red: 'is-bad',
  blue: 'is-accent',
  yellow: 'is-warn',
  purple: 'is-accent',
  violet: 'is-accent',
  amber: 'is-warn',
  orange: 'is-warn',
  cyan: 'is-accent',
  teal: 'is-accent',
  gray: 'is-muted',
}

// One size in the mockup: the keys stay so callers keep working
export const BADGE_SIZES = {
  sm: 'is-sm',
  default: 'is-md',
  lg: 'is-lg',
}

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
  return (
    <span
      className={cn('lv-pill ui-badge', BADGE_SIZES[size], BADGE_VARIANTS[variant], className)}
      {...props}
    >
      {dot && <span className={cn('ui-dot', pulse && 'animate-pulse')} aria-hidden="true" />}
      {Icon && <Icon weight="bold" aria-hidden="true" />}
      {children}
    </span>
  )
}

/**
 * CATypeIcon - Consistent icon for Root/Intermediate CA
 * Reusable across CAsPage tree view and CADetails panel
 * Uses global CSS classes for theme-aware colors
 */

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
      isRoot ? 'ca-icon-root' : 'ca-icon-intermediate',
      className
    )}>
      {isRoot ? (
        <Crown size={icon} weight="duotone" />
      ) : (
        <ShieldCheck size={icon} weight="duotone" />
      )}
    </div>
  )
}

/**
 * ExperimentalBadge - Inline badge for features not yet fully tested
 */
export function ExperimentalBadge({ className }) {
  const { t } = useTranslation()
  return (
    <Badge
      variant="amber"
      size="sm"
      icon={Flask}
      className={className}
      title={t('common.experimentalTooltip')}
    >
      {t('common.experimental')}
    </Badge>
  )
}
