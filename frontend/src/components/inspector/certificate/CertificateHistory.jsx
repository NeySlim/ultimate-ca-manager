/**
 * History of a certificate, newest first: what its record keeps (issued or imported,
 * renewed, revoked) and its entries of the audit log when the account may read it.
 * The audit route has no filter on one object: the latest certificate entries are read
 * and those of this certificate kept.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { CheckCircle, Prohibit, Warning } from '@phosphor-icons/react'
import { auditService } from '../../../services'
import { usePermission } from '../../../hooks'
import { cn, formatDate } from '../../../lib/utils'
import { recordEvents, mergeHistory, fromAudit } from './historyEvents'

const PAGE_SIZE = 100
const MAX_PAGES = 3

export function CertificateHistory({ certificate }) {
  const { t } = useTranslation()
  const { hasPermission } = usePermission()
  const canAudit = hasPermission('read:audit')
  const [audit, setAudit] = useState({ state: canAudit ? 'loading' : 'denied', entries: [], read: 0 })
  const id = certificate.id

  useEffect(() => {
    if (!canAudit) { setAudit({ state: 'denied', entries: [], read: 0 }); return undefined }
    let cancelled = false
    setAudit({ state: 'loading', entries: [], read: 0 })
    const load = async () => {
      const entries = []
      let read = 0
      for (let page = 1; page <= MAX_PAGES; page++) {
        const res = await auditService.getLogs({ resource_type: 'certificate', page, per_page: PAGE_SIZE })
        const rows = res?.data || []
        read += rows.length
        entries.push(...rows.filter((log) => String(log.resource_id) === String(id)).map(fromAudit))
        if (rows.length < PAGE_SIZE || page >= (res?.meta?.total_pages || 1)) break
      }
      return { entries, read }
    }
    load()
      .then((found) => { if (!cancelled) setAudit({ state: 'ready', ...found }) })
      .catch(() => { if (!cancelled) setAudit({ state: 'failed', entries: [], read: 0 }) })
    return () => { cancelled = true }
  }, [id, canAudit])

  const events = mergeHistory(recordEvents(certificate, t), audit.entries)

  return (
    <div aria-busy={audit.state === 'loading'}>
      {events.length > 0 ? (
        <ul className="insp-history" data-testid="cert-history">
          {events.map((e, i) => (
            <li key={i} className={cn(e.failed && 'is-bad')}>
              <time dateTime={new Date(e.at).toISOString()}>{formatDate(e.at, { time: true })}</time>
              {e.failed ? <Warning aria-hidden="true" /> : e.revoked ? <Prohibit aria-hidden="true" /> : <CheckCircle aria-hidden="true" />}
              <span className="insp-history-what">
                {e.label}
                {e.failed && <span className="insp-bad"> ({t('inspector.history.failed')})</span>}
                {e.detail && <span className="insp-muted"> · {e.detail}</span>}
              </span>
              {e.actor && <span className="insp-history-who">{e.actor}</span>}
            </li>
          ))}
        </ul>
      ) : audit.state !== 'loading' && <p className="insp-foot" style={{ marginTop: 0 }}>{t('inspector.history.empty')}</p>}
      <p className="insp-foot" role="status">
        {audit.state === 'loading' && t('inspector.history.loading')}
        {audit.state === 'denied' && t('inspector.history.noAudit')}
        {audit.state === 'failed' && t('inspector.history.loadFailed')}
        {audit.state === 'ready' && (
          <>
            {t('inspector.history.scope', { count: audit.read })}{' '}
            <Link className="insp-link" to="/audit">{t('inspector.history.openAudit')}</Link>
          </>
        )}
      </p>
    </div>
  )
}
