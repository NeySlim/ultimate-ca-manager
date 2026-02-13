/**
 * UCM Logo Component - U Orbit
 * Stylized U letter with protective orbital arcs
 * Uses CSS variables for gradient colors
 */
import { cn } from '../lib/utils'

const sizes = {
  xs: 16,
  sm: 24,
  md: 32,
  lg: 48,
  xl: 64,
}

function LogoIcon({ size = 32, className }) {
  return (
    <svg
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      className={className}
    >
      <defs>
        <linearGradient id="ucm-g1" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="var(--logo-gradient-start)" />
          <stop offset="50%" stopColor="var(--logo-gradient-mid)" />
          <stop offset="100%" stopColor="var(--logo-gradient-end)" />
        </linearGradient>
        <linearGradient id="ucm-g2" x1="100%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="var(--logo-gradient-accent)" />
          <stop offset="100%" stopColor="var(--logo-gradient-start)" />
        </linearGradient>
      </defs>
      {/* Dashed orbit ring */}
      <ellipse cx="24" cy="24" rx="21" ry="21" fill="none" stroke="url(#ucm-g1)" strokeWidth="3" strokeDasharray="8 4" opacity="0.3" />
      {/* Left arc */}
      <path d="M6 32 A21 21 0 0 1 6 16" fill="none" stroke="url(#ucm-g2)" strokeWidth="3.5" strokeLinecap="round" />
      {/* Right arc */}
      <path d="M42 16 A21 21 0 0 1 42 32" fill="none" stroke="url(#ucm-g1)" strokeWidth="3.5" strokeLinecap="round" />
      {/* U letter */}
      <path d="M16 14v12a8 8 0 0 0 16 0V14" fill="none" stroke="url(#ucm-g1)" strokeWidth="4.5" strokeLinecap="round" />
      {/* Accent dot */}
      <circle cx="38" cy="12" r="3" fill="url(#ucm-g2)" />
    </svg>
  )
}

export function Logo({
  variant = 'horizontal', // 'horizontal' | 'vertical' | 'compact' | 'icon'
  withText = true,
  size = 'md', // 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  className
}) {
  const iconPx = sizes[size] || sizes.md

  if (!withText || variant === 'icon') {
    return (
      <div className={className}>
        <LogoIcon size={iconPx} />
      </div>
    )
  }

  // Vertical variant
  if (variant === 'vertical' || variant === 'stacked') {
    return (
      <div className={cn('flex flex-col items-center', className)} style={{ gap: '12px' }}>
        <LogoIcon size={iconPx} />
        <div className="text-center">
          <div
            className="font-black tracking-tight leading-none logo-text-gradient"
            style={{ fontSize: size === 'lg' ? '32px' : '24px', letterSpacing: '-1px' }}
          >
            UCM
          </div>
          <div
            className="font-semibold uppercase"
            style={{
              fontSize: '9px',
              letterSpacing: '2px',
              color: 'var(--text-tertiary)',
              marginTop: '2px'
            }}
          >
            Certificate Manager
          </div>
        </div>
      </div>
    )
  }

  // Horizontal / compact with text
  const fontSize = variant === 'compact' ? '18px' : size === 'lg' ? '32px' : '24px'
  return (
    <div className={cn('flex items-center', className)} style={{ gap: variant === 'compact' ? '8px' : '12px' }}>
      <LogoIcon size={iconPx} />
      <div className="flex flex-col">
        <div
          className="font-black tracking-tight leading-none logo-text-gradient"
          style={{ fontSize, letterSpacing: '-1px' }}
        >
          UCM
        </div>
        {variant !== 'compact' && (
          <div
            className="font-semibold uppercase"
            style={{
              fontSize: '9px',
              letterSpacing: '2px',
              color: 'var(--text-tertiary)',
              marginTop: '2px'
            }}
          >
            Certificate Manager
          </div>
        )}
      </div>
    </div>
  )
}
