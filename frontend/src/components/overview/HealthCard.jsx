import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { overviewService } from '../../services'
import { usePermission } from '../../hooks/usePermission'
import { isVisible, moduleForPath } from '../../navigation/registry'
import { formatDate } from '../../lib/utils'
import { stateLabel } from '../../lib/stateLabel'
import { CardFrame, num, useCardData } from './shared'

const PROTOCOLS = ['acme', 'scep', 'est', 'tsa', 'scheduler', 'smtp', 'webhooks', 'auto_renewal']
// Settings witnesses: a state of a setting, no series and no last operation
const WITNESSES = ['smtp', 'webhooks', 'auto_renewal']
const ROW_LINKS = {
  tsa: '/tsa-config', scheduler: '/settings?tab=scheduler', smtp: '/settings?tab=email',
  webhooks: '/settings?tab=webhooks', auto_renewal: '/settings?tab=autoRenewal',
}

/** The row's link, only when the navigation guard of its page lets this user in. */
function rowLink(name, can) {
  const link = ROW_LINKS[name]
  const mod = link && moduleForPath(link.split('?')[0])
  return mod && isVisible(mod, can) ? link : null
}

function Bars({ periods }) {
  const peak = Math.max(1, ...periods.map((p) => (Number(p.ok) || 0) + (Number(p.failed) || 0)))
  return (
    <span className="flex items-end gap-0.5 h-5" aria-hidden="true">
      {periods.map((p) => (
        <span key={p.date} title={`${p.date}: ${p.ok} / ${p.failed}`}
          className={`w-1.5 rounded-sm ${p.failed > 0 ? 'bg-status-danger' : 'bg-status-success'}`}
          style={{ height: `${Math.max(8, (((Number(p.ok) || 0) + (Number(p.failed) || 0)) / peak) * 100)}%` }} />
      ))}
    </span>
  )
}

/** What the line says and whether it is an alert: the signer's state, the scheduler's failures, else the last status. */
function summary(name, p, t) {
  if (name === 'tsa') {
    const key = p.state === 'unusable' ? `overview.health.tsaReason.${p.reason}` : `overview.health.tsaState.${p.state}`
    return { text: t(key, { count: p.days_left, defaultValue: p.state }), alert: Boolean(p.alert) }
  }
  if (WITNESSES.includes(name)) {
    return { text: t(`overview.health.witness.${name}.${p.state}`, { count: p.count, defaultValue: p.state }), alert: Boolean(p.alert) }
  }
  if (name === 'scheduler') {
    const failed = Number(p.by_status?.failed) || 0
    const warned = Number(p.by_status?.warning) || 0
    if (p.stale) return { text: t('overview.health.stale'), alert: true }
    if (failed > 0) return { text: t('overview.health.tasksFailed', { count: failed }), alert: true }
    if (warned > 0) return { text: t('overview.health.tasksWarning', { count: warned }), alert: false }
  }
  return { text: stateLabel(t, p.last_status), alert: p.last_status === 'failed' }
}

export function HealthCard() {
  const { t } = useTranslation()
  const { isAdmin, hasPermission } = usePermission()
  const can = { isAdmin, hasPermission }
  const state = useCardData(() => overviewService.getHealth(), ['certificate'])
  const protocols = state.data?.protocols || {}
  const present = PROTOCOLS.filter((p) => protocols[p])

  return (
    <CardFrame id="health" title={t('overview.cards.health')} state={state} onRetry={state.reload}
      empty={state.status === 'ready' && present.length === 0}>
      <ul className="flex flex-col gap-2">
        {present.map((name) => {
          const p = protocols[name]
          const { text, alert } = summary(name, p, t)
          const label = t(`overview.health.${name}`)
          const link = rowLink(name, can)
          return (
            <li key={name} data-testid={`health-${name}`} data-alert={alert ? 'true' : 'false'}
              className="flex items-center justify-between gap-3">
              {link
                ? <Link to={link} className="text-sm text-text-primary hover:text-accent-primary">{label}</Link>
                : <span className="text-sm text-text-primary">{label}</span>}
              <span className="flex items-center gap-3 text-xs text-text-secondary">
                {Array.isArray(p.periods) && <Bars periods={p.periods} />}
                {name === 'scheduler' && <span>{t('overview.health.tasks')} {num(p.tasks)}</span>}
                <span className={alert ? 'text-status-danger font-medium' : undefined}>{text}</span>
                {name !== 'tsa' && !WITNESSES.includes(name) && <span>{p.last_operation_at ? formatDate(p.last_operation_at) : '–'}</span>}
              </span>
            </li>
          )
        })}
      </ul>
    </CardFrame>
  )
}
