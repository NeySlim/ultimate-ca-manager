import { cn } from '../lib/utils'

/**
 * Card - the mockup's panel: one bordered frame on the panel surface, radius 5, no gradient
 * or shadow (Aurore adds its gradient border). `interactive` frames hover; `accent` keeps a
 * 4 px left rule in the tone. `variant` and `hover` are accepted for compatibility.
 */
// eslint-disable-next-line no-unused-vars
export function Card({ children, className, hover, interactive = false, variant, accent, ...props }) {
  return (
    <div
      className={cn('ui-panel', interactive && 'is-interactive', accent && `is-accent-${accent}`, className)}
      {...props}
    >
      {children}
    </div>
  )
}

// Heading of the panel: title 14 px/600 in sentence case, its sentence 12 px under it, action on the right.
// eslint-disable-next-line no-unused-vars
Card.Header = function CardHeader({ children, className, icon: Icon, iconColor, title, subtitle, action }) {
  if (Icon || title) {
    return (
      <div className={cn('ui-panel-heading', className)}>
        <div>
          {Icon && <Icon aria-hidden="true" />}
          <div>
            {title && <h3>{title}</h3>}
            {subtitle && <p>{subtitle}</p>}
          </div>
        </div>
        {action}
      </div>
    )
  }
  return <div className={cn('ui-panel-heading', className)}>{children}</div>
}

Card.Body = function CardBody({ children, className }) {
  return <div className={cn('ui-panel-content', className)}>{children}</div>
}

Card.Footer = function CardFooter({ children, className }) {
  return <div className={cn('ui-panel-foot', className)}>{children}</div>
}
