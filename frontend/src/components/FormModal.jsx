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
import { useRef } from 'react'
import { useTranslation } from 'react-i18next'
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
  submitLabel,
  cancelLabel,
  loading = false,
  disabled = false,
  variant = 'primary', // 'primary' | 'danger'
  
  // Content
  children,
  
  // Footer customization
  footer,
}) {
  const { t } = useTranslation()
  // Only four of the six call sites pass `loading`, so the submit button often
  // stays live while the request runs and a second Enter re-runs the action.
  // The ref guard is independent of that prop and costs no re-render.
  const inFlight = useRef(false)

  const handleSubmit = async (e) => {
    e?.preventDefault()
    if (inFlight.current) return
    inFlight.current = true

    // Collect form data from the form element
    const form = e?.target
    try {
      if (form && onSubmit) {
        const formData = new FormData(form)
        const data = Object.fromEntries(formData.entries())
        await onSubmit(data)
      } else {
        await onSubmit?.()
      }
    } finally {
      inFlight.current = false
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
        <div className="space-y-4">
          {children}
        </div>

        {footer ?? (
          <div className="ui-dialog-actions">
            <Button
              type="button"
              variant="secondary"
              onClick={handleClose}
              disabled={loading}
            >
              {cancelLabel ?? t('common.cancel')}
            </Button>
            <Button
              type="submit"
              variant={variant}
              disabled={loading || disabled}
            >
              {loading ? (
                <>
                  <LoadingSpinner size="sm" />
                  <span>{t('common.saving')}</span>
                </>
              ) : (
                submitLabel ?? t('common.save')
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
  title,
  message,
  confirmLabel,
  cancelLabel,
  variant = 'danger',
  loading = false,
}) {
  const { t } = useTranslation()
  return (
    <Modal open={open} onClose={onClose} title={title ?? t('common.confirm')} size="sm">
      <p className="ui-dialog-message">{message}</p>
      <div className="ui-dialog-actions">
        <Button type="button" variant="secondary" onClick={onClose} disabled={loading}>
          {cancelLabel ?? t('common.cancel')}
        </Button>
        <Button type="button" variant={variant} onClick={onConfirm} disabled={loading}>
          {loading ? <LoadingSpinner size="sm" /> : (confirmLabel ?? t('common.confirm'))}
        </Button>
      </div>
    </Modal>
  )
}
