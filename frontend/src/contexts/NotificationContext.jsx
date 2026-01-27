/**
 * Notification Context - Toast notifications
 */
import { createContext, useContext, useState } from 'react'
import * as Toast from '@radix-ui/react-toast'
import { CheckCircle, Warning, Info, XCircle, X } from '@phosphor-icons/react'

const NotificationContext = createContext()

export function NotificationProvider({ children }) {
  const [toasts, setToasts] = useState([])

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

  const getIcon = (type) => {
    switch (type) {
      case 'success': return <CheckCircle size={20} weight="fill" className="text-green-500" />
      case 'error': return <XCircle size={20} weight="fill" className="text-red-500" />
      case 'warning': return <Warning size={20} weight="fill" className="text-orange-500" />
      case 'info': return <Info size={20} weight="fill" className="text-blue-500" />
      default: return <Info size={20} weight="fill" />
    }
  }

  const getColors = (type) => {
    switch (type) {
      case 'success': return 'border-green-500/20 bg-green-500/10'
      case 'error': return 'border-red-500/20 bg-red-500/10'
      case 'warning': return 'border-orange-500/20 bg-orange-500/10'
      case 'info': return 'border-blue-500/20 bg-blue-500/10'
      default: return 'border-border bg-bg-secondary'
    }
  }

  const value = {
    showSuccess,
    showError,
    showWarning,
    showInfo,
  }

  return (
    <NotificationContext.Provider value={value}>
      <Toast.Provider swipeDirection="right">
        {children}
        
        {toasts.map(toast => (
          <Toast.Root
            key={toast.id}
            className={`fixed top-4 right-4 z-50 rounded-xl border p-4 shadow-2xl backdrop-blur-sm transition-all w-96 ${getColors(toast.type)}`}
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

        <Toast.Viewport className="fixed top-0 right-0 flex flex-col gap-2 p-4 w-96 max-w-full z-50" />
      </Toast.Provider>
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
