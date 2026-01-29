import { cn } from '../lib/utils'

export function Badge({ children, variant = 'default', size = 'default', dot = false, className, ...props }) {
  const variants = {
    default: 'bg-bg-tertiary/80 text-text-primary border-border/50 shadow-sm',
    primary: 'bg-accent-primary/15 text-accent-primary border-accent-primary/25 shadow-accent-primary/10',
    secondary: 'bg-bg-tertiary/60 text-text-secondary border-border/40',
    success: 'bg-green-500/12 text-green-400 border-green-500/20 shadow-green-500/10',
    warning: 'bg-yellow-500/12 text-yellow-400 border-yellow-500/20 shadow-yellow-500/10',
    danger: 'bg-red-500/12 text-red-400 border-red-500/20 shadow-red-500/10',
    info: 'bg-blue-500/12 text-blue-400 border-blue-500/20 shadow-blue-500/10',
    outline: 'bg-transparent text-text-primary border-border/60 hover:bg-bg-tertiary/50',
    // Color variants
    emerald: 'bg-emerald-500/12 text-emerald-400 border-emerald-500/20',
    red: 'bg-red-500/12 text-red-400 border-red-500/20',
    blue: 'bg-blue-500/12 text-blue-400 border-blue-500/20',
    yellow: 'bg-yellow-500/12 text-yellow-400 border-yellow-500/20',
    purple: 'bg-purple-500/12 text-purple-400 border-purple-500/20',
    orange: 'bg-orange-500/12 text-orange-400 border-orange-500/20',
    cyan: 'bg-cyan-500/12 text-cyan-400 border-cyan-500/20',
    gray: 'bg-gray-500/12 text-gray-400 border-gray-500/20',
  }
  
  const dotColors = {
    default: 'bg-text-secondary',
    primary: 'bg-accent-primary',
    success: 'bg-green-400',
    warning: 'bg-yellow-400',
    danger: 'bg-red-400',
    info: 'bg-blue-400',
  }
  
  const sizes = {
    sm: 'px-1.5 py-0 text-[10px]',
    default: 'px-2 py-0.5 text-xs',
    lg: 'px-2.5 py-1 text-sm',
  }
  
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md font-medium border shadow-sm',
        'transition-colors duration-150',
        sizes[size],
        variants[variant],
        className
      )}
      {...props}
    >
      {dot && (
        <span className={cn('w-1.5 h-1.5 rounded-full', dotColors[variant] || dotColors.default)} />
      )}
      {children}
    </span>
  )
}
