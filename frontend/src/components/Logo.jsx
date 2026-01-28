/**
 * UCM Logo Component - Certificate Chain
 * Based on design from docs/design/logo-chain-complete.html
 */
import { cn } from '../lib/utils'

export function Logo({ 
  variant = 'horizontal', // 'horizontal' | 'vertical' | 'compact' | 'icon'
  withText = true,
  size = 'md', // 'sm' | 'md' | 'lg'
  filled = false,
  className 
}) {
  // Chain styles based on variant
  const chainStyles = {
    horizontal: {
      container: 'flex items-center gap-1',
      link: 'w-4 h-6 border-[3px] rounded-lg',
      transforms: ['', 'translate-y-2', '-translate-y-1']
    },
    compact: {
      container: 'flex items-center gap-0.5',
      link: 'w-3 h-5 border-2 rounded-md',
      transforms: ['', 'translate-y-1.5', '-translate-y-0.5']
    },
    vertical: {
      container: 'flex flex-col items-center gap-1',
      link: 'w-6 h-4 border-[3px] rounded-lg',
      transforms: ['', 'translate-x-2', '-translate-x-1']
    },
    icon: {
      container: 'flex items-center gap-1',
      link: 'w-4 h-6 border-[3px] rounded-lg',
      transforms: ['', 'translate-y-2', '-translate-y-1']
    }
  }

  // Size adjustments
  const sizeClasses = {
    sm: variant === 'compact' ? 'scale-75' : 'scale-50',
    md: '',
    lg: variant === 'compact' ? 'scale-110' : 'scale-125',
    xl: 'scale-150'
  }

  const style = chainStyles[variant] || chainStyles.horizontal
  
  // Border or filled
  const linkClass = filled
    ? 'bg-gradient-to-br from-accent to-accent-secondary'
    : 'border-accent bg-transparent [border-image:linear-gradient(135deg,var(--color-accent),var(--color-accent-secondary))_1]'

  const chainIcon = (
    <div className={cn(style.container, sizeClasses[size])}>
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className={cn(
            style.link,
            linkClass,
            style.transforms[i]
          )}
        />
      ))}
    </div>
  )

  if (!withText || variant === 'icon') {
    return <div className={className}>{chainIcon}</div>
  }

  // With text variants
  if (variant === 'vertical') {
    return (
      <div className={cn('flex flex-col items-center gap-3', className)}>
        {chainIcon}
        <div className="text-center">
          <div className="text-3xl font-black tracking-tight bg-gradient-to-r from-accent to-accent-secondary bg-clip-text text-transparent">
            UCM
          </div>
          <div className="text-[9px] font-semibold tracking-widest uppercase text-text-tertiary mt-0.5">
            Certificate Manager
          </div>
        </div>
      </div>
    )
  }

  // Horizontal and compact with text
  return (
    <div className={cn('flex items-center gap-3', className)}>
      {chainIcon}
      <div className="flex flex-col">
        <div className={cn(
          'font-black tracking-tight bg-gradient-to-r from-accent to-accent-secondary bg-clip-text text-transparent leading-none',
          variant === 'compact' ? 'text-lg' : 'text-2xl'
        )}>
          UCM
        </div>
        {variant !== 'compact' && (
          <div className="text-[9px] font-semibold tracking-widest uppercase text-text-tertiary mt-0.5">
            Certificate Manager
          </div>
        )}
      </div>
    </div>
  )
}
