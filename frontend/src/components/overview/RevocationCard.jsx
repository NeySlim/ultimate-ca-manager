/**
 * Revocation coverage (maquette-1) over GET /dashboard/revocation: the share of active authorities
 * publishing a current CRL, the whole in three parts (current, stale or missing, no distribution
 * point), then the authorities to publish first, each with its action.
 */
import { useContext, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Icon } from '../atelier'
import { crlService, overviewService } from '../../services'
import { usePermission } from '../../hooks/usePermission'
import { compactDue } from '../../lib/relativeTime'
import { coverParts, daysSince } from '../../lib/overviewTiles'
import { OverviewCard, OverviewContext, useCardData } from './shared'
import { useChartTip } from './viz'

const LIST = 5
const n = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : 0)

export function RevocationCard() {
  const { t } = useTranslation()
  const page = useContext(OverviewContext)
  const { hasPermission } = usePermission()
  const tip = useChartTip()
  const state = useCardData(() => overviewService.getRevocation(LIST), ['ca'])
  const [busy, setBusy] = useState(null)
  const data = state.data || {}
  const total = n(data.total)
  const parts = coverParts(data)
  const share = total > 0 ? Math.floor((n(data.current) / total) * 100) : null
  const items = Array.isArray(data.items) ? data.items.slice(0, LIST) : []
  const canPublish = hasPermission('write:crl') && page?.notify
  const publish = (item) => async () => {
    setBusy(item.ca_id)
    try {
      await crlService.regenerate(item.ca_id)
      page.notify.showSuccess(t('notifications.crlRegenerated', { name: item.name }))
      window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'ca' } }))
    } catch (error) {
      page.notify.showError(error?.message || t('overview.queue.actionFailed'))
    } finally {
      setBusy(null)
      state.refresh()
    }
  }
  const stateText = (item) => {
    if (item.state === 'missing') return t('overview.tiles.crlMissing')
    if (item.state === 'stale') return item.next_update ? t('overview.tiles.crlStaleSince', { count: daysSince(item.next_update) }) : t('overview.tiles.crlStale')
    return item.next_update ? t('overview.revocation.nextIn', { when: compactDue(item.next_update, t) }) : t('overview.tiles.crlCurrent')
  }
  const table = () => [{
    caption: t('overview.revocation.tableCaption', { count: total }),
    columns: [t('overview.revocation.partCol'), t('overview.revocation.cas')],
    rows: parts.map((p) => [t(`overview.revocation.part.${p.key}`), p.value]),
  }]

  return (
    <OverviewCard id="revocation" state={state} route="GET /api/v2/dashboard/revocation" table={table}
      sub={t('overview.revocation.sub')}
      empty={state.status === 'ready' && total === 0}>
      <div className="panel-content">
        <div className="rev-head">
          <span className="fig">{share === null ? '–' : t('overview.compliance.pct', { pct: share })}</span>
          <span className="muted">{t('overview.revocation.headline', { count: total })}</span>
        </div>
        <span className="cover" role="img" aria-label={parts.map((p) => `${t(`overview.revocation.part.${p.key}`)} : ${p.value}`).join(', ')}>
          {/* The grey part is not 4.5:1 under the card's colour: its figure is in the legend only */}
          {parts.filter((p) => p.value > 0).map((p) => (
            <i key={p.key} data-part={p.key} tabIndex={0} style={{ flexGrow: p.value, background: p.color }}
              {...tip.bind({ title: t(`overview.revocation.part.${p.key}`), rows: [
                { label: t('overview.revocation.cas'), value: p.value },
                { label: t('overview.compliance.share'), value: t('overview.compliance.pct', { pct: Math.round((p.value / total) * 100) }) },
              ] })}>
              {p.key !== 'noCdp' && p.value / total >= 0.15 ? p.value : ''}
            </i>
          ))}
        </span>
        <ul className="legend cover-legend">
          {parts.map((p) => <li key={p.key}><i className="swatch" style={{ background: p.color }} />{t(`overview.revocation.part.${p.key}`)}<b>{p.value}</b></li>)}
        </ul>
        {items.length > 0 && (
          <ul className="rev-list">
            {items.map((item) => {
              const bad = item.state === 'stale' || item.state === 'missing'
              return (
                <li key={item.ca_id} data-ca={item.ca_id} data-state={item.state}>
                  <span className={bad ? 'bad' : 'muted'}><Icon name={bad ? 'warning' : 'clock'} /></span>
                  <span>
                    <Link to={item.href_hint || `/crl-ocsp?ca=${item.ca_id}`}><b>{item.name}</b></Link>
                    <span className={bad ? 'bad' : 'muted'}>{stateText(item)}</span>
                  </span>
                  {bad && item.can_publish && canPublish
                    ? <button type="button" className="text-link" data-action="publish-crl" disabled={busy === item.ca_id} onClick={publish(item)}>{t('overview.revocation.publish')}</button>
                    : <span className="muted">{bad && item.offline ? t('overview.hierarchy.offline') : t(item.ocsp_enabled ? 'overview.hierarchy.ocspOn' : 'overview.hierarchy.ocspOff')}</span>}
                </li>
              )
            })}
          </ul>
        )}
      </div>
      {tip.node}
    </OverviewCard>
  )
}
