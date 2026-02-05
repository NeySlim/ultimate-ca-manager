import { cn } from '../lib/utils'

/**
 * Button Component - Standardized sizes across the app
 * 
 * Size guidelines:
 * - sm: Content headers, inline actions, compact UI (default for most actions)
 * - default: Forms, modals, primary actions
 * - lg: Hero sections, prominent CTAs
 * 
 * Enhanced with visual effects:
 * - Layered shadows
 * - Gradient shine on hover
 * - Smooth micro-interactions
 */
export function Button({ children, variant = 'primary', size = 'default', loading = false, className, ...props }) {
  const variants = {
    primary: 'btn-gradient text-white',
    secondary: 'btn-soft text-text-primary',
    danger: 'btn-gradient danger text-white',
    'danger-soft': 'btn-danger-soft',
    'warning-soft': 'btn-warning-soft',
    success: 'btn-gradient success text-white',
    ghost: 'hover:bg-bg-tertiary/80 text-text-primary hover:text-text-primary transition-colors',
    outline: 'border border-border bg-transparent text-text-primary hover:bg-bg-tertiary/60 hover:border-border-strong transition-all',
  }
  
  // Standardized sizes - sm is the default for content actions
  const sizes = {
    xs: 'px-2 py-1 text-[11px] gap-1',      // Very compact (icon buttons)
    sm: 'px-2.5 py-1.5 text-xs gap-1.5',    // Content headers, inline actions
    default: 'px-3 py-2 text-sm gap-1.5',   // Forms, modals
    lg: 'px-4 py-2.5 text-sm gap-2',        // Prominent actions
  }
  
  // For non-gradient variants, add focus ring
  const needsFocusRing = !['primary', 'danger', 'success'].includes(variant)
  
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center rounded-lg font-medium',
        'disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none',
        needsFocusRing && 'focus-ring',
        variants[variant],
        sizes[size],
        loading && 'pointer-events-none opacity-70',
        className
      )}
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
