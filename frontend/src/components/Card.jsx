import { cn } from '../lib/utils'

export function Card({ children, className, hover = true, glow = false, ...props }) {
  return (
    <div
      className={cn(
        'bg-gradient-to-br from-bg-secondary to-bg-tertiary border border-border/50 rounded-lg p-3',
        'shadow-lg shadow-black/20',
        'backdrop-blur-sm relative overflow-hidden',
        'transition-all duration-300 ease-out',
        hover && 'hover:shadow-xl hover:shadow-black/30 hover:border-border/80 hover:-translate-y-0.5',
        glow && 'ring-1 ring-accent/20',
        className
      )}
      style={{ background: 'var(--gradient-bg)' }}
      {...props}
    >
      <div className="absolute inset-0 opacity-[0.03] pointer-events-none bg-gradient-to-br from-white to-transparent" />
      <div className="relative z-10">
        {children}
      </div>
    </div>
  )
}
