/**
 * The strip of figures above the cards (maquette-1): each figure with what situates it, a trend or
 * a split and a named gap, and the one tooltip on hover and focus. Its requests are shared with the
 * cards that read the same routes; a figure the API did not give is a dash and leads nowhere.
 */
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Bar, Icon, skWidth } from '../atelier'
import { dashboardService, overviewService } from '../../services'
import { queueSplit } from '../../lib/overviewQueue'
import { HEALTH_DAYS, ISSUANCE_DAYS, failuresPerDay, issuedPerDay, seriesStats } from '../../lib/overviewViz'
import { num, useCardData, useLang } from './shared'
import { MiniBars, SplitBar, Spark, useChartTip } from './viz'

const count = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null)
const FAIL_DAYS = 14
const PROTOCOLS = ['acme', 'scep', 'est']
const SERIES_COLOR = { acme: 'var(--s1)', scep: 'var(--s2)', est: 'var(--s3)' }

function dayLabel(date, lang) {
  const at = new Date(`${date}T00:00:00Z`)
  if (Number.isNaN(at.getTime())) return date
  try { return new Intl.DateTimeFormat(lang, { day: 'numeric', month: 'short', timeZone: 'UTC' }).format(at) } catch { return date }
}

/** A gap with its direction in an icon and its sign in words; `good` says which direction is good news. */
function Delta({ value, good = 'up' }) {
  if (value === null || value === undefined) return null
  const dir = value > 0 ? 'up' : value < 0 ? 'down' : null
  const tone = dir === null ? 'muted' : dir === good ? 'good' : 'bad'
  return (
    <span className={`delta ${tone}`} data-delta={value}>
      {dir && <Icon name={dir} />}{value > 0 ? `+ ${value}` : value < 0 ? `− ${-value}` : '0'}
    </span>
  )
}

/** to: a route; onClick: a place in the page (its href is that card); neither: a figure that leads nowhere. */
function Metric({ id, value, label, sub, tone, chart, to, href, onClick, loading, index, tip }) {
  if (loading) {
    return (
      <div className="metric stat sk-metric">
        <Bar width="46px" kind="figure" />
        <div><Bar width={skWidth(index, 50, 30)} /><Bar width={skWidth(index, 60, 30)} kind="thin" /></div>
      </div>
    )
  }
  const inner = (
    <>
      <span className="label">{label}</span>
      <span className={tone ? `value ${tone}` : 'value'}>{num(value)}</span>
      {chart ? <span className="metric-chart">{chart}</span> : <span className="metric-chart" />}
      {sub && <small>{sub}</small>}
    </>
  )
  const props = { className: 'metric stat', 'data-metric': id, ...(tip || {}) }
  if (to) return <Link to={to} {...props}>{inner}</Link>
  if (onClick) return <a href={href} {...props} onClick={(e) => { e.preventDefault(); onClick() }}>{inner}</a>
  // A figure that leads nowhere is still reachable, for its tooltip
  return <a {...props} tabIndex={tip ? 0 : undefined}>{inner}</a>
}

export function MetricStrip({ showQueue }) {
  const { t } = useTranslation()
  const lang = useLang()
  const tip = useChartTip()
  const statsState = useCardData(() => dashboardService.getStats(), ['certificate', 'ca'], 'stats')
  const queueState = useCardData(() => overviewService.getQueue(), ['certificate', 'ca', 'truststore'], 'queue')
  const healthState = useCardData(() => overviewService.getHealth(HEALTH_DAYS), ['certificate'], 'health')
  const issuanceState = useCardData(() => overviewService.getIssuance(ISSUANCE_DAYS), ['certificate', 'ca'], 'issuance')
  const stats = statsState.data || {}
  const first = (s) => s.status === 'loading' && !s.data

  // Certificates: the inventory, its issuances per day and how many are still usable
  const certificates = count(stats.total_certificates)
  const issued = issuedPerDay(issuanceState.data)
  const issuedStats = issued && seriesStats(issued.values)
  const active = count(stats.valid) !== null && count(stats.expiring_soon) !== null ? stats.valid + stats.expiring_soon : null
  const certSub = issuedStats ? (
    <><Delta value={issuedStats.sum} />{t('overview.metrics.issuedSub', { count: ISSUANCE_DAYS })}
      {active !== null && <>{' · '}{t('overview.metrics.active', { count: active })}</>}</>
  ) : t('overview.metrics.inventory')

  // To handle: critical rows, the rest to do, what is only to watch
  const queue = queueSplit(queueState.data)
  const items = Array.isArray(queueState.data?.items) ? queueState.data.items : []
  const critical = items.filter((i) => i.tier === 'critical').length
  const todo = queue.act === null ? null : Math.max(0, queue.act - critical)
  const queueParts = [
    { key: 'critical', value: critical, color: 'var(--bad)', label: t('overview.metrics.critical', { count: critical }) },
    { key: 'todo', value: todo || 0, color: 'var(--warn-fill)', label: t('overview.metrics.todo', { count: todo || 0 }) },
    { key: 'watch', value: queue.watch || 0, color: 'var(--s0)', label: t('overview.metrics.watch', { count: queue.watch || 0 }) },
  ]
  const queueSub = queue.total === null ? null : critical > 0 ? (
    <><span className="delta bad"><Icon name="warning" />{queueParts[0].label}</span>{` · ${queueParts[1].label} · ${queueParts[2].label}`}</>
  ) : t('overview.metrics.queueSub', { act: t('overview.metrics.interventions', { count: queue.act }), watch: queue.watch })

  // Expiring within the window: the stock already expired goes under it
  const expiring = count(stats.expiring_soon)
  const expired = count(stats.expired)

  // Failures today: the three protocols, 14 days in columns, the gap with yesterday
  const protocols = healthState.data?.protocols
  const failSeries = failuresPerDay(protocols, PROTOCOLS, FAIL_DAYS)
  const failStats = failSeries && seriesStats(failSeries)
  const failures = failStats ? failStats.today : null
  // The failures lead to the queue filtered on ACME (M:356), the card shown again if hidden
  const toFailures = failures === null || !showQueue ? null : () => showQueue('acme')
  const failTotals = PROTOCOLS.filter((p) => Array.isArray(protocols?.[p]?.periods)).map((p) => ({
    label: t(`overview.health.${p}`), color: SERIES_COLOR[p],
    value: protocols[p].periods.slice(-FAIL_DAYS).reduce((s, d) => s + (Number(d.failed) || 0), 0),
  }))

  const tips = {
    certificates: issuedStats && {
      title: t('overview.metrics.tip.issued', { count: ISSUANCE_DAYS }),
      rows: [
        { label: t('overview.health.today'), value: issuedStats.today },
        { label: t('overview.metrics.tip.mean'), value: issuedStats.mean.toLocaleString(lang) },
        { label: t('overview.metrics.tip.peak', { date: dayLabel(issued.dates[issuedStats.maxIndex], lang) }), value: issuedStats.max },
      ],
      hint: t('overview.metrics.tip.openInventory'),
    },
    queue: queue.total !== null && {
      title: t('overview.cards.queue'),
      rows: queueParts.map((p) => ({ label: t(`overview.metrics.part.${p.key}`), value: p.value, color: p.color })),
      hint: showQueue ? t('overview.metrics.tip.openQueue') : null,
    },
    expiring: expiring !== null && {
      title: t('overview.metrics.expiring'),
      rows: [{ label: t('overview.metrics.expiring'), value: expiring }, ...(expired === null ? [] : [{ label: t('overview.horizon.expired'), value: expired }])],
      hint: t('overview.metrics.tip.openList'),
    },
    failures: failStats && {
      title: t('overview.metrics.tip.failures', { count: failSeries.length }),
      rows: failTotals,
      hint: toFailures ? t('overview.metrics.tip.openFailures') : null,
    },
  }
  const bind = (id) => (tips[id] ? tip.bind(tips[id]) : null)

  return (
    <div className="metric-strip">
      <Metric id="certificates" index={0} loading={first(statsState)} value={certificates} label={t('overview.metrics.certificates')}
        chart={issued && <Spark values={issued.values} label={t('overview.metrics.issuedAlt', { count: issued.values.length, today: issuedStats.today })} />}
        sub={certSub} to={certificates === null ? null : '/certificates'} tip={bind('certificates')} />
      <Metric id="queue" index={1} loading={first(queueState)} value={queue.total} label={t('overview.cards.queue')}
        tone={queue.total > 0 ? 'warn' : ''}
        chart={queue.total > 0 && <SplitBar parts={queueParts} label={queueParts.map((p) => p.label).join(', ')} />}
        sub={queueSub} href="#card-queue" onClick={queue.total === null || !showQueue ? null : () => showQueue('')} tip={bind('queue')} />
      <Metric id="expiring" index={2} loading={first(statsState)} value={expiring} label={t('overview.metrics.expiring')}
        sub={expired === null ? t('overview.metrics.toCheck') : t('overview.metrics.alreadyExpired', { count: expired })}
        to={expiring === null ? null : '/certificates?status=expiring'} tip={bind('expiring')} />
      <Metric id="failures" index={3} loading={first(healthState)} value={failures} label={t('overview.metrics.failures')}
        tone={failures > 0 ? 'bad' : ''}
        chart={failSeries && <MiniBars values={failSeries} tone="var(--bad)" label={t('overview.metrics.failuresAlt', { count: failSeries.length, today: failures })} />}
        sub={failStats && failStats.delta !== null
          ? <><Delta value={failStats.delta} good="down" />{t('overview.metrics.sinceYesterday')}</>
          : t('overview.metrics.failuresSub')}
        href="#card-queue" onClick={toFailures} tip={bind('failures')} />
      {tip.node}
    </div>
  )
}
