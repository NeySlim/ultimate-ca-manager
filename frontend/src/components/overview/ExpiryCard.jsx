import { useTranslation } from 'react-i18next'
import { certificatesService } from '../../services'
import { CardFrame, Counter, useCardData } from './shared'

const BUCKETS = ['valid', 'expiring', 'expired', 'revoked']

export function ExpiryCard() {
  const { t } = useTranslation()
  const state = useCardData(() => certificatesService.getStats())
  const data = state.data || {}

  return (
    <CardFrame id="expiry" title={t('overview.cards.expiry')} state={state} onRetry={state.reload}
      empty={state.status === 'ready' && data.total === 0}>
      <div>
        {BUCKETS.map((bucket) => (
          <Counter key={bucket} label={t(`overview.expiry.${bucket}`)} count={data[bucket]}
            to={`/certificates?status=${bucket}`} />
        ))}
      </div>
    </CardFrame>
  )
}
