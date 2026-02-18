/**
 * ServiceReconnectOverlay - Fullscreen overlay shown during service restart/update
 * 
 * Flow: countdown → connecting → redirecting → (or timeout)
 */
import { useTranslation } from 'react-i18next'
import { ArrowsClockwise, Check, Warning, Timer, SignOut } from '@phosphor-icons/react'

const COUNTDOWN_TOTAL = 60

export function ServiceReconnectOverlay({ status, attempt, countdown, onCancel }) {
  const { t } = useTranslation()

  const statusConfig = {
    countdown: {
      icon: <Timer size={40} weight="duotone" className="text-accent-primary" />,
      title: t('reconnect.countdown', 'Service is restarting...'),
      subtitle: t('reconnect.countdownSub', 'Reconnection will start in {{seconds}}s', { seconds: countdown }),
    },
    connecting: {
      icon: <ArrowsClockwise size={40} className="text-accent-primary animate-spin" />,
      title: t('reconnect.connecting', 'Reconnecting...'),
      subtitle: t('reconnect.connectingSub', 'Waiting for service to come back online'),
    },
    redirecting: {
      icon: <SignOut size={40} weight="duotone" className="text-accent-success" />,
      title: t('reconnect.redirecting', 'Service is back!'),
      subtitle: t('reconnect.redirectingSub', 'Redirecting to login page...'),
    },
    timeout: {
      icon: <Warning size={40} className="text-accent-danger" />,
      title: t('reconnect.timeout', 'Connection timeout'),
      subtitle: t('reconnect.timeoutSub', 'Service may need more time. Try refreshing manually.'),
    },
  }

  const config = statusConfig[status] || statusConfig.countdown

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-bg-primary/90 backdrop-blur-sm">
      <div className="text-center space-y-4 p-8 max-w-sm">
        <div className="flex justify-center">{config.icon}</div>
        <h2 className="text-xl font-semibold text-text-primary">{config.title}</h2>
        <p className="text-sm text-text-secondary">{config.subtitle}</p>
        
        {/* Countdown ring */}
        {status === 'countdown' && (
          <div className="flex justify-center mt-2">
            <div className="relative w-20 h-20">
              <svg className="w-20 h-20 -rotate-90" viewBox="0 0 80 80">
                <circle cx="40" cy="40" r="34" fill="none" stroke="currentColor" strokeWidth="3" className="text-bg-tertiary" />
                <circle
                  cx="40" cy="40" r="34" fill="none" stroke="currentColor" strokeWidth="3"
                  className="text-accent-primary transition-all duration-1000 ease-linear"
                  strokeDasharray={`${2 * Math.PI * 34}`}
                  strokeDashoffset={`${2 * Math.PI * 34 * (1 - countdown / COUNTDOWN_TOTAL)}`}
                  strokeLinecap="round"
                />
              </svg>
              <span className="absolute inset-0 flex items-center justify-center text-2xl font-bold text-text-primary">
                {countdown}
              </span>
            </div>
          </div>
        )}

        {/* Connection attempts progress */}
        {status === 'connecting' && attempt > 0 && (
          <div className="space-y-3">
            <div className="w-48 mx-auto h-1 bg-bg-tertiary rounded-full overflow-hidden">
              <div
                className="h-full bg-accent-primary rounded-full transition-all duration-500"
                style={{ width: `${Math.min((attempt / 30) * 100, 100)}%` }}
              />
            </div>
            <p className="text-xs text-text-tertiary">
              {t('reconnect.attempt', 'Attempt {{count}}', { count: attempt })}
            </p>
          </div>
        )}

        {/* Redirecting indicator */}
        {status === 'redirecting' && (
          <div className="flex justify-center mt-2">
            <Check size={24} weight="bold" className="text-accent-success animate-pulse" />
          </div>
        )}
        
        {/* Timeout actions */}
        {status === 'timeout' && (
          <div className="flex justify-center gap-3 mt-4">
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 bg-accent-primary text-white rounded-lg text-sm hover:bg-accent-primary/90"
            >
              {t('reconnect.refresh', 'Refresh Page')}
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
