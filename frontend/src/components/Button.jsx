import { cn } from '../lib/utils'

export function Button({ children, variant = 'primary', size = 'default', loading = false, className, ...props }) {
  const variants = {
    primary: 'text-white shadow-lg shadow-accent-primary/25 hover:shadow-xl hover:shadow-accent-primary/35',
    secondary: 'bg-gradient-to-r from-bg-tertiary to-bg-secondary hover:from-bg-secondary hover:to-border/80 text-text-primary border border-border/40 shadow-md shadow-black/10',
    danger: 'text-white shadow-lg shadow-red-500/25 hover:shadow-xl hover:shadow-red-500/35',
    ghost: 'hover:bg-bg-tertiary/80 text-text-primary hover:text-text-primary',
    outline: 'border border-border/60 bg-transparent text-text-primary hover:bg-bg-tertiary/60 hover:border-border shadow-sm',
  }
  
  const sizes = {
    sm: 'px-2 py-0.5 text-xs gap-1',
    default: 'px-3 py-1.5 text-sm gap-1.5',
    lg: 'px-4 py-2 text-sm gap-2',
  }
  
  const gradientStyle = variant === 'primary' 
    ? { background: 'var(--gradient-accent)' }
    : variant === 'danger'
    ? { background: 'linear-gradient(135deg, #EF4444 0%, #DC2626 100%)' }
    : {}
  
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center rounded-md font-medium',
        'transition-all duration-200 ease-out',
        'disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none',
        'focus:outline-none focus:ring-2 focus:ring-accent-primary/40 focus:ring-offset-1 focus:ring-offset-bg-primary',
        'hover:scale-[1.02] hover:-translate-y-px active:scale-[0.98] active:translate-y-0',
        variants[variant],
        sizes[size],
        loading && 'pointer-events-none opacity-70',
        className
      )}
      style={gradientStyle}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading ? (
        <>
          <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span>Loading...</span>
        </>
      ) : children}
    </button>
  )
}
