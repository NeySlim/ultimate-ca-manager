import { cn } from '../lib/utils'

export function Card({ 
  children, 
  className, 
  hover = true, 
  interactive = false, // clickable card with lift effect
  variant = 'default',  // default, elevated, bordered, soft
  accent,  // left border color: 'primary', 'success', 'warning', 'danger', 'info'
  ...props 
}) {
  const variants = {
    default: 'card-soft',
    elevated: cn(
      'bg-bg-secondary border border-border/40 rounded-xl',
      'elevation-2',
    ),
    bordered: cn(
      'bg-bg-secondary/50 border-2 border-border rounded-xl',
    ),
    soft: 'card-soft',
  }
  
  const accentColors = {
    primary: 'border-l-accent-primary',
    success: 'border-l-accent-success',
    warning: 'border-l-accent-warning',
    danger: 'border-l-accent-danger',
    info: 'border-l-accent-primary',
    purple: 'border-l-accent-purple',
  }
  
  return (
    <div
      className={cn(
        interactive ? 'card-interactive' : variants[variant],
        accent && `border-l-4 ${accentColors[accent]}`,
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
}

// Card sub-components for structured content
Card.Header = function CardHeader({ children, className, icon: Icon, title, subtitle, action }) {
  if (Icon || title) {
    return (
      <div className={cn('flex items-start justify-between gap-3 p-4 pb-3', className)}>
        <div className="flex items-center gap-3">
          {Icon && (
            <div className="w-10 h-10 rounded-xl status-primary-bg flex items-center justify-center shrink-0">
              <Icon size={20} className="text-accent-primary" weight="duotone" />
            </div>
          )}
          <div>
            {title && <h3 className="text-sm font-semibold text-text-primary">{title}</h3>}
            {subtitle && <p className="text-xs text-text-secondary mt-0.5">{subtitle}</p>}
          </div>
        </div>
        {action}
      </div>
    )
  }
  return <div className={cn('p-4 pb-3', className)}>{children}</div>
}

Card.Body = function CardBody({ children, className }) {
  return <div className={cn('px-4 pb-4', className)}>{children}</div>
}

Card.Footer = function CardFooter({ children, className }) {
  return (
    <div className={cn('px-4 py-3 border-t border-border/50 bg-bg-tertiary/30 rounded-b-xl', className)}>
      {children}
    </div>
  )
}
