/**
 * Modal Component - the Atelier dialog (`dialog` of the mockup), on the list template's
 * ListDialog: heading 18 px with its close button, body 22/24 px, actions under a rule.
 * Widths of the mockup: sm 520 (narrow), md 760, lg and xl 920 (wide).
 */
import { ListDialog } from './list/ListDialog'
import { cn } from '../lib/utils'

export function Modal({
  open,
  onClose,
  onOpenChange,
  title,
  subtitle,
  children,
  size = 'md',
  showClose = true,
  className,
}) {
  // Support both onClose and onOpenChange
  const handleOpenChange = onOpenChange || ((next) => { if (!next) onClose?.() })
  return (
    <ListDialog
      open={open}
      onOpenChange={handleOpenChange}
      title={title}
      subtitle={subtitle}
      narrow={size === 'sm'}
      closable={showClose}
      className={cn('ui-modal', (size === 'lg' || size === 'xl') && 'is-wide', className)}
    >
      {children}
    </ListDialog>
  )
}
