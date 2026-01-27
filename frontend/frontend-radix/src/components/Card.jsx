import { cn } from '../lib/utils'

export function Card({ children, className, ...props }) {
  return (
    <div
      className={cn(
        'bg-gradient-to-br from-bg-secondary to-bg-tertiary border border-border/50 rounded-sm p-3 shadow-md hover:shadow-lg transition-all duration-200 backdrop-blur-sm relative overflow-hidden',
        className
      )}
      style={{ background: 'var(--gradient-bg)' }}
      {...props}
    >
      <div className="absolute inset-0 opacity-10 pointer-events-none" style={{ background: 'var(--gradient-accent)' }}></div>
      <div className="relative z-10">
        {children}
      </div>
    </div>
  )
}
