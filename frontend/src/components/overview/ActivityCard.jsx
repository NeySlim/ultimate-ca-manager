import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { dashboardService } from '../../services'
import { usePermission } from '../../hooks/usePermission'
import { formatDate } from '../../lib/utils'
import { CardFrame, useCardData } from './shared'

const LATEST = 5

export function ActivityCard() {
  const { t } = useTranslation()
  const { hasPermission } = usePermission()
  const state = useCardData(() => dashboardService.getActivityLog(LATEST))
  const rows = Array.isArray(state.data?.activity) ? state.data.activity : []

  return (
    <CardFrame id="activity" title={t('overview.cards.activity')} state={state} onRetry={state.reload}
      empty={state.status === 'ready' && rows.length === 0}
      action={hasPermission('read:audit')
        ? <Link to="/audit" className="text-sm">{t('overview.activity.all')}</Link> : null}>
      <ul className="flex flex-col divide-y divide-border-op30">
        {rows.slice(0, LATEST).map((a, i) => (
          <li key={`${a.timestamp}-${i}`} className="py-1.5 flex items-center justify-between gap-3">
            <span className="min-w-0">
              <span className="block text-sm text-text-primary truncate">{a.message}</span>
              <span className="block text-xs text-text-secondary">{a.user}</span>
            </span>
            <time className="text-xs text-text-secondary whitespace-nowrap">{a.timestamp ? formatDate(a.timestamp) : '–'}</time>
          </li>
        ))}
      </ul>
    </CardFrame>
  )
}
