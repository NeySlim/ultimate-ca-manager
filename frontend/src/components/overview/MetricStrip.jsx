import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { dashboardService, overviewService } from '../../services'
import { queueSplit } from '../../lib/overviewQueue'
import { num, useCardData } from './shared'

const count = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null)

function Metric({ id, value, label, sub, tone, to, onClick }) {
  const inner = (
    <>
      <span className={`ov-metric-value${tone ? ` is-${tone}` : ''}`}>{num(value)}</span>
      <span className="ov-metric-text">
        <span className="ov-metric-label">{label}</span>
        {sub && <small className="ov-metric-sub">{sub}</small>}
      </span>
    </>
  )
  const props = { className: 'ov-metric', 'data-testid': `metric-${id}` }
  if (to) return <Link to={to} {...props}>{inner}</Link>
  if (onClick) return <button type="button" onClick={onClick} {...props}>{inner}</button>
  return <div {...props}>{inner}</div>
}

/**
 * Four figures above the cards. Its three requests are shared with the cards that read the
 * same routes; a figure the API did not give is a dash, and it then leads nowhere.
 */
export function MetricStrip({ go }) {
  const { t } = useTranslation()
  const stats = useCardData(() => dashboardService.getStats(), ['certificate', 'ca'], 'stats').data || {}
  const queue = queueSplit(useCardData(() => overviewService.getQueue(), ['certificate', 'ca', 'truststore'], 'queue').data)
  const protocols = useCardData(() => overviewService.getHealth(), ['certificate'], 'health').data?.protocols
  const series = ['acme', 'scep', 'est'].map((p) => protocols?.[p]?.periods).filter(Array.isArray)
  const failures = series.length > 0 ? series.reduce((sum, periods) => sum + (Number(periods.at(-1)?.failed) || 0), 0) : null
  const certificates = count(stats.total_certificates)
  const expired = count(stats.expired)
  const inventory = [
    count(stats.total_cas) !== null && t('overview.metrics.cas', { count: stats.total_cas }),
    count(stats.pending_csrs) > 0 && t('overview.metrics.pending', { count: stats.pending_csrs }),
    count(stats.ssh_certificates) > 0 && t('overview.metrics.ssh', { count: stats.ssh_certificates }),
  ].filter(Boolean).join(' · ')

  return (
    <div className="ov-metrics" role="group" aria-label={t('overview.metrics.label')}>
      <Metric id="certificates" value={certificates} label={t('common.certificates')} sub={inventory}
        to={certificates === null ? null : '/certificates'} />
      <Metric id="queue" value={queue.total} label={t('overview.cards.queue')} tone={queue.total > 0 ? 'warn' : ''}
        sub={queue.total === null ? null : t('overview.metrics.queueSub', { act: queue.act, watch: queue.watch })}
        onClick={queue.total === null ? null : go?.('queue')} />
      <Metric id="expired" value={expired} label={t('overview.horizon.expired')}
        sub={count(stats.expiring_soon) === null ? null : t('overview.metrics.expiringSoon', { count: stats.expiring_soon })}
        to={expired === null ? null : '/certificates?status=expired'} />
      <Metric id="failures" value={failures} label={t('overview.metrics.failures')} tone={failures > 0 ? 'bad' : ''}
        sub={t('overview.metrics.failuresSub')} onClick={failures === null ? null : go?.('health')} />
    </div>
  )
}
