/**
 * Cause of a queue read that failed, in the mockup's words: the status and the request
 * when the server answered, the request alone when it did not, else the message.
 */
import { Trans } from 'react-i18next'

export function loadCause(err, t) {
  if (!err) return ''
  const mono = { mono: <span className="font-mono" /> }
  if (err.status && err.request) {
    return (
      <Trans i18nKey="work.cause.status" components={mono}
        values={{ status: err.status, reason: t(`certificates.httpStatus${err.status}`, { defaultValue: '' }), request: err.request }} />
    )
  }
  if (err.request) return <Trans i18nKey="work.cause.noAnswer" components={mono} values={{ request: err.request }} />
  return err.message ? t('work.cause.message', { message: err.message }) : ''
}
