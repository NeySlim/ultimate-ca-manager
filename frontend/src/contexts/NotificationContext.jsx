/**
 * Notification Context - Toast notifications + Confirmation dialogs
 */
import { createContext, useContext, useState, useCallback, useMemo } from 'react'
import * as Toast from '@radix-ui/react-toast'
import { CheckCircle, Warning, Info, XCircle, X } from '@phosphor-icons/react'
import { Button } from '../components/Button'
import { Input } from '../components/Input'
import { ListDialog } from '../components/list/ListDialog'
import { useTranslation } from 'react-i18next'

const NotificationContext = createContext()

export function NotificationProvider({ children }) {
  const { t } = useTranslation()
  const [toasts, setToasts] = useState([])
  const [confirmDialog, setConfirmDialog] = useState(null)
  const [promptDialog, setPromptDialog] = useState(null)
  const [promptValue, setPromptValue] = useState('')

  const removeToast = useCallback((id) => {
    setToasts(prev => prev.filter(toast => toast.id !== id))
  }, [])

  const addToast = useCallback((type, message, duration = 5000) => {
    const id = Date.now() + Math.random() // unique even when called in a tight loop
    setToasts(prev => [...prev, { id, type, message, duration }])
    
    if (duration > 0) {
      setTimeout(() => removeToast(id), duration)
    }
  }, [removeToast])

  // duration 0: the toast stays until the user closes it
  const showSuccess = useCallback((message, duration) => addToast('success', message, duration), [addToast])
  const showError = useCallback((message, duration) => addToast('error', message, duration), [addToast])
  const showWarning = useCallback((message, duration) => addToast('warning', message, duration), [addToast])
  const showInfo = useCallback((message, duration) => addToast('info', message, duration), [addToast])

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

  const getIcon = (type) => {
    switch (type) {
      case 'success': return <CheckCircle size={20} weight="fill" className="status-success-text" />
      case 'error': return <XCircle size={20} weight="fill" className="status-danger-text" />
      case 'warning': return <Warning size={20} weight="fill" className="status-warning-text" />
      case 'info': return <Info size={20} weight="fill" className="status-primary-text" />
      default: return <Info size={20} weight="fill" />
    }
  }

  const getColors = (type) => {
    switch (type) {
      case 'success': return 'status-success-border status-success-bg border'
      case 'error': return 'status-danger-border status-danger-bg border'
      case 'warning': return 'status-warning-border status-warning-bg border'
      case 'info': return 'status-primary-border status-primary-bg border'
      default: return 'border-border bg-bg-secondary'
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
        
        {toasts.map(toast => (
          <Toast.Root
            key={toast.id}
            className={`rounded-xl border p-4 shadow-2xl backdrop-blur-sm transition-all ${getColors(toast.type)}`}
            open={true}
            duration={toast.duration > 0 ? toast.duration : Infinity}
            onOpenChange={() => removeToast(toast.id)}
          >
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 mt-0.5">
                {getIcon(toast.type)}
              </div>
              <Toast.Description className="flex-1 min-w-0 text-sm text-text-primary break-words whitespace-pre-line">
                {toast.message}
              </Toast.Description>
              <Toast.Close className="flex-shrink-0">
                <button className="text-text-secondary hover:text-text-primary transition-colors">
                  <X size={16} />
                </button>
              </Toast.Close>
            </div>
          </Toast.Root>
        ))}

        {/* Bottom centre, above the status bar: a toast never covers a page header's commands */}
        <Toast.Viewport className="fixed bottom-10 left-1/2 -translate-x-1/2 flex flex-col gap-3 w-96 max-w-[calc(100vw-2rem)] z-[300] outline-none" />
      </Toast.Provider>

      {/* Confirmation and prompt: the narrow Atelier dialog, its buttons in the interface language */}
      <ListDialog
        open={!!confirmDialog}
        onOpenChange={(open) => !open && handleConfirm(false)}
        title={confirmDialog?.title || t('common.confirm')}
        className="ui-modal"
        testId="confirm-dialog"
      >
        <p className="ui-dialog-message">{confirmDialog?.message}</p>
        <div className="ui-dialog-actions">
          {confirmDialog?.cancelText !== null && (
            <Button type="button" variant="secondary" onClick={() => handleConfirm(false)}>
              {confirmDialog?.cancelText || t('common.cancel')}
            </Button>
          )}
          <Button
            type="button"
            variant={confirmDialog?.variant === 'danger' ? 'danger' : 'primary'}
            onClick={() => handleConfirm(true)}
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
