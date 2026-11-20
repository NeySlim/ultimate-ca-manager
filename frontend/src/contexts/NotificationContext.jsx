/**
 * Notification Context - Toast notifications + Confirmation dialogs
 */
import { createContext, useContext, useState, useCallback, useMemo } from 'react'
import * as Toast from '@radix-ui/react-toast'
import { CheckCircle, Warning, Info, X } from '@phosphor-icons/react'
import { Button } from '../components/Button'
import { Input } from '../components/Input'
import { ListDialog } from '../components/list/ListDialog'
import { yieldEscapeToDialog } from '../components/list/dialogEscape'
import { useTranslation } from 'react-i18next'

const NotificationContext = createContext()
const TOAST_ICONS = { success: CheckCircle, error: Warning, warning: Warning, info: Info }

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
      <Toast.Provider swipeDirection="down">
        {children}
        
        {/* The mockup's inverted pill; a toast that stays or carries an action is its failure toast:
            a framed line with the tone's rule and icon, the action, and a close button */}
        {toasts.map(toast => {
          const held = toast.duration === 0 || !!toast.action
          const Icon = TOAST_ICONS[toast.type] || Info
          return (
            <Toast.Root
              key={toast.id}
              className={`ui-toast${held ? ` is-held is-${toast.type}` : ''}`}
              type={toast.type === 'error' ? 'foreground' : 'background'}
              open={true}
              duration={toast.duration > 0 ? toast.duration : Infinity}
              onOpenChange={() => removeToast(toast.id)}
              onEscapeKeyDown={yieldEscapeToDialog}
            >
              {held && <Icon className="ui-toast-icon" aria-hidden="true" />}
              <Toast.Description className="ui-toast-text">{toast.message}</Toast.Description>
              {toast.action && (
                <Toast.Action asChild altText={toast.action.label}>
                  <button type="button" className="lv-btn" onClick={() => toast.action.onClick()}>{toast.action.label}</button>
                </Toast.Action>
              )}
              {held && (
                <Toast.Close asChild>
                  <button type="button" className="lv-btn is-icon" aria-label={t('common.closeMessage')}>
                    <X size={16} aria-hidden="true" />
                  </button>
                </Toast.Close>
              )}
            </Toast.Root>
          )
        })}

        {/* Bottom centre, 40 px above the window's edge: a toast never covers a page header's commands */}
        <Toast.Viewport className="ui-toast-viewport fixed bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-3 z-[300] outline-none" />
      </Toast.Provider>

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

export function useNotification() {
  const context = useContext(NotificationContext)
  if (!context) {
    throw new Error('useNotification must be used within NotificationProvider')
  }
  return context
}
