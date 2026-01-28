import { cn } from '../lib/utils'

export function Badge({ children, variant = 'default', size = 'default', className, ...props }) {
  const variants = {
    default: 'bg-bg-tertiary text-text-primary border-border',
    primary: 'bg-accent-primary/20 text-accent-primary border-accent-primary/30',
    secondary: 'bg-bg-tertiary text-text-secondary border-border',
    success: 'bg-green-500/15 text-green-400 border-green-500/25',
    warning: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/25',
    danger: 'bg-red-500/15 text-red-400 border-red-500/25',
    info: 'bg-blue-500/15 text-blue-400 border-blue-500/25',
    // Color variants for flexible usage
    emerald: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/25',
    red: 'bg-red-500/15 text-red-400 border-red-500/25',
    blue: 'bg-blue-500/15 text-blue-400 border-blue-500/25',
    yellow: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/25',
    purple: 'bg-purple-500/15 text-purple-400 border-purple-500/25',
    orange: 'bg-orange-500/15 text-orange-400 border-orange-500/25',
    cyan: 'bg-cyan-500/15 text-cyan-400 border-cyan-500/25',
    gray: 'bg-gray-500/15 text-gray-400 border-gray-500/25',
  }
  
  const sizes = {
    sm: 'px-1.5 py-0 text-[10px]',
    default: 'px-2 py-0.5 text-xs',
    lg: 'px-2.5 py-1 text-sm',
  }
  
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded font-medium border',
        sizes[size],
        variants[variant],
        className
      )}
      {...props}
    >
      {children}
    </span>
  )
}
