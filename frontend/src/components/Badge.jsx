import { cn } from '../lib/utils'

export function Badge({ children, variant = 'default', className, ...props }) {
  const variants = {
    default: 'bg-bg-tertiary text-text-primary border-border',
    primary: 'bg-accent-primary/20 text-accent-primary border-accent-primary/30',
    secondary: 'bg-bg-tertiary text-text-secondary border-border',
    success: 'bg-green-500/15 text-green-400 border-green-500/25',
    warning: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/25',
    danger: 'bg-red-500/15 text-red-400 border-red-500/25',
    info: 'bg-blue-500/15 text-blue-400 border-blue-500/25',
  }
  
  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border',
        variants[variant],
        className
      )}
      {...props}
    >
      {children}
    </span>
  )
}
