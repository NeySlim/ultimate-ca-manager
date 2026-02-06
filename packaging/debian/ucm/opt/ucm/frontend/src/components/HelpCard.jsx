/**
 * HelpCard Component - Info/tip cards for contextual help
 * Inspired by UCM 1.8 info-box design
 */
import { Info, Lightbulb, Warning, Question, CheckCircle } from '@phosphor-icons/react'
import { cn } from '../lib/utils'

const variants = {
  info: {
    icon: Info,
    color: 'text-accent-primary',
    bg: 'bg-accent-primary/5',
    border: 'border-accent-primary/20',
  },
  tip: {
    icon: Lightbulb,
    color: 'status-warning-text',
    bg: 'status-warning-bg',
    border: 'status-warning-border',
  },
  warning: {
    icon: Warning,
    color: 'text-accent-danger',
    bg: 'bg-accent-danger/5',
    border: 'border-accent-danger/20',
  },
  help: {
    icon: Question,
    color: 'status-purple-text',
    bg: 'status-purple-bg',
    border: 'status-purple-border',
  },
  success: {
    icon: CheckCircle,
    color: 'text-accent-success',
    bg: 'bg-accent-success/5',
    border: 'border-accent-success/20',
  },
}

export function HelpCard({ 
  variant = 'info', 
  title, 
  children, 
  items = [],
  className,
  compact = false 
}) {
  const config = variants[variant]
  const Icon = config.icon

  return (
    <div className={cn(
      'rounded-lg border',
      config.bg,
      config.border,
      compact ? 'p-2' : 'p-3',
      className
    )}>
      <div className="flex gap-2">
        <div className={cn('flex-shrink-0 mt-0.5', config.color)}>
          <Icon size={compact ? 14 : 16} weight="fill" />
        </div>
        <div className="flex-1 min-w-0 text-xs">
          {title && (
            <p className={cn('font-semibold mb-1', config.color)}>
              {title}
            </p>
          )}
          {children && (
            <div className="text-text-secondary leading-relaxed">
              {children}
            </div>
          )}
          {items.length > 0 && (
            <ul className="text-text-secondary space-y-0.5 mt-1">
              {items.map((item, i) => (
                <li key={i} className="flex items-start gap-1.5">
                  <span className={cn('mt-1.5 w-1 h-1 rounded-full flex-shrink-0', config.color.replace('text-', 'bg-'))} />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
