/**
 * Notification Context - Toast notifications + Confirmation dialogs
 */
import { createContext, useContext, useState, useCallback, useEffect, useMemo } from 'react'
import { Warning } from '@phosphor-icons/react'
import { Icon } from '../components/atelier/Icon'
import { Button } from '../components/Button'
import { Input } from '../components/Input'
import { ListDialog } from '../components/list/ListDialog'
import { useTranslation } from 'react-i18next'

const NotificationContext = createContext()
// A message that stays takes the mockup's failure toast; its icon and rule follow its type (extensions.css)
const TOAST_TONES = { success: ['check', 'good'], error: ['warning', 'bad'], warning: ['warning', 'warn'], info: ['bell', 'accent'] }

export function NotificationProvider({ children }) {
  const { t } = useTranslation()
  const [toasts, setToasts] = useState([])
  const [confirmDialog, setConfirmDialog] = useState(null)
  const [promptDialog, setPromptDialog] = useState(null)
  const [promptValue, setPromptValue] = useState('')

  const removeToast = useCallback((id) => {
    setToasts(prev => prev.filter(toast => toast.id !== id))
  }, [])

  // options: a duration in ms (0 keeps the toast until it is closed) or { duration, action: { label, onClick } };
  // a toast that carries an action stays until it is used or closed, as the mockup's failure toast
  const addToast = useCallback((type, message, options) => {
    const opts = options !== null && typeof options === 'object' ? options : { duration: options }
    const action = opts.action && opts.action.label && typeof opts.action.onClick === 'function' ? opts.action : null
    const duration = opts.duration ?? (action ? 0 : 5000)
    const id = Date.now() + Math.random() // unique even when called in a tight loop
    setToasts(prev => [...prev, { id, type, message, duration, action }])

    if (duration > 0) {
      setTimeout(() => removeToast(id), duration)
    }
  }, [removeToast])

  const showSuccess = useCallback((message, options) => addToast('success', message, options), [addToast])
  const showError = useCallback((message, options) => addToast('error', message, options), [addToast])
  const showWarning = useCallback((message, options) => addToast('warning', message, options), [addToast])
  const showInfo = useCallback((message, options) => addToast('info', message, options), [addToast])

  // Confirmation dialog
  const showConfirm = useCallback((message, options = {}) => {
    return new Promise((resolve) => {
      setConfirmDialog({
        message,
        title: options.title,
        confirmText: options.confirmText,
        // An explicit `null` hides Cancel (acknowledge-only dialog); any other
        // empty value shows the translated default at render time.
        cancelText: options.cancelText,
        variant: options.variant || 'primary', // 'primary' | 'danger'
        resolve
      })
    })
  }, [])

  const handleConfirm = (result) => {
    if (confirmDialog) {
      confirmDialog.resolve(result)
      setConfirmDialog(null)
    }
  }

  // Prompt dialog
  const showPrompt = useCallback((message, options = {}) => {
    return new Promise((resolve) => {
      setPromptValue(options.defaultValue || '')
      setPromptDialog({
        message,
        title: options.title,
        placeholder: options.placeholder || '',
        type: options.type || 'text',
        confirmText: options.confirmText,
        cancelText: options.cancelText,
        resolve
      })
    })
  }, [])

  const handlePrompt = (result) => {
    if (promptDialog) {
      promptDialog.resolve(result ? promptValue : null)
      setPromptDialog(null)
      setPromptValue('')
    }
  }

  const value = useMemo(() => ({
    showSuccess,
    showError,
    showWarning,
    showInfo,
    showConfirm,
    showPrompt,
  }), [showSuccess, showError, showWarning, showInfo, showConfirm, showPrompt])

  return (
    <NotificationContext.Provider value={value}>
      {children}
      <ToastLine toast={toasts[toasts.length - 1]} onClose={removeToast} closeLabel={t('common.closeMessage')} />

      {/* Confirmation and prompt: the narrow Atelier dialog, its buttons in the interface language */}
      <ListDialog
        open={!!confirmDialog}
        onOpenChange={(open) => !open && handleConfirm(false)}
        title={confirmDialog?.title || t('common.confirm')}
        className="ui-modal"
        testId="confirm-dialog"
      >
        {/* A destructive action is announced in the mockup's warning notice; the safe action takes the focus */}
        {confirmDialog?.variant === 'danger' ? (
          <div className="ui-notice is-warn ui-dialog-notice">
            <Warning aria-hidden="true" />
            <p className="ui-notice-body">{confirmDialog?.message}</p>
          </div>
        ) : (
          <p className="ui-dialog-message">{confirmDialog?.message}</p>
        )}
        <div className="ui-dialog-actions">
          {confirmDialog?.cancelText !== null && (
            <Button type="button" variant="secondary" onClick={() => handleConfirm(false)} data-autofocus>
              {confirmDialog?.cancelText || t('common.cancel')}
            </Button>
          )}
          <Button
            type="button"
            variant={confirmDialog?.variant === 'danger' ? 'danger' : 'primary'}
            onClick={() => handleConfirm(true)}
            data-autofocus={confirmDialog?.cancelText === null ? true : undefined}
          >
            {confirmDialog?.confirmText || t('common.confirm')}
          </Button>
        </div>
      </ListDialog>

      <ListDialog
        open={!!promptDialog}
        onOpenChange={(open) => !open && handlePrompt(false)}
        title={promptDialog?.title || t('common.inputRequired')}
        className="ui-modal"
        testId="prompt-dialog"
      >
        <form onSubmit={(e) => { e.preventDefault(); handlePrompt(true) }}>
          {promptDialog?.message && <p className="ui-dialog-message">{promptDialog.message}</p>}
          <Input
            type={promptDialog?.type || 'text'}
            value={promptValue}
            onChange={(e) => setPromptValue(e.target.value)}
            placeholder={promptDialog?.placeholder}
            aria-label={promptDialog?.message || promptDialog?.title}
            autoFocus
          />
          <div className="ui-dialog-actions">
            <Button type="button" variant="secondary" onClick={() => handlePrompt(false)}>
              {promptDialog?.cancelText || t('common.cancel')}
            </Button>
            <Button type="submit">
              {promptDialog?.confirmText || t('common.ok')}
            </Button>
          </div>
        </form>
      </ListDialog>
    </NotificationContext.Provider>
  )
}

/**
 * The mockup's toast(): one line at the bottom centre, a newer message in place of the one shown (an
 * older one still running comes back when it ends). A passing message is the inverted pill; one that
 * stays or carries an action is the framed failure line, its action and Fermer le message. The line
 * stays mounted, so each message is announced: an error assertively, the others politely.
 */
function ToastLine({ toast, onClose, closeLabel }) {
  // Escape outside a dialog or a menu closes the message shown; one typed in a dialog stays the dialog's
  useEffect(() => {
    if (!toast) return undefined
    const onKey = (e) => {
      if (e.key !== 'Escape' || e.defaultPrevented || e.target?.closest?.('dialog, [role="dialog"], [role="alertdialog"], [role="menu"]')) return
      onClose(toast.id)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toast, onClose])
  const held = !!toast && (toast.duration === 0 || !!toast.action)
  const [icon, tone] = TOAST_TONES[toast?.type] || TOAST_TONES.info
  const cls = toast ? `visible${held ? ` failure tone-${tone}` : ''}` : undefined
  return (
    <div className="atl atl-island">
      <div id="toast" role="status" aria-live={toast?.type === 'error' ? 'assertive' : 'polite'} className={cls}>
        {toast && !held && toast.message}
        {toast && held && (
          <>
            <span className="toast-msg"><Icon name={icon} /><span className="toast-text">{toast.message}</span></span>
            {toast.action && (
              <button type="button" className="btn" id="toast-retry" data-write="false"
                onClick={() => { toast.action.onClick(); onClose(toast.id) }}>
                <Icon name="refresh" />{toast.action.label}
              </button>
            )}
            <button type="button" className="icon-btn" id="toast-close" aria-label={closeLabel} onClick={() => onClose(toast.id)}>
              <Icon name="close" />
            </button>
          </>
        )}
      </div>
    </div>
  )
}

export function useNotification() {
  const context = useContext(NotificationContext)
  if (!context) {
    throw new Error('useNotification must be used within NotificationProvider')
  }
  return context
}
