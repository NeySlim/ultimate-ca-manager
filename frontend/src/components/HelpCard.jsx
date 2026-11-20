/**
 * HelpCard Component - Info/tip cards for contextual help
 * Inspired by UCM 1.8 info-box design
 */
import { Info, Lightbulb, Warning, Question, CheckCircle } from '@phosphor-icons/react'
import { cn } from '../lib/utils'

// The mockup's `.notice`: 12 px text on the raised surface, radius 4, no border; warnings in their tone
const variants = {
  info: { icon: Info, tone: '' },
  tip: { icon: Lightbulb, tone: '' },
  warning: { icon: Warning, tone: 'is-warn' },
  help: { icon: Question, tone: '' },
  success: { icon: CheckCircle, tone: 'is-good' },
}

export function HelpCard({ 
  variant = 'info', 
  title, 
  children, 
  items = [],
  className,
  // eslint-disable-next-line no-unused-vars
  compact = false 
}) {
  const config = variants[variant] || variants.info
  const Icon = config.icon

  return (
    <div className={cn('ui-notice', config.tone, className)}>
      <Icon aria-hidden="true" />
      <div className="ui-notice-body">
        {title && <strong>{title}</strong>}
        {title && (children || items.length > 0) && ' '}
        {children}
        {items.length > 0 && (
          <ul>
            {items.map((item, i) => <li key={i}>{item}</li>)}
          </ul>
        )}
      </div>
    </div>
  )
}
