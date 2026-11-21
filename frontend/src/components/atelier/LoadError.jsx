/**
 * The mockup's loadError(): a read that failed says what could not be read, its cause (status
 * and request when the server answered, the request alone when it did not, else the message),
 * Réessayer, and the journal link for who may read it. The other views stay usable.
 */
import { Trans, useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Icon } from './Icon'

/** The cause of a failed read, from { status, request, message }. */
export function LoadCause({ error, fallback }) {
  const { t } = useTranslation()
  const mono = { mono: <span className="mono" /> }
  if (error?.status && error.request) {
    return <Trans i18nKey="work.cause.status" components={mono}
      values={{ status: error.status, reason: t(`certificates.httpStatus${error.status}`, { defaultValue: '' }), request: error.request }} />
  }
  if (error?.request) return <Trans i18nKey="work.cause.noAnswer" components={mono} values={{ request: error.request }} />
  return t('work.cause.message', { message: error?.message || fallback || '' })
}

/** id: the zone (load-error-<id>, retry-<id>); journal: the audit path, given only to who may read it. */
export function LoadError({ id, title, cause, onRetry, journal }) {
  const { t } = useTranslation()
  return (
    <div className="load-error" id={id ? `load-error-${id}` : undefined} role="alert">
      <Icon name="warning" />
      <div>
        <h2>{title}</h2>
        {cause && <p>{cause}</p>}
        <div className="load-error-actions">
          {onRetry && (
            <button type="button" className="btn primary" id={id ? `retry-${id}` : undefined} data-retry-load={id} data-write="false" onClick={onRetry}>
              <Icon name="refresh" />{t('table.retry')}
            </button>
          )}
          {journal && <Link className="text-link" to={journal}>{t('work.viewLog')} <Icon name="right" /></Link>}
        </div>
      </div>
    </div>
  )
}

export default LoadError
