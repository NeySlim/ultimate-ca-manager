/**
 * The mockup's metric strip: four figures above the cards. Its three requests are shared with
 * the cards that read the same routes; a figure the API did not give is a dash and leads nowhere.
 */
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Bar, skWidth } from '../atelier'
import { dashboardService, overviewService } from '../../services'
import { queueSplit } from '../../lib/overviewQueue'
import { num, useCardData } from './shared'

const count = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null)

/** to: a route; onClick: a place in the page (its href is that card); neither: a figure that leads nowhere. */
function Metric({ id, value, label, sub, tone, to, href, onClick, loading, index }) {
  if (loading) {
    return (
      <div className="metric sk-metric">
        <Bar width="46px" kind="figure" />
        <div><Bar width={skWidth(index, 50, 30)} /><Bar width={skWidth(index, 60, 30)} kind="thin" /></div>
      </div>
    )
  }
  const inner = (
    <>
      <span className={tone ? `value ${tone}` : 'value'}>{num(value)}</span>
      <div><span className="label">{label}</span>{sub && <small>{sub}</small>}</div>
    </>
  )
  if (to) return <Link className="metric" to={to} data-metric={id}>{inner}</Link>
  if (onClick) {
    return <a className="metric" href={href} data-metric={id} onClick={(e) => { e.preventDefault(); onClick() }}>{inner}</a>
  }
  return <a className="metric" data-metric={id}>{inner}</a>
}

export function MetricStrip({ showQueue }) {
  const { t } = useTranslation()
  const statsState = useCardData(() => dashboardService.getStats(), ['certificate', 'ca'], 'stats')
  const queueState = useCardData(() => overviewService.getQueue(), ['certificate', 'ca', 'truststore'], 'queue')
  const healthState = useCardData(() => overviewService.getHealth(), ['certificate'], 'health')
  const stats = statsState.data || {}
  const queue = queueSplit(queueState.data)
  const protocols = healthState.data?.protocols
  const series = ['acme', 'scep', 'est'].map((p) => protocols?.[p]?.periods).filter(Array.isArray)
  const failures = series.length > 0 ? series.reduce((sum, periods) => sum + (Number(periods.at(-1)?.failed) || 0), 0) : null
  const certificates = count(stats.total_certificates)
  const expired = count(stats.expired)
  const first = (s) => s.status === 'loading' && !s.data
  // The mockup's failures lead to the queue filtered on ACME (M:356), the card shown again if hidden
  const toFailures = failures === null || !showQueue ? null : () => showQueue('acme')

  return (
    <div className="metric-strip">
      <Metric id="certificates" index={0} loading={first(statsState)} value={certificates} label={t('overview.metrics.certificates')}
        sub={t('overview.metrics.inventory')} to={certificates === null ? null : '/certificates'} />
      <Metric id="queue" index={1} loading={first(queueState)} value={queue.total} label={t('overview.cards.queue')}
        tone={queue.total > 0 ? 'warn' : ''}
        sub={queue.total === null ? null : t('overview.metrics.queueSub', {
          act: t('overview.metrics.interventions', { count: queue.act }), watch: queue.watch,
        })}
        href="#card-queue" onClick={queue.total === null || !showQueue ? null : () => showQueue('')} />
      <Metric id="expired" index={2} loading={first(statsState)} value={expired} label={t('overview.horizon.expired')}
        sub={t('overview.metrics.toCheck')} to={expired === null ? null : '/certificates?status=expired'} />
      <Metric id="failures" index={3} loading={first(healthState)} value={failures} label={t('overview.metrics.failures')}
        tone={failures > 0 ? 'bad' : ''} sub={t('overview.metrics.failuresSub')} href="#card-queue" onClick={toFailures} />
    </div>
  )
}
