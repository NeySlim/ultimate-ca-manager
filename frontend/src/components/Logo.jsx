/**
 * UCM Logo Component - Certificate Chain
 * Based on design from docs/design/logo-chain-complete.html
 */
import { cn } from '../lib/utils'

export function Logo({ 
  variant = 'horizontal', // 'horizontal' | 'vertical' | 'compact' | 'icon'
  withText = true,
  size = 'md', // 'sm' | 'md' | 'lg' | 'xl'
  filled = false,
  className 
}) {
  // Gradient style for chain links (from reference design)
  const gradientStyle = {
    background: filled 
      ? 'linear-gradient(135deg, #5a8fc7, #7aa5d9)'
      : 'transparent',
    borderImage: filled 
      ? 'none' 
      : 'linear-gradient(135deg, #5a8fc7, #7aa5d9) 1',
    borderStyle: 'solid'
  }

  // Chain configuration based on variant (from reference design)
  const configs = {
    horizontal: {
      container: 'flex items-center',
      gap: size === 'sm' ? '2px' : '4px',
      linkWidth: size === 'sm' ? '12px' : size === 'lg' ? '24px' : '16px',
      linkHeight: size === 'sm' ? '18px' : size === 'lg' ? '36px' : '24px',
      borderWidth: size === 'sm' ? '2px' : size === 'lg' ? '4px' : '3px',
      borderRadius: '8px',
      transforms: [
        'translateY(0)',
        size === 'sm' ? 'translateY(6px)' : size === 'lg' ? 'translateY(12px)' : 'translateY(8px)',
        size === 'sm' ? 'translateY(-3px)' : size === 'lg' ? 'translateY(-6px)' : 'translateY(-4px)'
      ]
    },
    compact: {
      container: 'flex items-center',
      gap: '2px',
      linkWidth: '12px',
      linkHeight: '20px',
      borderWidth: '2px',
      borderRadius: '8px',
      transforms: ['translateY(0)', 'translateY(6px)', 'translateY(-3px)']
    },
    vertical: {
      container: 'flex flex-col items-center',
      gap: '4px',
      linkWidth: '24px',
      linkHeight: '16px',
      borderWidth: '3px',
      borderRadius: '8px',
      transforms: ['translateX(0)', 'translateX(8px)', 'translateX(-4px)']
    },
    icon: {
      container: 'flex items-center',
      gap: '4px',
      linkWidth: '16px',
      linkHeight: '24px',
      borderWidth: '3px',
      borderRadius: '8px',
      transforms: ['translateY(0)', 'translateY(8px)', 'translateY(-4px)']
    }
  }

  const config = configs[variant] || configs.horizontal

  const chainIcon = (
    <div className={config.container} style={{ gap: config.gap }}>
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          style={{
            width: config.linkWidth,
            height: config.linkHeight,
            borderWidth: filled ? '0' : config.borderWidth,
            borderRadius: config.borderRadius,
            transform: config.transforms[i],
            ...gradientStyle
          }}
        />
      ))}
    </div>
  )

  if (!withText || variant === 'icon') {
    return <div className={className}>{chainIcon}</div>
  }

  // Text gradient (matching chain gradient)
  const textGradientStyle = {
    background: 'linear-gradient(135deg, #5a8fc7, #7aa5d9)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    backgroundClip: 'text'
  }

  // With text - vertical variant (login page)
  if (variant === 'vertical') {
    return (
      <div className={cn('flex flex-col items-center', className)} style={{ gap: '12px' }}>
        {chainIcon}
        <div className="text-center">
          <div 
            className="font-black tracking-tight leading-none"
            style={{ fontSize: '32px', letterSpacing: '-1px', ...textGradientStyle }}
          >
            UCM
          </div>
          <div 
            className="font-semibold uppercase" 
            style={{ 
              fontSize: '9px', 
              letterSpacing: '2px', 
              color: '#888', 
              marginTop: '2px' 
            }}
          >
            Certificate Manager
          </div>
        </div>
      </div>
    )
  }

  // Horizontal with text (main logo)
  return (
    <div className={cn('flex items-center', className)} style={{ gap: '12px' }}>
      {chainIcon}
      <div className="flex flex-col">
        <div 
          className="font-black tracking-tight leading-none"
          style={{ 
            fontSize: variant === 'compact' ? '18px' : '32px',
            letterSpacing: '-1px',
            ...textGradientStyle 
          }}
        >
          UCM
        </div>
        {variant !== 'compact' && (
          <div 
            className="font-semibold uppercase" 
            style={{ 
              fontSize: '9px', 
              letterSpacing: '2px', 
              color: '#888',
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
