import { useTranslation } from 'react-i18next'
import { overviewService } from '../../services'
import { listHref } from '../../lib/overviewFilters'
import { CardFrame, Counter, num, useCardData } from './shared'

const COUNTERS = ['rsa_below_3072', 'weak_signature_hash', 'server_lifetime_over_398_days',
  'incomplete_chain', 'no_private_key']

export function ComplianceCard() {
  const { t } = useTranslation()
  const state = useCardData(() => overviewService.getCompliance())
  const data = state.data || {}
  const counters = data.counters || {}
  const algos = Array.isArray(data.by_key_algorithm) ? data.by_key_algorithm : []
  const link = (entry) => (entry?.filter_available ? listHref(entry.filter_hint) : null)

  return (
    <CardFrame id="compliance" title={t('overview.cards.compliance')} state={state} onRetry={state.reload}
      empty={state.status === 'ready' && data.total === 0}
      action={<span className="text-sm font-semibold tabular-nums">{num(data.total)}</span>}>
      <div>
        {COUNTERS.map((name) => (
          <Counter key={name} label={t(`overview.compliance.${name}`)} count={counters[name]?.count}
            to={link(counters[name])} />
        ))}
      </div>
      {algos.length > 0 && (
        <div aria-label={t('overview.compliance.byAlgorithm')}>
          {algos.slice(0, 5).map((entry) => (
            <Counter key={entry.key_algo ?? 'none'} label={entry.key_algo ?? t('overview.compliance.unknownAlgo')}
              count={entry.count} to={link(entry)} />
          ))}
        </div>
      )}
    </CardFrame>
  )
}
