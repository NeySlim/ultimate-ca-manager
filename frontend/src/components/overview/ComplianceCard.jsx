/**
 * The mockup's complianceCard() over GET /dashboard/compliance: the key algorithms with their
 * share, then one tile per check. A tile the server gives a list filter for opens that list.
 */
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Icon } from '../atelier'
import { overviewService } from '../../services'
import { listHref } from '../../lib/overviewFilters'
import { OverviewCard, num, useCardData } from './shared'

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

  const tile = (name) => {
    const n = counters[name]?.count
    const known = typeof n === 'number' && Number.isFinite(n)
    const neutral = NEUTRAL.includes(name)
    const tone = !known || neutral ? '' : n > 0 ? 'warn' : 'good'
    const inner = (
      <>
        <span className={tone ? `tile-value ${tone}` : 'tile-value'}>
          {known && <Icon name={neutral ? 'key' : n > 0 ? 'warning' : 'check'} />}<strong>{num(n)}</strong>
        </span>
        <span className="tile-label">{t(`overview.compliance.${name}`)}</span>
        <small>{t(`overview.compliance.sub_${name}`)}</small>
      </>
    )
    const to = link(counters[name])
    return to
      ? <Link key={name} className="tile" to={to} data-check={name}>{inner}</Link>
      : <div key={name} className="tile" data-check={name}>{inner}</div>
  }

  return (
    <OverviewCard id="compliance" state={state} route="GET /api/v2/dashboard/compliance"
      empty={state.status === 'ready' && data.total === 0}
      sub={t('overview.compliance.sub', { count: num(data.total) })}>
      <div className="panel-content">
        <div className="tiles">
          <div className="tile algo">
            <h3 className="tile-label">{t('overview.compliance.byAlgorithm')}</h3>
            <ul className="algo-list">
              {algos.map((entry) => {
                const name = entry.key_algo ?? t('overview.compliance.unknownAlgo')
                const inner = (
                  <>
                    <span>{name}</span><strong>{num(entry.count)}</strong>
                    <span className="algo-bar" aria-hidden="true"><span style={{ width: `${share(entry.count)}%` }} /></span>
                  </>
                )
                const to = link(entry)
                const label = t('overview.compliance.algoLabel', { name, count: num(entry.count) })
                return (
                  <li key={entry.key_algo ?? 'none'}>
                    {to
                      ? <Link to={to} className="algo-row" data-check={`algo-${entry.key_algo}`} aria-label={label}>{inner}</Link>
                      : <span className="algo-row" aria-label={label}>{inner}</span>}
                  </li>
                )
              })}
            </ul>
          </div>
          {COUNTERS.map(tile)}
        </div>
      </div>
    </OverviewCard>
  )
}
