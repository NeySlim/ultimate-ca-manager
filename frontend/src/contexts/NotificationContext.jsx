/**
 * Notification Context - Toast notifications + Confirmation dialogs
 */
import { createContext, useContext, useState, useCallback } from 'react'
import * as Toast from '@radix-ui/react-toast'
import * as Dialog from '@radix-ui/react-dialog'
import { CheckCircle, Warning, Info, XCircle, X } from '@phosphor-icons/react'
import { Button } from '../components/Button'
import { Input } from '../components/Input'

const NotificationContext = createContext()

export function NotificationProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const [confirmDialog, setConfirmDialog] = useState(null)
  const [promptDialog, setPromptDialog] = useState(null)
  const [promptValue, setPromptValue] = useState('')

  const addToast = (type, message, duration = 5000) => {
    const id = Date.now()
    setToasts(prev => [...prev, { id, type, message, duration }])
    
    if (duration > 0) {
      setTimeout(() => removeToast(id), duration)
    }
  }

  const removeToast = (id) => {
    setToasts(prev => prev.filter(toast => toast.id !== id))
  }

  const showSuccess = (message) => addToast('success', message)
  const showError = (message) => addToast('error', message)
  const showWarning = (message) => addToast('warning', message)
  const showInfo = (message) => addToast('info', message)

  // Confirmation dialog
  const showConfirm = useCallback((message, options = {}) => {
    return new Promise((resolve) => {
      setConfirmDialog({
        message,
        title: options.title || 'Confirm',
        confirmText: options.confirmText || 'Confirm',
        cancelText: options.cancelText || 'Cancel',
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
        title: options.title || 'Input Required',
        placeholder: options.placeholder || '',
        type: options.type || 'text',
        confirmText: options.confirmText || 'OK',
        cancelText: options.cancelText || 'Cancel',
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

  const value = {
    showSuccess,
    showError,
    showWarning,
    showInfo,
    showConfirm,
    showPrompt,
  }

  return (
    <NotificationContext.Provider value={value}>
      <Toast.Provider swipeDirection="right">
        {children}
        
        {toasts.map(toast => (
          <Toast.Root
            key={toast.id}
            className={`rounded-xl border p-4 shadow-2xl backdrop-blur-sm transition-all ${getColors(toast.type)}`}
            open={true}
            onOpenChange={() => removeToast(toast.id)}
          >
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 mt-0.5">
                {getIcon(toast.type)}
              </div>
              <Toast.Description className="flex-1 text-sm text-text-primary">
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

        <Toast.Viewport className="fixed top-4 right-4 flex flex-col gap-3 w-96 max-w-[calc(100vw-2rem)] z-[300] outline-none" />
      </Toast.Provider>

      {/* Confirm Dialog */}
      <Dialog.Root open={!!confirmDialog} onOpenChange={(open) => !open && handleConfirm(false)}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[300]" />
          <Dialog.Content className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-[301] w-full max-w-sm bg-bg-secondary border border-border rounded-lg shadow-xl p-4">
            <Dialog.Title className="text-sm font-semibold text-text-primary mb-2">
              {confirmDialog?.title}
            </Dialog.Title>
            <Dialog.Description className="text-xs text-text-secondary mb-4 whitespace-pre-wrap">
              {confirmDialog?.message}
            </Dialog.Description>
            <div className="flex justify-end gap-2">
              {confirmDialog?.cancelText !== null && (
                <Button type="button" variant="secondary" size="sm" onClick={() => handleConfirm(false)}>
                  {confirmDialog?.cancelText || 'Cancel'}
                </Button>
              )}
              <Button 
                variant={confirmDialog?.variant === 'danger' ? 'danger' : 'primary'} 
                size="sm"
                onClick={() => handleConfirm(true)}
              >
                {confirmDialog?.confirmText}
              </Button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      {/* Prompt Dialog */}
      <Dialog.Root open={!!promptDialog} onOpenChange={(open) => !open && handlePrompt(false)}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[300]" />
          <Dialog.Content className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-[301] w-full max-w-sm bg-bg-secondary border border-border rounded-lg shadow-xl p-4">
            <Dialog.Title className="text-sm font-semibold text-text-primary mb-2">
              {promptDialog?.title}
            </Dialog.Title>
            <Dialog.Description className="text-xs text-text-secondary mb-3">
              {promptDialog?.message}
            </Dialog.Description>
            <Input
              type={promptDialog?.type || 'text'}
              value={promptValue}
              onChange={(e) => setPromptValue(e.target.value)}
              placeholder={promptDialog?.placeholder}
              autoFocus
              onKeyDown={(e) => e.key === 'Enter' && handlePrompt(true)}
            />
            <div className="flex justify-end gap-2 mt-4">
              <Button type="button" variant="secondary" size="sm" onClick={() => handlePrompt(false)}>
                {promptDialog?.cancelText}
              </Button>
              <Button type="button" size="sm" onClick={() => handlePrompt(true)}>
                {promptDialog?.confirmText}
              </Button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
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
