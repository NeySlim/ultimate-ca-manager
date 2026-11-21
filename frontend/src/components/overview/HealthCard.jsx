/**
 * The mockup's healthCard() over GET /dashboard/health: one row per protocol with its last
 * operation, today and the whole period in figures and its curve, then the services that only
 * report a state, and the summary under them.
 */
import { useContext } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Icon } from '../atelier'
import { overviewService } from '../../services'
import { usePermission } from '../../hooks/usePermission'
import { isVisible, moduleForPath } from '../../navigation/registry'
import { formatDate } from '../../lib/utils'
import { stateLabel } from '../../lib/stateLabel'
import { clockOf } from '../../lib/overviewTime'
import { OverviewCard, OverviewContext, num, useCardData, useLang } from './shared'

// Protocols with a daily series, then the services that only report a state
const SERIES = ['acme', 'scep', 'est']
const SERVICES = ['tsa', 'scheduler', 'smtp', 'webhooks', 'auto_renewal']
// Settings witnesses: a state of a setting, no series and no last operation
const WITNESSES = ['smtp', 'webhooks', 'auto_renewal']
const GOOD_STATES = ['ok', 'success', 'ready', 'active', 'enabled', 'dedicated']
const ROW_LINKS = {
  tsa: '/tsa-config', scheduler: '/settings?tab=scheduler', smtp: '/settings?tab=email',
  webhooks: '/settings?tab=webhooks', auto_renewal: '/settings?tab=autoRenewal',
}
const TONE_ICON = { good: 'check', warn: 'warning', bad: 'warning' }

/** The row's link, only when the navigation guard of its page lets this user in. */
function rowLink(name, can) {
  const link = ROW_LINKS[name]
  const mod = link && moduleForPath(link.split('?')[0])
  return mod && isVisible(mod, can) ? link : null
}

const count = (v) => Number(v) || 0
const sum = (periods, key) => periods.reduce((total, p) => total + count(p[key]), 0)

/** What the line says and whether it is an alert: the signer's state, the scheduler's failures, else the last status. */
function summary(name, p, t) {
  if (name === 'tsa') {
    const key = p.state === 'unusable' ? `overview.health.tsaReason.${p.reason}` : `overview.health.tsaState.${p.state}`
    return { text: t(key, { count: p.days_left, defaultValue: p.state }), alert: Boolean(p.alert),
      warning: p.severity === 'warning', state: p.state }
  }
  if (WITNESSES.includes(name)) {
    if (p.state === 'unavailable') return { text: t('overview.health.witness.unavailable'), alert: true }
    return { text: t(`overview.health.witness.${name}.${p.state}`, { count: p.count, defaultValue: p.state }),
      alert: Boolean(p.alert), state: p.state }
  }
  if (name === 'scheduler') {
    const failed = count(p.by_status?.failed)
    const warned = count(p.by_status?.warning)
    if (p.stale) return { text: t('overview.health.stale'), alert: true }
    if (failed > 0) return { text: t('overview.health.tasksFailed', { count: failed }), alert: true }
    if (warned > 0) return { text: t('overview.health.tasksWarning', { count: warned }), alert: false, caution: true }
  }
  return { text: stateLabel(t, p.last_status), alert: p.last_status === 'failed', state: p.last_status }
}

function toneOf({ alert, warning, caution, state }) {
  if (alert) return warning ? 'warn' : 'bad'
  if (caution) return 'warn'
  return GOOD_STATES.includes(String(state || '').toLowerCase()) ? 'good' : ''
}

/** A state in words, with its icon (the mockup's badge); the tone only repeats it in colour. */
function StateBadge({ info }) {
  if (!info.text || info.text === '–') return null
  const tone = toneOf(info)
  return <span className={tone ? `badge ${tone}` : 'badge'} data-tone={tone || 'neutral'}><Icon name={TONE_ICON[tone] || 'block'} />{info.text}</span>
}

/** The mockup's sparkline(): one point per day, successes above the baseline, failures as ticks below it. */
function Sparkline({ id, periods, label }) {
  const w = 140
  const h = 40
  const top = 5
  const base = 27
  const ok = periods.map((p) => count(p.ok))
  const failed = periods.map((p) => count(p.failed))
  const peak = Math.max(1, ...ok)
  const peakFailed = Math.max(1, ...failed)
  const step = periods.length > 1 ? (w - 10) / (periods.length - 1) : 0
  const x = (i) => (5 + i * step).toFixed(1)
  const y = (n) => (base - 3 - (n / peak) * (base - 3 - top)).toFixed(1)
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img" aria-labelledby={`spark-${id}`}>
      <title id={`spark-${id}`}>{label}</title>
      <line className="spark-base" x1="0" x2={w} y1={base} y2={base} vectorEffect="non-scaling-stroke" />
      {failed.map((n, i) => n > 0 && (
        <line key={`f${periods[i].date}`} className="spark-fail" x1={x(i)} x2={x(i)} y1={base + 3}
          y2={(base + 4 + (n / peakFailed) * (h - base - 5)).toFixed(1)} vectorEffect="non-scaling-stroke" />
      ))}
      <polyline className="spark-line" points={ok.map((n, i) => `${x(i)},${y(n)}`).join(' ')} vectorEffect="non-scaling-stroke" />
      {ok.map((n, i) => (
        <line key={periods[i].date} className={`spark-dot ${i === ok.length - 1 ? 'last' : ''}`}
          x1={x(i)} x2={x(i)} y1={y(n)} y2={y(n)} vectorEffect="non-scaling-stroke" />
      ))}
    </svg>
  )
}

/** The mockup's healthStat(): the span, the successes, the failures (a link to the queue for ACME). */
function Stat({ span, ok, failed, onFailures, label, t }) {
  let failure = <span className="muted">{t('overview.health.failures', { count: 0 })}</span>
  if (failed > 0) {
    failure = onFailures
      ? <button type="button" className="fail-link" aria-label={label} onClick={onFailures}><Icon name="warning" />{t('overview.health.failures', { count: failed })}</button>
      : <span className="bad"><Icon name="warning" />{t('overview.health.failures', { count: failed })}</span>
  }
  return (
    <div className="health-stat">
      <span className="health-span">{span}</span>
      <span className="health-values"><span><Trans i18nKey="overview.health.runs" count={ok} components={{ strong: <strong /> }} /></span>{failure}</span>
    </div>
  )
}

export function HealthCard() {
  const { t } = useTranslation()
  const lang = useLang()
  const page = useContext(OverviewContext)
  const { isAdmin, hasPermission } = usePermission()
  const can = { isAdmin, hasPermission }
  const state = useCardData(() => overviewService.getHealth(), ['certificate'], 'health')
  const protocols = state.data?.protocols || {}
  const series = SERIES.filter((p) => protocols[p])
  const services = SERVICES.filter((p) => protocols[p])
  const infos = Object.fromEntries([...series, ...services].map((name) => [name, summary(name, protocols[name], t)]))
  const alerts = Object.values(infos).filter((i) => i.alert).length
  const acmeToday = count((protocols.acme?.periods || []).at(-1)?.failed)
  const lastRun = protocols.scheduler?.last_operation_at
  const days = state.data?.days
  const toQueue = page?.showQueue ? () => page.showQueue('acme') : null

  const name = (id) => {
    const link = rowLink(id, can)
    const label = t(`overview.health.${id}`)
    return <strong>{link ? <Link to={link}>{label}</Link> : label}</strong>
  }
  const rowProps = (id) => {
    const info = infos[id]
    return { 'data-protocol': id, 'data-alert': info.alert ? 'true' : 'false',
      'data-severity': info.alert ? (info.warning ? 'warning' : 'critical') : undefined }
  }

  return (
    <OverviewCard id="health" state={state} route="GET /api/v2/dashboard/health"
      empty={state.status === 'ready' && series.length + services.length === 0}
      sub={[
        lastRun ? t('overview.health.subScheduler', { when: clockOf(lastRun, t, lang) }) : null,
        typeof days === 'number' ? t('overview.health.sub', { count: days }) : null,
      ].filter(Boolean).join(' ')}>
      <ul className="health-list panel-content">
        {series.map((id) => {
          const p = protocols[id]
          const periods = Array.isArray(p.periods) ? p.periods : []
          const today = periods.at(-1)
          const label = t(`overview.health.${id}`)
          return (
            <li key={id} className="health-row" {...rowProps(id)}>
              <div className="health-name">
                {name(id)}
                <small title={p.last_operation_at ? formatDate(p.last_operation_at, { time: true }) : undefined}>
                  {p.last_operation_at
                    ? t('overview.health.lastOperation', { when: clockOf(p.last_operation_at, t, lang) })
                    : t('overview.health.idle', { count: periods.length || days || 7 })}
                </small>
                {/* A good state stays silent, as in the mockup; a failure or an unknown state is said */}
                {toneOf(infos[id]) !== 'good' && <StateBadge info={infos[id]} />}
              </div>
              {periods.length > 0 && (
                <div className="health-stats">
                  <Stat span={t('overview.health.today')} ok={count(today?.ok)} failed={count(today?.failed)} t={t}
                    onFailures={id === 'acme' ? toQueue : null} label={t('overview.health.failLink', { count: count(today?.failed), name: label, span: t('overview.health.today') })} />
                  <Stat span={t('overview.days', { count: periods.length })} ok={sum(periods, 'ok')} failed={sum(periods, 'failed')} t={t}
                    onFailures={id === 'acme' ? toQueue : null} label={t('overview.health.failLink', { count: sum(periods, 'failed'), name: label, span: t('overview.days', { count: periods.length }) })} />
                </div>
              )}
              {periods.length > 0 && (
                <Sparkline id={id} periods={periods} label={t('overview.health.sparkAlt', {
                  name: label, ok: periods.map((d) => count(d.ok)).join(', '), failed: periods.map((d) => count(d.failed)).join(', '),
                })} />
              )}
            </li>
          )
        })}
        {services.map((id) => {
          const p = protocols[id]
          return (
            <li key={id} className="health-row" {...rowProps(id)}>
              <div className="health-name">
                {name(id)}
                {id === 'scheduler' && (
                  <small title={p.last_operation_at ? formatDate(p.last_operation_at, { time: true }) : undefined}>
                    {t('overview.health.taskCount', { count: num(p.tasks) })}
                    {p.last_operation_at ? `, ${t('overview.health.lastRun', { when: clockOf(p.last_operation_at, t, lang) })}` : ''}
                  </small>
                )}
              </div>
              <div className="health-stats"><StateBadge info={infos[id]} /></div>
            </li>
          )
        })}
      </ul>
      {alerts > 0 ? (
        <p className="health-foot">
          <Icon name="warning" />
          <span>{t('overview.health.alerts', { count: alerts })}</span>
          {acmeToday > 0 && toQueue && (
            <button type="button" className="text-link" onClick={toQueue}>{t('overview.health.seeQueue')} <Icon name="right" /></button>
          )}
        </p>
      ) : (
        <p className="health-foot good"><Icon name="check" /><span>{t('overview.health.allFine')}</span></p>
      )}
    </OverviewCard>
  )
}
