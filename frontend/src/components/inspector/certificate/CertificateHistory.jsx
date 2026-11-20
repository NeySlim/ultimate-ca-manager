/**
 * History of a certificate: the dates its record carries and, for a user who may
 * read the audit log, the entries whose resource is this certificate. The API
 * filters the log by resource type only, so the latest certificate entries are read.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CheckCircle, Prohibit, ArrowsClockwise, UploadSimple, Warning, ClockCounterClockwise } from '@phosphor-icons/react'
import { historyEntries } from '../../../lib/certificateDetail'
import { formatDate, cn } from '../../../lib/utils'
import { usePermission } from '../../../hooks'
import { auditService } from '../../../services'

export const AUDIT_WINDOW = 100
const ICONS = { issued: CheckCircle, imported: UploadSimple, renewed: ArrowsClockwise, revoked: Prohibit, audit: ClockCounterClockwise }
const humanize = (action) => String(action || '').replace(/[._]/g, ' ').replace(/^\w/, (c) => c.toUpperCase())

export function CertificateHistory({ cert }) {
  const { t } = useTranslation()
  const { hasPermission } = usePermission()
  const canAudit = hasPermission('read:audit')
  const [logs, setLogs] = useState([])
  const [state, setState] = useState(canAudit ? 'loading' : 'denied')

  useEffect(() => {
    if (!canAudit) return undefined
    let cancelled = false
    setState('loading')
    auditService.getLogs({ resource_type: 'certificate', per_page: AUDIT_WINDOW })
      .then((res) => { if (!cancelled) { setLogs(res?.data || []); setState('ready') } })
      .catch(() => { if (!cancelled) setState('failed') })
    return () => { cancelled = true }
  }, [canAudit, cert.id])

  const entries = historyEntries(cert, logs)
  const label = (e) => {
    if (e.kind === 'audit') return e.details || humanize(e.action)
    if (e.kind === 'revoked') {
      return t('inspector.history.revoked', { reason: e.reason ? t(`revocation.reasons.${e.reason}`, e.reason) : t('details.unspecified') })
    }
    return t(`inspector.history.${e.kind}`)
  }

  return (
    <div data-testid="certificate-history">
      {state === 'loading' && <p className="ins-muted" role="status">{t('common.loading')}</p>}
      <ul className="ins-history">
        {entries.map((e) => {
          const Icon = e.ok ? (ICONS[e.kind] || ClockCounterClockwise) : Warning
          return (
            <li key={e.id} className={cn(!e.ok && 'is-failed')}>
              <time dateTime={e.at}>{formatDate(e.at, { time: false })}</time>
              <Icon size={14} aria-hidden="true" />
              <span className="ins-what" title={e.action || undefined}>
                {label(e)}{!e.ok && <span className="sr-only"> ({t('inspector.history.failed')})</span>}
              </span>
              {e.actor && <span className="ins-actor">{e.actor}</span>}
            </li>
          )
        })}
      </ul>
      <p className="ins-note">
        {state === 'denied' ? t('inspector.history.noAudit')
          : state === 'failed' ? t('inspector.history.auditFailed')
            : t('inspector.history.scope', { count: AUDIT_WINDOW })}
      </p>
    </div>
  )
}
