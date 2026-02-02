/**
 * Modal Component - Radix Dialog wrapper with enhanced visuals
 */
import * as Dialog from '@radix-ui/react-dialog'
import { X } from '@phosphor-icons/react'
import { cn } from '../lib/utils'

export function Modal({ 
  open, 
  onClose, 
  onOpenChange,
  title, 
  children, 
  size = 'md',
  showClose = true 
}) {
  // Support both onClose and onOpenChange
  const handleOpenChange = onOpenChange || onClose;
  const sizes = {
    sm: 'max-w-md',
    md: 'max-w-2xl',
    lg: 'max-w-4xl',
    xl: 'max-w-6xl',
  }

  return (
    <Dialog.Root open={open} onOpenChange={handleOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-backdrop fixed inset-0 z-40 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <Dialog.Content 
          className={cn(
            "fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-50",
            "w-full mx-4",
            sizes[size],
            "modal-enhanced",
            "data-[state=open]:animate-in data-[state=closed]:animate-out",
            "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
            "data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95",
            "data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%]",
            "data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%]"
          )}
          aria-describedby={undefined}
        >
          <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
            <Dialog.Title className="text-sm font-semibold text-text-primary">
              {title}
            </Dialog.Title>
            {showClose && (
              <Dialog.Close className="w-7 h-7 rounded-lg flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-all focus-ring">
                <X size={16} />
              </Dialog.Close>
            )}
          </div>

          <div className="max-h-[70vh] overflow-y-auto">
            {children}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
