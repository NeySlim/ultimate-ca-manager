/**
 * Certificates issued, revoked and expired per day (GET /dashboard/certificate-trend): a card of
 * the product the mockup has not, in its card() with the mockup's segmented period and legend.
 */
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { dashboardService } from '../../services'
import { monotonePath, niceMax, tickIndexes } from '../../lib/overviewChart'
import { OverviewCard, useCardData, useLang } from './shared'
import { EmptyLine } from './viz'

const TREND_PERIODS = [7, 15, 30]
const SERIES = ['issued', 'revoked', 'expired']
// A second signal beside the colour: each series keeps its own line pattern
const DASH = { issued: undefined, revoked: '7 5', expired: '2 5' }
// Drawn at the size it is shown: one unit is one pixel, so the axis text keeps the size of the page's text
const WIDTH = 560
const H = 210
const PAD = { left: 34, right: 10, top: 12, bottom: 26 }

const value = (v) => (typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : 0)

function dayLabel(date, lang, short) {
  const at = new Date(`${date}T00:00:00Z`)
  if (Number.isNaN(at.getTime())) return date
  const options = short ? { weekday: 'short', timeZone: 'UTC' } : { day: 'numeric', month: 'short', timeZone: 'UTC' }
  try { return new Intl.DateTimeFormat(lang, options).format(at) } catch { return date }
}

function Key({ series }) {
  return (
    <svg className="trend-key" viewBox="0 0 18 10" data-series={series} aria-hidden="true">
      <line x1="1" x2="17" y1="5" y2="5" strokeDasharray={DASH[series]} />
    </svg>
  )
}

function useWidth() {
  const ref = useRef(null)
  const [width, setWidth] = useState(WIDTH)
  useEffect(() => {
    const el = ref.current
    if (!el || typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(() => { if (el.clientWidth > 0) setWidth(Math.round(el.clientWidth)) })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  return [ref, width]
}

function Chart({ trend, labels, lang, alt, hint }) {
  const [at, setAt] = useState(null)
  const [frame, W] = useWidth()
  const n = trend.length
  const top = niceMax(Math.max(...trend.flatMap((d) => SERIES.map((s) => value(d[s])))))
  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom
  const x = (i) => PAD.left + (n > 1 ? (i * innerW) / (n - 1) : innerW / 2)
  const y = (v) => PAD.top + innerH - (v / top) * innerH
  const points = (s) => trend.map((d, i) => [x(i), y(value(d[s]))])
  const base = PAD.top + innerH
  const area = n > 1 ? `${monotonePath(points('issued'))}L${x(n - 1)},${base}L${x(0)},${base}Z` : ''
  const nearest = (clientX, box) => {
    if (!box.width) return 0
    const px = ((clientX - box.left) / box.width) * W
    return Math.min(n - 1, Math.max(0, Math.round(((px - PAD.left) / innerW) * (n - 1))))
  }
  const onKeyDown = (e) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
    e.preventDefault()
    const from = at === null ? (e.key === 'ArrowLeft' ? n : -1) : at
    setAt(Math.min(n - 1, Math.max(0, from + (e.key === 'ArrowRight' ? 1 : -1))))
  }
  const day = at === null ? null : trend[at]

  return (
    // The arrow keys read the chart day by day, as the pointer does
    <div className="trend-chart" ref={frame} tabIndex={0} role="group" aria-label={hint} onKeyDown={onKeyDown} onBlur={() => setAt(null)}
      onPointerMove={(e) => setAt(nearest(e.clientX, e.currentTarget.querySelector('svg').getBoundingClientRect()))}
      onPointerLeave={() => setAt(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} height={H} role="img" aria-label={alt} data-testid="trend-chart">
        {[0, 0.5, 1].map((k) => (
          <g key={k}>
            <line className="trend-grid" x1={PAD.left} x2={W - PAD.right} y1={y(top * k)} y2={y(top * k)} />
            <text className="trend-axis" x={PAD.left - 8} y={y(top * k) + 4} textAnchor="end">{top * k}</text>
          </g>
        ))}
        {tickIndexes(n, n <= 7 ? 7 : 5).map((i) => (
          <text key={trend[i].date} className="trend-axis" x={x(i)} y={H - 6}
            textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'}>
            {dayLabel(trend[i].date, lang, n <= 7)}
          </text>
        ))}
        {area && <path className="trend-area" data-series="issued" d={area} />}
        {SERIES.map((s) => (
          <path key={s} className="trend-series" data-series={s} data-testid={`trend-line-${s}`} strokeDasharray={DASH[s]}
            d={monotonePath(points(s))} />
        ))}
        {at !== null && (
          <g>
            <line className="trend-cross" x1={x(at)} x2={x(at)} y1={PAD.top} y2={base} />
            {SERIES.map((s) => (
              <circle key={s} className="trend-dot" data-series={s} cx={x(at)} cy={y(value(day[s]))} r="4.5" />
            ))}
          </g>
        )}
      </svg>
      {day && (
        <div className="trend-tip" aria-live="polite" data-testid="trend-tip"
          style={at > (n - 1) / 2 ? { right: `${100 - (x(at) / W) * 100 + 2}%` } : { left: `${(x(at) / W) * 100 + 2}%` }}>
          <strong>{dayLabel(day.date, lang, false)}</strong>
          {SERIES.map((s) => (
            <span key={s}><Key series={s} />{labels[s]}<b>{value(day[s])}</b></span>
          ))}
        </div>
      )}
    </div>
  )
}

export function TrendCard() {
  const { t } = useTranslation()
  const lang = useLang()
  const [days, setDays] = useState(TREND_PERIODS[0])
  const state = useCardData(() => dashboardService.getCertificateTrend(days), ['certificate'])
  const first = useRef(true)
  const { refresh } = state
  // The figures stay on screen while the other period loads
  useEffect(() => {
    if (first.current) { first.current = false; return }
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days])

  const trend = Array.isArray(state.data?.trend) ? state.data.trend : []
  const totals = Object.fromEntries(SERIES.map((s) => [s, trend.reduce((sum, d) => sum + value(d[s]), 0)]))
  const labels = { issued: t('common.issued'), revoked: t('common.revoked'), expired: t('common.expired') }
  const quiet = SERIES.every((s) => totals[s] === 0)
  const alt = t('overview.trend.alt', { count: trend.length, ...totals })

  return (
    <OverviewCard id="trend" state={state} route="GET /api/v2/dashboard/certificate-trend"
      sub={t('overview.trend.sub', { count: days })}
      empty={state.status === 'ready' && quiet && (
        <div className="panel-content"><EmptyLine text={t('overview.trend.quiet', { count: days })} /></div>
      )}
      tools={(
        <div className="segmented" role="group" aria-label={t('overview.trend.period')}>
          {TREND_PERIODS.map((d) => (
            <button key={d} type="button" id={`trend-${d}`} aria-pressed={days === d} onClick={() => setDays(d)}
              aria-label={t('overview.days', { count: d })}>
              {t('overview.trend.short', { count: d })}
            </button>
          ))}
        </div>
      )}>
      <div className="panel-content">
        <ul className="horizon-legend">
          {SERIES.map((s) => (
            <li key={s}><Key series={s} />{labels[s]}<strong>{totals[s]}</strong></li>
          ))}
        </ul>
        <Chart trend={trend} labels={labels} lang={lang} alt={alt} hint={t('overview.trend.keys')} />
        {/* A table ignores overflow: the hidden box is a div, or its cells widen the page on a phone */}
        <div className="sr-only"><table>
          <caption>{alt}</caption>
          <thead>
            <tr><th scope="col">{t('overview.trend.day')}</th>{SERIES.map((s) => <th key={s} scope="col">{labels[s]}</th>)}</tr>
          </thead>
          <tbody>
            {trend.map((d) => (
              <tr key={d.date}><th scope="row">{d.date}</th>{SERIES.map((s) => <td key={s}>{value(d[s])}</td>)}</tr>
            ))}
          </tbody>
        </table></div>
      </div>
    </OverviewCard>
  )
}
