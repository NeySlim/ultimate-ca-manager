/**
 * The Historique panel: the mockup's historyDetail(), newest first: the dates the certificate
 * carries and, for who may read the audit log, its entries; a note says where they come from.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../../../components/atelier'
import { historyEntries } from '../../../lib/certificateDetail'
import { formatDate } from '../../../lib/utils'
import { usePermission } from '../../../hooks'
import { auditService } from '../../../services'
import { AUDIT_WINDOW, auditWords } from './auditWords'

const humanize = (action) => String(action || '').replace(/[._]/g, ' ').replace(/^\w/, (c) => c.toUpperCase())

export function HistoryPanel({ cert }) {
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
    if (e.kind === 'audit') {
      const words = auditWords(e.action)
      return words ? t(`inspector.history.${words}`) : humanize(e.action)
    }
    if (e.kind === 'revoked') return t('inspector.history.revoked', { reason: e.reason ? t(`revocation.reasons.${e.reason}`, e.reason) : t('details.unspecified') })
    return t(`inspector.history.${e.kind}`)
  }
  return (
    <>
      <ul className="history-list" aria-busy={state === 'loading' || undefined} data-testid="certificate-history">
        {entries.map((e) => {
          const revoked = e.kind === 'revoked' || (e.kind === 'audit' && /revok/i.test(e.action))
          return (
            <li key={e.id}>
              <time dateTime={e.at}>{formatDate(e.at, { time: false })}</time>
              <Icon name={!e.ok ? 'warning' : revoked ? 'block' : 'check'} />
              <span title={[e.action, e.details].filter(Boolean).join(' · ') || undefined}>
                {label(e)}{!e.ok && <span className="sr-only"> ({t('inspector.history.failed')})</span>}
              </span>
              {e.actor && <span className="actor">{e.actor}</span>}
            </li>
          )
        })}
      </ul>
      <p className="small muted" style={{ marginTop: 15 }} role={state === 'loading' ? 'status' : undefined}>
        {state === 'loading' ? t('common.loading')
          : state === 'denied' ? t('inspector.history.noAudit')
            : state === 'failed' ? t('inspector.history.auditFailed')
              : t('inspector.history.scope', { count: AUDIT_WINDOW })}
      </p>
    </>
  )
}
