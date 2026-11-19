import { useContext } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { CaretRight, CheckCircle, MinusCircle, Warning, WarningCircle } from '@phosphor-icons/react'
import { overviewService } from '../../services'
import { usePermission } from '../../hooks/usePermission'
import { isVisible, moduleForPath } from '../../navigation/registry'
import { relativeTime } from '../../lib/overviewTime'
import { formatDate } from '../../lib/utils'
import { stateLabel } from '../../lib/stateLabel'
import { CardFrame, OverviewContext, Pill, num, useCardData, useLang } from './shared'

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
const TONE_ICON = { good: CheckCircle, warn: Warning, bad: WarningCircle }
const TONE_CLASS = { warn: 'text-status-warning font-medium', bad: 'text-status-danger font-medium' }

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
  return GOOD_STATES.includes(String(state || '').toLowerCase()) ? 'good' : undefined
}

function StatePill({ info }) {
  const tone = toneOf(info)
  if (info.text === '–') return null
  return <Pill tone={tone} icon={TONE_ICON[tone] || MinusCircle} className={TONE_CLASS[tone]}>{info.text}</Pill>
}

/** One point per day: successes above the baseline, failures as ticks under it. Drawn only with something to show. */
function Sparkline({ periods, label }) {
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
    <svg className="ov-spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img" aria-label={label}
      data-testid="health-spark">
      <line className="ov-spark-base" x1="0" x2={w} y1={base} y2={base} vectorEffect="non-scaling-stroke" />
      {failed.map((n, i) => n > 0 && (
        <line key={`f${periods[i].date}`} className="ov-spark-fail" x1={x(i)} x2={x(i)} y1={base + 3}
          y2={(base + 4 + (n / peakFailed) * (h - base - 5)).toFixed(1)} vectorEffect="non-scaling-stroke" />
      ))}
      <polyline className="ov-spark-line" points={ok.map((n, i) => `${x(i)},${y(n)}`).join(' ')} vectorEffect="non-scaling-stroke" />
      {ok.map((n, i) => (
        <line key={periods[i].date} className={`ov-spark-dot${i === ok.length - 1 ? ' is-last' : ''}`}
          x1={x(i)} x2={x(i)} y1={y(n)} y2={y(n)} vectorEffect="non-scaling-stroke" />
      ))}
    </svg>
  )
}

function Stat({ span, ok, failed, t }) {
  return (
    <div className="ov-health-stat">
      <span className="ov-muted">{span}</span>
      <span className="ov-health-values">
        <span className="ov-num">{t('overview.health.successes', { count: ok })}</span>
        {failed > 0
          ? <span className="ov-health-fail ov-num"><Warning size={13} aria-hidden="true" />{t('overview.health.failures', { count: failed })}</span>
          : <span className="ov-muted ov-num">{t('overview.health.failures', { count: 0 })}</span>}
      </span>
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

  const name = (id) => {
    const link = rowLink(id, can)
    const label = t(`overview.health.${id}`)
    return link ? <Link to={link}>{label}</Link> : <strong>{label}</strong>
  }
  const rowProps = (id) => {
    const info = infos[id]
    return { 'data-testid': `health-${id}`, 'data-alert': info.alert ? 'true' : 'false',
      'data-severity': info.alert ? (info.warning ? 'warning' : 'critical') : undefined }
  }

  return (
    <CardFrame id="health" title={t('overview.cards.health')} state={state} onRetry={state.reload}
      empty={state.status === 'ready' && series.length + services.length === 0}
      sub={[
        typeof days === 'number' ? t('overview.health.sub', { count: days }) : null,
        lastRun ? t('overview.health.subScheduler', { when: relativeTime(lastRun, lang) }) : null,
      ].filter(Boolean).join(' ')}>
      {series.length > 0 && (
        <ul className="ov-health-list">
          {series.map((id) => {
            const p = protocols[id]
            const periods = Array.isArray(p.periods) ? p.periods : []
            const today = periods.at(-1)
            const drawn = sum(periods, 'ok') + sum(periods, 'failed') > 0
            return (
              <li key={id} className="ov-health-row" {...rowProps(id)}>
                <div className="ov-health-name">
                  {name(id)}
                  <small title={p.last_operation_at ? formatDate(p.last_operation_at) : undefined}>
                    {p.last_operation_at
                      ? t('overview.health.lastOperation', { when: relativeTime(p.last_operation_at, lang) })
                      : t('overview.health.noOperation')}
                  </small>
                  <StatePill info={infos[id]} />
                </div>
                {periods.length > 0 && (
                  <div className="ov-health-stats">
                    <Stat span={t('overview.health.today')} ok={count(today?.ok)} failed={count(today?.failed)} t={t} />
                    <Stat span={t('overview.days', { count: periods.length })} ok={sum(periods, 'ok')} failed={sum(periods, 'failed')} t={t} />
                  </div>
                )}
                {drawn && (
                  <Sparkline periods={periods} label={t('overview.health.sparkAlt', {
                    name: t(`overview.health.${id}`),
                    ok: periods.map((d) => count(d.ok)).join(', '), failed: periods.map((d) => count(d.failed)).join(', '),
                  })} />
                )}
              </li>
            )
          })}
        </ul>
      )}
      {services.length > 0 && (
        <ul className="ov-services">
          {services.map((id) => {
            const p = protocols[id]
            return (
              <li key={id} className="ov-service" {...rowProps(id)}>
                <span className="ov-service-name">
                  {name(id)}
                  {id === 'scheduler' && (
                    <small title={p.last_operation_at ? formatDate(p.last_operation_at) : undefined}>
                      {t('overview.health.tasks')} {num(p.tasks)}
                      {p.last_operation_at ? ` · ${relativeTime(p.last_operation_at, lang)}` : ''}
                    </small>
                  )}
                </span>
                <StatePill info={infos[id]} />
              </li>
            )
          })}
        </ul>
      )}
      {alerts > 0 ? (
        <p className="ov-health-foot">
          <Warning size={14} aria-hidden="true" />
          <span>{t('overview.health.alerts', { count: alerts })}</span>
          {acmeToday > 0 && page?.showQueue && (
            <button type="button" className="ov-link" onClick={() => page.showQueue('acme')}>
              {t('overview.health.seeQueue')}<CaretRight size={12} aria-hidden="true" />
            </button>
          )}
        </p>
      ) : (
        <p className="ov-health-foot is-good"><CheckCircle size={14} aria-hidden="true" /><span>{t('overview.health.allFine')}</span></p>
      )}
    </CardFrame>
  )
}
