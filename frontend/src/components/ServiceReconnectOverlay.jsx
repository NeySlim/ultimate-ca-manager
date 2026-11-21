/**
 * The wait for a restarted or updated service, in the mockup's narrow modal(): the state as the title,
 * what happens next as the subtitle, the countdown or the attempts as its progress bar, then Refresh
 * and Cancel once the wait times out. Flow: countdown → connecting → redirecting (or timeout).
 * Closing it (Escape, the head's button) cancels the wait when the caller lets it be cancelled.
 */
import { useTranslation } from 'react-i18next'
import { AtelierDialog } from './atelier/AtelierDialog'
import { ModalActions } from './atelier/Form'

const COUNTDOWN_TOTAL = 60
const ATTEMPTS_SHOWN = 30

export function ServiceReconnectOverlay({ status, attempt, countdown, onCancel, note }) {
  const { t } = useTranslation()
  const states = {
    countdown: [t('reconnect.countdown', 'Service is restarting...'), t('reconnect.countdownSub', 'Reconnection will start in {{seconds}}s', { seconds: countdown })],
    connecting: [t('reconnect.connecting', 'Reconnecting...'), t('reconnect.connectingSub', 'Waiting for service to come back online')],
    redirecting: [t('reconnect.redirecting', 'Service is back!'), t('reconnect.redirectingSub', 'Redirecting to login page...')],
    timeout: [t('reconnect.timeout', 'Connection timeout'), t('reconnect.timeoutSub', 'Service may need more time. Try refreshing manually.')],
  }
  const [title, subtitle] = states[status] || states.countdown
  const share = status === 'countdown' ? (1 - countdown / COUNTDOWN_TOTAL) * 100
    : status === 'connecting' && attempt > 0 ? Math.min(attempt / ATTEMPTS_SHOWN, 1) * 100 : null

  return (
    <AtelierDialog title={title} subtitle={subtitle} size="narrow" onClose={() => onCancel?.()} testId="service-reconnect">
      <div role="status">
        {note && (status === 'countdown' || status === 'connecting') && <p className="small muted">{note}</p>}
        {share !== null && <div className="progress"><span style={{ width: `${Math.round(share)}%` }} /></div>}
        {status === 'connecting' && attempt > 0 && (
          <p className="small muted">{t('reconnect.attempt', 'Attempt {{count}}', { count: attempt })}</p>
        )}
      </div>
      {status === 'timeout' && (
        <ModalActions>
          {onCancel && <button type="button" className="btn" onClick={onCancel}>{t('common.cancel', 'Cancel')}</button>}
          <button type="button" className="btn primary" onClick={() => window.location.reload()}>{t('reconnect.refresh', 'Refresh Page')}</button>
        </ModalActions>
      )}
    </AtelierDialog>
  )
}

export default ServiceReconnectOverlay
