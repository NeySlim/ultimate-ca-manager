/**
 * Automation health over GET /dashboard/health (maquette-3): one row per protocol with its last
 * operation, 30 days of mirror bars (successes up, failures down) and its success rate, then the
 * services that only report a state as compact pills, and the summary under them.
 */
import { useContext, useEffect, useRef, useState } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'
import { Icon } from '../atelier'
import { overviewService } from '../../services'
import { usePermission } from '../../hooks/usePermission'
import { isVisible, moduleForPath } from '../../navigation/registry'
import { formatDate } from '../../lib/utils'
import { stateLabel } from '../../lib/stateLabel'
import { clockOf } from '../../lib/overviewTime'
import { HEALTH_DAYS, failuresHref, successRate } from '../../lib/overviewViz'
import { OverviewCard, OverviewContext, num, useCardData, useLang } from './shared'
import { MirrorBars } from './viz'

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

/** A key that changes when a reload brings a scheduler run newer than the one shown: the pill beats again. */
function useNewRun(lastRun) {
  const seen = useRef(lastRun)
  const [beat, setBeat] = useState(0)
  useEffect(() => {
    const before = Date.parse(seen.current)
    if (Number.isFinite(before) && Date.parse(lastRun) > before) setBeat((b) => b + 1)
    if (lastRun) seen.current = lastRun
  }, [lastRun])
  return beat
}
const SERIES_COLOR = { acme: 'var(--s1)', scep: 'var(--s2)', est: 'var(--s3)' }

/** The row's link, only when the navigation guard of its page lets this user in. */
function rowLink(name, can) {
  const link = ROW_LINKS[name]
  const mod = link && moduleForPath(link.split('?')[0])
  return mod && isVisible(mod, can) ? link : null
}

const count = (v) => Number(v) || 0
const sum = (periods, key) => periods.reduce((total, p) => total + count(p[key]), 0)
const periodsOf = (p) => (Array.isArray(p?.periods) ? p.periods : [])

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
    // Published, no task failed or warned: the scheduler is fine whatever its last task did (skipped)
    if (count(p.tasks) > 0) return { text: stateLabel(t, p.last_status), alert: false, state: 'ok' }
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

/** A day of a protocol series, as its tooltip and its table row write it. */
function dayOf(date, lang) {
  const at = new Date(`${date}T00:00:00Z`)
  if (Number.isNaN(at.getTime())) return date
  try { return new Intl.DateTimeFormat(lang, { day: 'numeric', month: 'short', timeZone: 'UTC' }).format(at) } catch { return date }
}

/** The success rate and the period's figures (maquette-3), ACME failures leading to the queue. */
function Rate({ ok, failed, onFailures, label, lang, t }) {
  const rate = successRate(ok, failed)
  let failure = <span className="muted">{t('overview.health.failures', { count: 0 })}</span>
  if (failed > 0) {
    failure = onFailures
      ? <button type="button" className="fail-link" aria-label={label} onClick={onFailures}><Icon name="warning" />{t('overview.health.failures', { count: failed })}</button>
      : <span className="bad"><Icon name="warning" />{t('overview.health.failures', { count: failed })}</span>
  }
  return (
    <div className="health-rate">
      <b className={failed > 0 ? 'warn' : undefined} data-rate={rate ?? ''}>
        {rate === null ? '–' : t('overview.health.rate', { rate: rate.toLocaleString(lang) })}
      </b>
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
  const state = useCardData(() => overviewService.getHealth(HEALTH_DAYS), ['certificate'], 'health')
  const protocols = state.data?.protocols || {}
  const series = SERIES.filter((p) => protocols[p])
  const services = SERVICES.filter((p) => protocols[p])
  const infos = Object.fromEntries([...series, ...services].map((name) => [name, summary(name, protocols[name], t)]))
  const alerts = Object.values(infos).filter((i) => i.alert).length
  // The queue lists the ACME orders failed in the last 7 days
  const acmeRecent = sum(periodsOf(protocols.acme).slice(-7), 'failed')
  const lastRun = protocols.scheduler?.last_operation_at
  const days = state.data?.days
  const toQueue = page?.showQueue ? () => page.showQueue('acme') : null
  const navigate = useNavigate()
  const toActivity = hasPermission('read:audit') ? (date) => navigate(failuresHref(date)) : null
  const beat = useNewRun(lastRun)

  const name = (id) => {
    const link = rowLink(id, can)
    const label = t(`overview.health.${id}`)
    return link ? <Link to={link}>{label}</Link> : label
  }
  const rowProps = (id) => {
    const info = infos[id]
    return { 'data-protocol': id, 'data-alert': info.alert ? 'true' : 'false',
      'data-severity': info.alert ? (info.warning ? 'warning' : 'critical') : undefined }
  }
  // The table view: one row per day, successes and failures of each protocol
  const withSeries = series.filter((id) => periodsOf(protocols[id]).length > 0)
  const table = () => {
    const dates = periodsOf(protocols[withSeries[0]]).map((p) => p.date)
    return [{
      caption: t('overview.health.tableCaption', { count: dates.length }),
      columns: [t('overview.trend.day'), ...withSeries.flatMap((id) => [
        t('overview.health.okOf', { name: t(`overview.health.${id}`) }), t('overview.health.failedOf', { name: t(`overview.health.${id}`) })])],
      rows: dates.map((date, i) => [date, ...withSeries.flatMap((id) => {
        const d = periodsOf(protocols[id])[i]
        return [count(d?.ok), count(d?.failed)]
      })]),
    }]
  }

  return (
    <OverviewCard id="health" state={state} route="GET /api/v2/dashboard/health"
      empty={state.status === 'ready' && series.length + services.length === 0}
      table={withSeries.length > 0 ? table : undefined}
      sub={[
        typeof days === 'number' ? t('overview.health.sub', { count: days }) : null,
        lastRun ? t('overview.health.subScheduler', { when: clockOf(lastRun, t, lang) }) : null,
      ].filter(Boolean).join(' ')}>
      <div className="panel-content health-body">
        {series.length > 0 && (
          <ul className="health-list">
            {series.map((id) => {
              const p = protocols[id]
              const periods = periodsOf(p)
              const label = t(`overview.health.${id}`)
              const ok = periods.map((d) => count(d.ok))
              const failed = periods.map((d) => count(d.failed))
              const okSum = sum(periods, 'ok')
              const failSum = sum(periods, 'failed')
              const span = t('overview.days', { count: periods.length })
              return (
                <li key={id} className="health-row proto" {...rowProps(id)}>
                  <div className="health-name">
                    <h3><i className="series-key" style={{ background: SERIES_COLOR[id] }} aria-hidden="true" /><strong>{name(id)}</strong>
                      {/* A good state stays silent, as in the mockup; a failure or an unknown state is said */}
                      {toneOf(infos[id]) !== 'good' && <StateBadge info={infos[id]} />}
                    </h3>
                    <small title={p.last_operation_at ? formatDate(p.last_operation_at, { time: true }) : undefined}>
                      {p.last_operation_at
                        ? t('overview.health.lastOperation', { when: clockOf(p.last_operation_at, t, lang) })
                        : t('overview.health.idle', { count: periods.length || days || HEALTH_DAYS })}
                    </small>
                  </div>
                  {periods.length > 0 && (
                    <MirrorBars ok={ok} failed={failed} color={SERIES_COLOR[id]}
                      label={t('overview.health.mirrorAlt', { name: label, count: periods.length, ok: okSum, failed: failSum })}
                      tipModel={(i) => ({
                        title: dayOf(periods[i].date, lang),
                        rows: [
                          { label: t('overview.health.ok'), value: ok[i], color: SERIES_COLOR[id] },
                          { label: t('overview.health.failed'), value: failed[i], color: 'var(--bad)' },
                        ],
                        hint: id !== 'acme' || failed[i] === 0 ? null
                          : toActivity ? t('overview.health.seeActivity') : toQueue ? t('overview.health.seeQueue') : null,
                      })}
                      onPick={id === 'acme' && (toActivity || toQueue) ? (i) => {
                        if (failed[i] === 0) return
                        if (toActivity) toActivity(periods[i].date)
                        else toQueue()
                      } : undefined} />
                  )}
                  {periods.length > 0 && (
                    <Rate ok={okSum} failed={failSum} lang={lang} t={t} onFailures={id === 'acme' ? toQueue : null}
                      label={t('overview.health.failLink', { count: failSum, name: label, span })} />
                  )}
                </li>
              )
            })}
          </ul>
        )}
        {services.length > 0 && (
          <ul className="services">
            {services.map((id) => {
              const p = protocols[id]
              const info = infos[id]
              const tone = toneOf(info)
              let text = info.text
              // The scheduler's tasks and last run, unless a problem says more
              if (id === 'scheduler' && !info.alert && !info.caution) {
                text = [t('overview.health.taskCount', { count: num(p.tasks) }),
                  p.last_operation_at ? t('overview.health.lastRun', { when: clockOf(p.last_operation_at, t, lang) }) : null].filter(Boolean).join(', ')
              }
              return (
                <li key={id} className="health-row svc" data-tone={tone || 'neutral'} {...rowProps(id)}
                  title={id === 'scheduler' && p.last_operation_at ? formatDate(p.last_operation_at, { time: true }) : undefined}>
                  <i key={id === 'scheduler' ? `beat-${beat}` : undefined} className={id === 'scheduler' && beat > 0 ? 'pulse live' : 'pulse'}
                    data-beat={id === 'scheduler' ? beat : undefined} aria-hidden="true" />
                  <strong>{name(id)}</strong>
                  <span className="svc-state">{text}</span>
                  <Icon name={TONE_ICON[tone] || 'block'} />
                </li>
              )
            })}
          </ul>
        )}
      </div>
      {alerts > 0 ? (
        <p className="health-foot">
          <Icon name="warning" />
          <span>{t('overview.health.alerts', { count: alerts })}</span>
          {acmeRecent > 0 && toQueue && (
            <button type="button" className="text-link" onClick={toQueue}>{t('overview.health.seeQueue')} <Icon name="right" /></button>
          )}
        </p>
      ) : (
        <p className="health-foot good"><Icon name="check" /><span>{t('overview.health.allFine')}</span></p>
      )}
    </OverviewCard>
  )
}
