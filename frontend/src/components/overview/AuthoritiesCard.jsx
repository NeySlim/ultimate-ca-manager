import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { casService } from '../../services'
import { formatDate } from '../../lib/utils'
import { CardFrame, num, useCardData } from './shared'

export function AuthoritiesCard() {
  const { t } = useTranslation()
  const state = useCardData(() => casService.getAll())
  const cas = Array.isArray(state.data) ? state.data : []

  return (
    <CardFrame id="authorities" title={t('overview.cards.authorities')} state={state} onRetry={state.reload}
      empty={state.status === 'ready' && cas.length === 0}
      action={<Link to="/cas" className="text-sm font-semibold tabular-nums">{num(state.meta?.total)}</Link>}>
      <ul className="flex flex-col divide-y divide-border-op30">
        {cas.slice(0, 5).map((ca) => (
          <li key={ca.id} className="py-1.5">
            <Link to={`/cas/${ca.id}`} className="flex items-center justify-between gap-3">
              <span className="text-sm text-text-primary truncate">{ca.descr || ca.common_name || '–'}</span>
              <span className="text-xs text-text-secondary">{ca.valid_to ? formatDate(ca.valid_to) : '–'}</span>
            </Link>
          </li>
        ))}
      </ul>
    </CardFrame>
  )
}
