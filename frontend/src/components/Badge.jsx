import { cn } from '../lib/utils'

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
  // Theme-aware variants using CSS classes defined in index.css
  const variants = {
    default: 'bg-bg-tertiary/80 text-text-primary border-border/50',
    primary: 'status-primary-bg status-primary-text status-primary-border',
    secondary: 'bg-bg-tertiary/60 text-text-secondary border-border/40',
    success: 'status-success-bg status-success-text status-success-border',
    warning: 'status-warning-bg status-warning-text status-warning-border',
    danger: 'status-danger-bg status-danger-text status-danger-border',
    info: 'status-primary-bg status-primary-text status-primary-border',
    outline: 'bg-transparent text-text-primary border-border hover:bg-bg-tertiary/50',
    // Named color variants (still theme-aware through CSS)
    emerald: 'status-success-bg status-success-text status-success-border',
    red: 'status-danger-bg status-danger-text status-danger-border',
    blue: 'status-primary-bg status-primary-text status-primary-border',
    yellow: 'status-warning-bg status-warning-text status-warning-border',
    purple: 'status-primary-bg status-primary-text status-primary-border',
    orange: 'status-warning-bg status-warning-text status-warning-border',
    cyan: 'status-primary-bg status-primary-text status-primary-border',
    gray: 'bg-bg-tertiary/60 text-text-secondary border-border/40',
  }
  
  const dotColors = {
    default: 'bg-text-secondary',
    primary: 'status-primary-bg-solid',
    success: 'status-success-bg-solid',
    warning: 'status-warning-bg-solid',
    danger: 'status-danger-bg-solid',
    info: 'status-primary-bg-solid',
  }
  
  const sizes = {
    sm: 'px-1.5 py-0.5 text-[10px] gap-1',
    default: 'px-2 py-0.5 text-xs gap-1.5',
    lg: 'px-3 py-1 text-sm gap-2',
  }
  
  const iconSizes = {
    sm: 10,
    default: 12,
    lg: 14,
  }
  
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-md font-medium border',
        'transition-all duration-200',
        sizes[size],
        variants[variant],
        className
      )}
      {...props}
    >
      {dot && (
        <span className={cn(
          'w-1.5 h-1.5 rounded-full shrink-0',
          dotColors[variant] || dotColors.default,
          pulse && 'animate-pulse'
        )} />
      )}
      {Icon && <Icon size={iconSizes[size]} weight="bold" className="shrink-0" />}
      {children}
    </span>
  )
}
