import { useTranslation } from 'react-i18next'
import { CheckCircle, Key, Warning } from '@phosphor-icons/react'
import { overviewService } from '../../services'
import { listHref } from '../../lib/overviewFilters'
import { CardFrame, MaybeLink, num, useCardData } from './shared'

const COUNTERS = ['rsa_below_3072', 'weak_signature_hash', 'server_lifetime_over_398_days',
  'incomplete_chain', 'no_private_key']
// A count, not a weakness: no warning colour whatever the figure
const NEUTRAL = ['no_private_key']
const ALGORITHMS = 5

export function ComplianceCard() {
  const { t } = useTranslation()
  const state = useCardData(() => overviewService.getCompliance(), ['certificate', 'ca'])
  const data = state.data || {}
  const counters = data.counters || {}
  const algos = Array.isArray(data.by_key_algorithm) ? data.by_key_algorithm.slice(0, ALGORITHMS) : []
  const link = (entry) => (entry?.filter_available ? listHref(entry.filter_hint) : null)
  const share = (n) => (data.total > 0 && typeof n === 'number' ? Math.min(100, (n / data.total) * 100) : 0)

  return (
    <CardFrame id="compliance" title={t('overview.cards.compliance')} state={state} onRetry={state.reload}
      empty={state.status === 'ready' && data.total === 0} count={num(data.total)}
      sub={t('overview.compliance.sub')}>
      <div className="ov-body">
        <div className={`ov-compliance${algos.length > 0 ? ' has-algo' : ''}`}>
          {algos.length > 0 && (
            <div className="ov-tile is-algo">
              <h3 className="ov-tile-label" id="overview-compliance-algos">{t('overview.compliance.byAlgorithm')}</h3>
              <ul className="ov-algo-list" aria-labelledby="overview-compliance-algos">
                {algos.map((entry) => (
                  <li key={entry.key_algo ?? 'none'}>
                    <MaybeLink to={link(entry)} className="ov-algo-row">
                      <span>{entry.key_algo ?? t('overview.compliance.unknownAlgo')}</span>
                      <strong>{num(entry.count)}</strong>
                      <span className="ov-algo-bar" aria-hidden="true">
                        <span data-testid="algo-bar" style={{ width: `${share(entry.count)}%` }} />
                      </span>
                    </MaybeLink>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="ov-tiles">
            {COUNTERS.map((name) => {
              const n = counters[name]?.count
              const known = typeof n === 'number' && Number.isFinite(n)
              const tone = !known || NEUTRAL.includes(name) ? '' : n > 0 ? 'is-warn' : 'is-good'
              const Icon = NEUTRAL.includes(name) ? Key : n > 0 ? Warning : CheckCircle
              return (
                <MaybeLink key={name} to={link(counters[name])} className="ov-tile" data-testid={`compliance-${name}`}>
                  <span className={`ov-tile-value ${tone}`}>
                    {known && <Icon size={16} aria-hidden="true" />}
                    <strong>{num(n)}</strong>
                  </span>
                  <span className="ov-tile-label">{t(`overview.compliance.${name}`)}</span>
                </MaybeLink>
              )
            })}
          </div>
        </div>
      </div>
    </CardFrame>
  )
}
