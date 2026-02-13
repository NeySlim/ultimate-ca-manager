/**
 * UCM Logo Component - U Orbit
 * Stylized U letter with protective orbital arcs
 * Uses CSS variables for gradient colors
 */
import { useId } from 'react'
import { cn } from '../lib/utils'

const sizes = {
  xs: 20,
  sm: 26,
  md: 32,
  lg: 48,
  xl: 64,
}

function LogoIcon({ size = 32, className }) {
  const uid = useId()
  const g1 = `ucm-g1-${uid}`
  const g2 = `ucm-g2-${uid}`
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
        <linearGradient id={g1} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="var(--logo-gradient-start)" />
          <stop offset="50%" stopColor="var(--logo-gradient-mid)" />
          <stop offset="100%" stopColor="var(--logo-gradient-end)" />
        </linearGradient>
        <linearGradient id={g2} x1="100%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="var(--logo-gradient-accent)" />
          <stop offset="100%" stopColor="var(--logo-gradient-start)" />
        </linearGradient>
      </defs>
      {/* Left protective arc */}
      <path d="M5 34 A22 22 0 0 1 5 14" fill="none" stroke={`url(#${g2})`} strokeWidth="4" strokeLinecap="round" />
      {/* Right protective arc */}
      <path d="M43 14 A22 22 0 0 1 43 34" fill="none" stroke={`url(#${g1})`} strokeWidth="4" strokeLinecap="round" />
      {/* U letter */}
      <path d="M16 13v13a8 8 0 0 0 16 0V13" fill="none" stroke={`url(#${g1})`} strokeWidth="5.5" strokeLinecap="round" />
      {/* Accent dot */}
      <circle cx="39" cy="10" r="3.5" fill={`url(#${g2})`} />
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
