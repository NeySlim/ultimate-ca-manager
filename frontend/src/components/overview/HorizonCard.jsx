import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { certificatesService, dashboardService } from '../../services'
import { formatDate } from '../../lib/utils'
import { CardFrame, Counter, settle, useCardData } from './shared'

const SOONEST = 5

export function HorizonCard() {
  const { t } = useTranslation()
  const state = useCardData(async () => {
    const { got, missing } = await settle(
      { stats: () => certificatesService.getStats(), next: () => dashboardService.getNextExpirations(SOONEST) },
      (g) => Boolean(g.stats) || g.next?.data?.length > 0)
    return { data: { stats: got.stats?.data, next: got.next?.data, missing } }
  })
  const stats = state.data?.stats || {}
  const next = Array.isArray(state.data?.next) ? state.data.next : []

  return (
    <CardFrame id="horizon" title={t('overview.cards.horizon')} state={state} onRetry={state.reload}
      missing={state.data?.missing}
      empty={state.status === 'ready' && stats.total === 0}>
      <div>
        <Counter label={t('overview.horizon.expiring')} count={stats.expiring} to="/certificates?status=expiring" />
        <Counter label={t('overview.horizon.expired')} count={stats.expired} to="/certificates?status=expired" />
      </div>
      {next.length > 0 && (
        <ul aria-label={t('overview.horizon.soonest')} className="flex flex-col divide-y divide-border-op30">
          {next.map((c) => (
            <li key={c.id} className="py-1.5">
              <Link to={`/certificates/${c.id}`} className="flex items-center justify-between gap-3">
                <span className="text-sm text-text-primary truncate">{c.common_name || c.descr || '–'}</span>
                <span className="text-xs text-text-secondary">{c.valid_to ? formatDate(c.valid_to) : '–'}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </CardFrame>
  )
}
