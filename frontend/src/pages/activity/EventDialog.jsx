/**
 * Detail of a journal entry, as the mockup's eventDialog(): the entry's text, its properties,
 * Fermer and, when the entry names a certificate or an authority, the way to inspect it.
 * The product adds what the server records besides: action code, IP address (with its copy
 * button), client.
 */
import { useTranslation } from 'react-i18next'
import { useClipboard } from '../../hooks/useClipboard'
import { AtelierDialog } from '../../components/atelier/AtelierDialog'
import { Icon } from '../../components/atelier/Icon'
import { actionLabel } from './activityTypes'
import { fullTime } from './activityDates'

const INSPECTABLE = { certificate: 'certificate', ca: 'ca' }

export function EventDialog({ log, locale, resource, onClose, onInspect, canInspect }) {
  const { t } = useTranslation()
  const { copy, isCopied } = useClipboard()
  const target = INSPECTABLE[log.resource_type]
  const id = Number(log.resource_id)
  const inspect = target && Number.isInteger(id) && id > 0 && canInspect(target)
  return (
    <AtelierDialog title={actionLabel(log.action) || t('audit.event')} size="narrow" onClose={onClose} testId="audit-event-dialog">
      <div className="event-detail">
        {log.details && <p>{log.details}</p>}
        <dl className="props">
          <dt>{t('audit.colResource')}</dt><dd>{resource}</dd>
          <dt>{t('audit.colUser')}</dt><dd>{log.username || t('common.system')}</dd>
          <dt>{t('audit.dateTime')}</dt><dd>{fullTime(log.timestamp, locale)}</dd>
          <dt>{t('audit.colResult')}</dt><dd>{log.success
            ? <span className="badge good"><Icon name="check" />{t('audit.badgeOk')}</span>
            : <span className="badge bad"><Icon name="warning" />{t('audit.badgeFailed')}</span>}</dd>
          <dt>{t('audit.action')}</dt><dd className="mono">{log.action}</dd>
          {log.ip_address && <><dt>{t('audit.ipAddress')}</dt><dd><span className="mono">{log.ip_address}</span>{' '}
            <button type="button" className="icon-btn quiet" aria-label={isCopied() ? t('audit.ipCopied') : t('audit.copyIp')} title={t('audit.copyIp')}
              onClick={() => copy(log.ip_address)}><Icon name={isCopied() ? 'check' : 'copy'} /></button></dd></>}
          {log.user_agent && <><dt>{t('audit.client')}</dt><dd>{log.user_agent}</dd></>}
        </dl>
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
