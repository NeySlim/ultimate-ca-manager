import { cn } from '../lib/utils'

export function Badge({ children, variant = 'default', className, ...props }) {
  const variants = {
    default: 'bg-bg-tertiary text-text-primary border-border',
    success: 'bg-gradient-to-r from-green-500/20 to-emerald-500/10 text-green-400 border-green-500/30 shadow-lg shadow-green-500/20',
    warning: 'bg-gradient-to-r from-yellow-500/20 to-orange-500/10 text-yellow-400 border-yellow-500/30 shadow-lg shadow-yellow-500/20',
    danger: 'bg-gradient-to-r from-red-500/20 to-pink-500/10 text-red-400 border-red-500/30 shadow-lg shadow-red-500/20',
    info: 'bg-gradient-to-r from-blue-500/20 to-cyan-500/10 text-blue-400 border-blue-500/30 shadow-lg shadow-blue-500/20',
  }
  
  return (
    <span
      className={cn(
        'inline-flex items-center px-3 py-1.5 rounded-full text-xs font-bold uppercase tracking-wider border backdrop-blur-sm',
        variants[variant],
        className
      )}
      {...props}
    >
      {children}
    </span>
  )
}
