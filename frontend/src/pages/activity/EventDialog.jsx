/**
 * Detail of a journal entry, as the mockup's eventDialog(): the entry's text, its properties,
 * Fermer and, when the entry names a certificate or an authority, the way to inspect it.
 * The product adds what the server records besides: action code, IP address (copyable), client.
 */
import { useTranslation } from 'react-i18next'
import { AtelierDialog } from '../../components/atelier/AtelierDialog'
import { CodeValue, Facts } from '../../components/atelier/Detail'
import { actionLabel } from './activityTypes'
import { fullTime } from './activityDates'

const INSPECTABLE = { certificate: 'certificate', ca: 'ca' }

export function EventDialog({ log, locale, resource, onClose, onInspect, canInspect }) {
  const { t } = useTranslation()
  const target = INSPECTABLE[log.resource_type]
  const id = Number(log.resource_id)
  const inspect = target && Number.isInteger(id) && id > 0 && canInspect(target)
  return (
    <AtelierDialog title={actionLabel(log.action, t) || t('audit.event')} size="narrow" onClose={onClose} testId="audit-event-dialog">
      <div className="event-detail">
        {log.details && <p>{log.details}</p>}
        <Facts items={[
          [t('audit.colResource'), resource],
          [t('audit.colUser'), log.username || t('common.system')],
          [t('audit.dateTime'), fullTime(log.timestamp, locale)],
          { label: t('audit.colResult'), state: log.success ? ['good', t('audit.badgeOk'), 'check'] : ['bad', t('audit.badgeFailed'), 'warning'] },
          [t('audit.action'), <span className="mono">{log.action}</span>],
          log.ip_address && [t('audit.ipAddress'), <CodeValue value={log.ip_address} label={t('audit.ipAddress')} />],
          log.user_agent && { label: t('audit.client'), value: log.user_agent, long: true },
        ]} />
      </div>
      <div className="modal-actions">
        <button type="button" className="btn" data-action="close-modal" onClick={onClose}>{t('common.close')}</button>
        {inspect && (
          <button type="button" className="btn primary" onClick={() => onInspect(target, id)}>
            {t(target === 'ca' ? 'audit.viewAuthority' : 'audit.inspectCertificate')}
          </button>
        )}
      </div>
    </AtelierDialog>
  )
}

export default EventDialog
