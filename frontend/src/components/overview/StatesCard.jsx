import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { dashboardService } from '../../services'
import { donutSlices } from '../../lib/overviewChart'
import { CardFrame, num, useCardData, useLang } from './shared'

// Fixed order and colour per state, whatever the figures; each opens its list
const STATES = [
  { key: 'valid', field: 'valid' }, { key: 'expiring', field: 'expiring_soon' },
  { key: 'expired', field: 'expired' }, { key: 'revoked', field: 'revoked' },
]
const R = 58
const STROKE = 16
const C = 2 * Math.PI * R

function percent(value, total, lang) {
  if (!(total > 0)) return '–'
  const share = value / total
  if (share > 0 && share < 0.01) return '<1%'
  try { return new Intl.NumberFormat(lang, { style: 'percent', maximumFractionDigits: 0 }).format(share) } catch { return `${Math.round(share * 100)}%` }
}

export function StatesCard() {
  const { t } = useTranslation()
  const lang = useLang()
  const state = useCardData(() => dashboardService.getStats(), ['certificate'], 'stats')
  const data = state.data || {}
  const parts = STATES.map((s) => ({ key: s.key, value: Number(data[s.field]) || 0 }))
  const sum = parts.reduce((total, p) => total + p.value, 0)
  const label = (key) => t(`overview.filterValue.${key}`)
  const alt = t('overview.states.alt', Object.fromEntries([['total', sum], ...parts.map((p) => [p.key, p.value])]))

  return (
    <CardFrame id="states" title={t('overview.cards.states')} state={state} onRetry={state.reload}
      empty={state.status === 'ready' && sum === 0} sub={t('overview.states.sub')}>
      <div className="ov-body ov-donut-wrap">
        <div className="ov-donut">
          <svg viewBox="0 0 148 148" role="img" aria-label={alt} data-testid="states-donut">
            <circle className="ov-donut-track" cx="74" cy="74" r={R} strokeWidth={STROKE} />
            <g transform="rotate(-90 74 74)">
              {donutSlices(parts, C).map((slice) => (
                <circle key={slice.key} className="ov-donut-seg" data-series={slice.key} cx="74" cy="74" r={R}
                  strokeWidth={STROKE} strokeDasharray={`${slice.length.toFixed(2)} ${(C - slice.length).toFixed(2)}`}
                  strokeDashoffset={(-slice.offset).toFixed(2)}>
                  <title>{`${label(slice.key)}: ${slice.value}`}</title>
                </circle>
              ))}
            </g>
          </svg>
          <div className="ov-donut-total"><strong>{num(sum)}</strong><small>{t('common.total')}</small></div>
        </div>
        <ul className="ov-donut-legend">
          {parts.map((p) => (
            <li key={p.key}>
              <Link to={`/certificates?status=${p.key}`}>
                <i className="ov-swatch" data-series={p.key} aria-hidden="true" />
                <span>{label(p.key)}</span>
                <strong>{p.value}</strong>
                <small>{percent(p.value, sum, lang)}</small>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </CardFrame>
  )
}
