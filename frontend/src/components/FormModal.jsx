/**
 * FormModal - Reusable modal with form handling
 * 
 * Global component for Create/Edit actions in modals
 * Combines Modal + Form with proper styling
 * 
 * Usage:
 * <FormModal
 *   open={showModal}
 *   onClose={() => setShowModal(false)}
 *   title="Create User"
 *   onSubmit={handleSubmit}
 *   submitLabel="Create"
 *   loading={saving}
 * >
 *   <Input label="Name" ... />
 *   <Input label="Email" ... />
 * </FormModal>
 */
import { Modal } from './Modal'
import { Button } from './Button'
import { LoadingSpinner } from './LoadingSpinner'

export function FormModal({
  // Modal props
  open,
  onClose,
  onOpenChange,
  title,
  size = 'md',
  
  // Form props
  onSubmit,
  submitLabel = 'Save',
  cancelLabel = 'Cancel',
  loading = false,
  disabled = false,
  variant = 'primary', // 'primary' | 'danger'
  
  // Content
  children,
  
  // Footer customization
  footer,
}) {
  const handleSubmit = (e) => {
    e?.preventDefault()
    
    // Collect form data from the form element
    const form = e?.target
    if (form && onSubmit) {
      const formData = new FormData(form)
      const data = Object.fromEntries(formData.entries())
      onSubmit(data)
    } else {
      onSubmit?.()
    }
  }

  const handleClose = onClose || (onOpenChange ? () => onOpenChange(false) : undefined)

  return (
    <Modal
      open={open}
      onClose={handleClose}
      onOpenChange={onOpenChange}
      title={title}
      size={size}
    >
      <form onSubmit={handleSubmit}>
        <div className="p-4 space-y-4">
          {children}
        </div>

        {footer ?? (
          <div className="flex justify-end gap-2 p-4 border-t border-border">
            <Button
              type="button"
              variant="secondary"
              onClick={handleClose}
              disabled={loading}
            >
              {cancelLabel}
            </Button>
            <Button
              type="submit"
              variant={variant}
              disabled={loading || disabled}
            >
              {loading ? (
                <>
                  <LoadingSpinner size="sm" />
                  <span className="ml-2">Saving...</span>
                </>
              ) : (
                submitLabel
              )}
            </Button>
          </div>
        )}
      </form>
    </Modal>
  )
}

/**
 * ConfirmModal - Simplified modal for confirmations
 */
export function ConfirmModal({
  open,
  onClose,
  onConfirm,
  title = 'Confirm',
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'danger',
  loading = false,
}) {
  return (
    <Modal open={open} onClose={onClose} title={title} size="sm">
      <div className="p-4">
        <p className="text-sm text-text-secondary">{message}</p>
      </div>
      <div className="flex justify-end gap-2 p-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onClose} disabled={loading}>
          {cancelLabel}
        </Button>
        <Button type="button" variant={variant} onClick={onConfirm} disabled={loading}>
          {loading ? <LoadingSpinner size="sm" /> : confirmLabel}
        </Button>
      </div>
    </Modal>
  )
}
