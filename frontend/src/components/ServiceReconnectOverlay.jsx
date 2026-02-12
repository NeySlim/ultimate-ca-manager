/**
 * ServiceReconnectOverlay - Fullscreen overlay shown during service restart/update
 */
import { useTranslation } from 'react-i18next'
import { ArrowsClockwise, Check, Warning } from '@phosphor-icons/react'

export function ServiceReconnectOverlay({ status, attempt, onCancel }) {
  const { t } = useTranslation()

  const statusConfig = {
    waiting: {
      icon: <ArrowsClockwise size={40} className="text-accent-primary animate-spin" />,
      title: t('settings.reconnect.waiting', 'Service is restarting...'),
      subtitle: t('settings.reconnect.waitingSub', 'Please wait while the service restarts'),
    },
    connecting: {
      icon: <ArrowsClockwise size={40} className="text-accent-primary animate-spin" />,
      title: t('settings.reconnect.connecting', 'Reconnecting...'),
      subtitle: t('settings.reconnect.connectingSub', 'Waiting for service to come back online'),
    },
    reloading: {
      icon: <Check size={40} weight="bold" className="text-accent-success" />,
      title: t('settings.reconnect.reloading', 'Service is back!'),
      subtitle: t('settings.reconnect.reloadingSub', 'Reloading page...'),
    },
    timeout: {
      icon: <Warning size={40} className="text-accent-danger" />,
      title: t('settings.reconnect.timeout', 'Connection timeout'),
      subtitle: t('settings.reconnect.timeoutSub', 'Service may need more time. Try refreshing manually.'),
    },
  }

  const config = statusConfig[status] || statusConfig.waiting

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-bg-primary/90 backdrop-blur-sm">
      <div className="text-center space-y-4 p-8 max-w-sm">
        <div className="flex justify-center">{config.icon}</div>
        <h2 className="text-xl font-semibold text-text-primary">{config.title}</h2>
        <p className="text-sm text-text-secondary">{config.subtitle}</p>
        
        {status === 'connecting' && attempt > 0 && (
          <div className="space-y-3">
            <div className="w-48 mx-auto h-1 bg-bg-tertiary rounded-full overflow-hidden">
              <div
                className="h-full bg-accent-primary rounded-full transition-all duration-500"
                style={{ width: `${Math.min((attempt / 30) * 100, 100)}%` }}
              />
            </div>
            <p className="text-xs text-text-tertiary">
              {t('settings.reconnect.attempt', 'Attempt {{count}}', { count: attempt })}
            </p>
          </div>
        )}
        
        {status === 'timeout' && (
          <div className="flex justify-center gap-3 mt-4">
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 bg-accent-primary text-white rounded-lg text-sm hover:bg-accent-primary/90"
            >
              {t('settings.reconnect.refresh', 'Refresh Page')}
            </button>
            {onCancel && (
              <button
                onClick={onCancel}
                className="px-4 py-2 bg-bg-tertiary text-text-secondary rounded-lg text-sm hover:bg-bg-tertiary/80"
              >
                {t('common.cancel', 'Cancel')}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default ServiceReconnectOverlay
