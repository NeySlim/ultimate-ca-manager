import { cn } from '../lib/utils'

export function Button({ children, variant = 'primary', size = 'default', className, ...props }) {
  const variants = {
    primary: 'text-white shadow-md hover:shadow-lg transition-all',
    secondary: 'bg-gradient-to-r from-bg-tertiary to-bg-secondary hover:from-bg-secondary hover:to-border text-text-primary border border-border/50',
    danger: 'text-white shadow-md shadow-red-500/20 hover:shadow-lg hover:shadow-red-500/30 transition-all',
    ghost: 'hover:bg-bg-tertiary text-text-primary',
  }
  
  const sizes = {
    sm: 'px-2 py-0.5 text-xs',
    default: 'px-2.5 py-1 text-sm',
    lg: 'px-3 py-1.5 text-sm',
  }
  
  const gradientStyle = variant === 'primary' 
    ? { background: 'var(--gradient-accent)' }
    : variant === 'danger'
    ? { background: 'linear-gradient(135deg, #EF4444 0%, #DC2626 100%)' }
    : {}
  
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center gap-1 rounded-sm font-medium',
        'transition-all duration-200',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        'focus:outline-none focus:ring-1 focus:ring-accent-primary focus:ring-offset-1 focus:ring-offset-bg-primary',
        'hover:scale-[1.01] active:scale-[0.99]',
        variants[variant],
        sizes[size],
        className
      )}
      style={gradientStyle}
      {...props}
    >
      {children}
    </button>
  )
}
