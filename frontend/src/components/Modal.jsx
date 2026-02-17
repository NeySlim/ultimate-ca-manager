/**
 * Modal Component - Radix Dialog wrapper with enhanced visuals
 * Full-screen on mobile for better UX
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
    sm: 'sm:max-w-md',
    md: 'sm:max-w-2xl',
    lg: 'sm:max-w-4xl',
    xl: 'sm:max-w-6xl',
  }

  return (
    <Dialog.Root open={open} onOpenChange={handleOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-backdrop fixed inset-0 z-[200] data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <Dialog.Content 
          className={cn(
            // Mobile: full screen
            "fixed inset-0 z-[201]",
            "sm:inset-auto sm:left-1/2 sm:top-1/2 sm:-translate-x-1/2 sm:-translate-y-1/2",
            "w-full h-full sm:h-auto sm:mx-4",
            sizes[size],
            "bg-bg-primary sm:modal-enhanced sm:rounded-xl",
            "flex flex-col",
            // Animations (desktop only)
            "sm:data-[state=open]:animate-in sm:data-[state=closed]:animate-out",
            "sm:data-[state=closed]:fade-out-0 sm:data-[state=open]:fade-in-0",
            "sm:data-[state=closed]:zoom-out-95 sm:data-[state=open]:zoom-in-95",
            "sm:data-[state=closed]:slide-out-to-left-1/2 sm:data-[state=closed]:slide-out-to-top-[48%]",
            "sm:data-[state=open]:slide-in-from-left-1/2 sm:data-[state=open]:slide-in-from-top-[48%]"
          )}
          aria-describedby={undefined}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-border/50 shrink-0 modal-header-gradient">
            <Dialog.Title className="text-sm font-semibold text-text-primary">
              {title}
            </Dialog.Title>
            {showClose && (
              <Dialog.Close className="w-8 h-8 sm:w-7 sm:h-7 rounded-lg flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-all focus-ring">
                <X size={18} className="sm:hidden" />
                <X size={16} className="hidden sm:block" />
              </Dialog.Close>
            )}
          </div>

          {/* Content - scrollable */}
          <div className="flex-1 overflow-y-auto sm:max-h-[70vh]">
            {children}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
