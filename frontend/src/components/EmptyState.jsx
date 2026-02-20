/**
 * Empty State Component - Theme-aware with subtle visual polish
 */
import { FileX } from '@phosphor-icons/react'
import { Button } from './Button'

export function EmptyState({ 
  icon: Icon = FileX, 
  title = 'No data', 
  description, 
  action 
}) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      {/* Decorative background circle */}
      <div className="relative mb-4">
        <div className="absolute inset-0 w-20 h-20 rounded-full bg-accent-25 -translate-x-2 -translate-y-2" />
        <div className="relative w-16 h-16 rounded-2xl bg-bg-tertiary border border-border-op50 flex items-center justify-center">
          <Icon size={28} className="text-accent-primary" weight="duotone" />
        </div>
      </div>
      <h3 className="text-base font-medium text-text-primary mb-1">{title}</h3>
      {description && (
        <p className="text-sm text-text-tertiary mb-4 max-w-sm">{description}</p>
      )}
      {action && (
        <Button type="button" onClick={action.onClick} size="sm">
          {action.label}
        </Button>
      )}
    </div>
  )
}
