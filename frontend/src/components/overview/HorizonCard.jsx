/**
 * The mockup's horizon() card over GET /dashboard/expiring-certs and /dashboard/stats. The weekly
 * histogram of the mockup needs a server aggregate the product has not; the card lists the
 * soonest expiries instead (the mockup's algo rows: name, delay, validity spent), then the
 * certificates per state as the mockup's status list.
 */
import { useContext } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Icon } from '../atelier'
import { dashboardService } from '../../services'
import { elapsedPercent } from '../../lib/overviewTime'
import { compactDue, dueTone } from '../../lib/relativeTime'
import { formatDate } from '../../lib/utils'
import { OverviewCard, OverviewContext, num, settle, useCardData } from './shared'

const SOONEST = 6
// The mockup's statuses, in its order, with the field of /dashboard/stats and the dot's tone
const STATES = [
  { key: 'valid', field: 'valid', tone: 'good' }, { key: 'expiring', field: 'expiring_soon', tone: 'warn' },
  { key: 'expired', field: 'expired', tone: 'bad' }, { key: 'revoked', field: 'revoked', tone: 'muted' },
]

export function HorizonCard() {
  const { t } = useTranslation()
  const page = useContext(OverviewContext)
  // The counters are the strip's and the assistant's read: one request for the three
  const stats = () => (page?.share ? page.share('stats', () => dashboardService.getStats()) : dashboardService.getStats())
  const state = useCardData(async () => {
    const { got, missing } = await settle(
      { stats, next: () => dashboardService.getNextExpirations(SOONEST) },
      (g) => Boolean(g.stats) || g.next?.data?.length > 0)
    return { data: { stats: got.stats?.data, next: got.next?.data, missing } }
  }, ['certificate'])
  const counts = state.data?.stats || {}
  const next = Array.isArray(state.data?.next) ? state.data.next.slice(0, SOONEST) : []

  return (
    <OverviewCard id="horizon" state={state} route="GET /api/v2/dashboard/expiring-certs" missing={state.data?.missing}
      sub={t('overview.horizon.sub')}
      empty={state.status === 'ready' && counts.total_certificates === 0 && next.length === 0}
      tools={<Link to="/certificates?status=expiring" className="text-link">{t('common.viewAll')} <Icon name="right" /></Link>}>
      <div className="panel-content">
        {next.length > 0 && (
          <ul className="algo-list" aria-label={t('overview.horizon.soonest')}>
            {next.map((c) => {
              const spent = elapsedPercent(c.valid_from, c.valid_to)
              const tone = dueTone(c.valid_to)
              const markers = [c.is_tsa_signer && t('overview.horizon.tsaSigner'), c.is_ocsp_responder && t('overview.horizon.ocspResponder')].filter(Boolean)
              return (
                <li key={c.id} data-urgency={tone || 'good'}>
                  <Link to={`/certificates/${c.id}`} className="algo-row" title={c.valid_to ? formatDate(c.valid_to) : undefined}>
                    <span>{c.common_name || c.descr || '–'}{markers.length > 0 && <span className="muted">{` · ${markers.join(' · ')}`}</span>}</span>
                    <strong className={tone || undefined}>{c.valid_to ? compactDue(c.valid_to, t) : '–'}</strong>
                    {spent !== null && (
                      <span className="algo-bar" role="img" aria-label={t('overview.horizon.elapsed', { percent: spent })}>
                        <span style={{ width: `${Math.max(2, spent)}%` }} />
                      </span>
                    )}
                  </Link>
                </li>
              )
            })}
          </ul>
        )}
        <div className="status-list">
          {STATES.map((s) => (
            <div key={s.key} data-state={s.key}>
              <span className={`dot ${s.tone}`} aria-hidden="true" />
              <Link to={`/certificates?status=${s.key}`}>{t(`overview.horizon.state.${s.key}`)}</Link>
              <strong>{num(counts[s.field])}</strong>
            </div>
          ))}
        </div>
      </div>
    </OverviewCard>
  )
}
