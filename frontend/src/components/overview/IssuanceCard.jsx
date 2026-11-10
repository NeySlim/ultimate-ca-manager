import { useTranslation } from 'react-i18next'
import { overviewService } from '../../services'
import { CardFrame, Counter, num, useCardData } from './shared'

export function IssuanceCard() {
  const { t } = useTranslation()
  const state = useCardData(() => overviewService.getIssuance())
  const data = state.data || {}
  const bySource = data.by_source && typeof data.by_source === 'object' ? Object.entries(data.by_source) : []
  const byCa = Array.isArray(data.by_ca) ? data.by_ca : []

  return (
    <CardFrame id="issuance" title={t('overview.cards.issuance')} state={state} onRetry={state.reload}
      empty={state.status === 'ready' && data.total === 0 && data.renewed === 0}>
      <div>
        <Counter label={t('overview.issuance.issued')} count={data.total} />
        <Counter label={t('overview.issuance.renewed')} count={data.renewed} />
      </div>
      {bySource.length > 0 && (
        <div aria-label={t('overview.issuance.bySource')}>
          {bySource.map(([source, n]) => <Counter key={source} label={source} count={n} />)}
        </div>
      )}
      {byCa.length > 0 && (
        <div aria-label={t('overview.issuance.byCa')}>
          {byCa.slice(0, 5).map((ca) => (
            <Counter key={ca.caref ?? ca.ca_id} label={ca.ca_name ?? '–'} count={ca.total} />
          ))}
        </div>
      )}
    </CardFrame>
  )
}
