/**
 * Empty State Component
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
      <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-accent/10 to-purple-500/10 border border-accent/20 flex items-center justify-center mb-4 shadow-lg shadow-accent/5">
        <Icon size={36} className="text-accent" weight="duotone" />
      </div>
      <h3 className="text-lg font-semibold text-text-primary mb-1">{title}</h3>
      {description && (
        <p className="text-sm text-text-secondary mb-4 max-w-sm">{description}</p>
      )}
      {action && (
        <Button onClick={action.onClick} size="sm">
          {action.label}
        </Button>
      )}
    </div>
  )
}
