import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { CaretRight, CheckCircle, Clock, Warning } from '@phosphor-icons/react'
import { certificatesService, dashboardService } from '../../services'
import { daysUntil, elapsedPercent, urgencyOf } from '../../lib/overviewTime'
import { formatDate } from '../../lib/utils'
import { CardFrame, Pill, num, settle, useCardData } from './shared'

const SOONEST = 6
const URGENCY_ICON = { bad: Warning, warn: Clock, good: CheckCircle }

export function HorizonCard() {
  const { t } = useTranslation()
  const state = useCardData(async () => {
    const { got, missing } = await settle(
      { stats: () => certificatesService.getStats(), next: () => dashboardService.getNextExpirations(SOONEST) },
      (g) => Boolean(g.stats) || g.next?.data?.length > 0)
    return { data: { stats: got.stats?.data, next: got.next?.data, missing } }
  }, ['certificate'])
  const stats = state.data?.stats || {}
  const next = Array.isArray(state.data?.next) ? state.data.next.slice(0, SOONEST) : []

  return (
    <CardFrame id="horizon" title={t('overview.cards.horizon')} state={state} onRetry={state.reload}
      missing={state.data?.missing} sub={t('overview.horizon.sub')}
      empty={state.status === 'ready' && stats.total === 0}
      tools={(
        <Link to="/certificates?status=expiring" className="ov-link">
          {t('common.viewAll')}<CaretRight size={13} aria-hidden="true" />
        </Link>
      )}>
      <div className="ov-body">
        <div className="ov-status-list">
          <Link to="/certificates?status=expiring" className="ov-status is-warn">
            <Clock size={15} aria-hidden="true" />
            <span>{t('overview.horizon.expiring')}</span>
            <strong>{num(stats.expiring)}</strong>
          </Link>
          <Link to="/certificates?status=expired" className="ov-status is-bad">
            <Warning size={15} aria-hidden="true" />
            <span>{t('overview.horizon.expired')}</span>
            <strong>{num(stats.expired)}</strong>
          </Link>
        </div>
        {next.length > 0 && (
          <ul aria-label={t('overview.horizon.soonest')} className="ov-expiry-list">
            {next.map((c) => {
              const days = daysUntil(c.valid_to)
              const tone = urgencyOf(days)
              const spent = elapsedPercent(c.valid_from, c.valid_to)
              return (
                <li key={c.id} data-urgency={tone}>
                  <div className="ov-expiry-row">
                    <span className="ov-expiry-name">
                      <Link to={`/certificates/${c.id}`}>{c.common_name || c.descr || '–'}</Link>
                      {c.is_tsa_signer && <span className="ov-marker">{t('overview.horizon.tsaSigner')}</span>}
                      {c.is_ocsp_responder && <span className="ov-marker">{t('overview.horizon.ocspResponder')}</span>}
                    </span>
                    {days === null
                      ? <span className="ov-muted">–</span>
                      : (
                        <Pill tone={tone} icon={URGENCY_ICON[tone]} title={formatDate(c.valid_to)}>
                          {t('overview.horizon.expiresIn', { count: days })}
                        </Pill>
                      )}
                  </div>
                  {spent !== null && (
                    <div className={`ov-meter is-${tone}`} role="img" aria-label={t('overview.horizon.elapsed', { percent: spent })}>
                      <span style={{ width: `${Math.max(2, spent)}%` }} />
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </CardFrame>
  )
}
