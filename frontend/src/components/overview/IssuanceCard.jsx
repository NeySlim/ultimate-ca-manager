/**
 * Issuances by source (maquette-3) over the `flow` of GET /dashboard/issuance: one stacked column per
 * UTC day (ACME, SCEP, EST, WSTEP, import, manual), one axis, the peak labelled, the window's total with
 * its gap to the previous window and its automated share. A day opens Certificates created that day.
 */
import { useContext, useEffect, useId, useRef, useState } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { Icon } from '../atelier'
import { overviewService } from '../../services'
import { usePermission } from '../../hooks/usePermission'
import { listHref } from '../../lib/overviewFilters'
import { FLOW_SERIES, axisTop, flowColumns, nextDay } from '../../lib/overviewHorizon'
import { ISSUANCE_DAYS } from '../../lib/overviewViz'
import { OverviewCard, OverviewContext, useCardData, useLang } from './shared'
import { SeriesFrame } from './viz'

const PERIODS = [7, 30, 90]
const H = 230
const PAD = { left: 30, right: 8, top: 18, bottom: 24 }
const domId = (raw) => `f${String(raw).replace(/[^a-zA-Z0-9_-]/g, '')}`

function dayLabel(date, lang) {
  try { return new Intl.DateTimeFormat(lang, { day: 'numeric', month: 'short', timeZone: 'UTC' }).format(new Date(`${date}T00:00:00Z`)) } catch { return date }
}

// A callback ref: the frame appears only once the card has loaded, after the first render
function useWidth(initial) {
  const [el, setEl] = useState(null)
  const [width, setWidth] = useState(initial)
  useEffect(() => {
    if (!el || typeof ResizeObserver === 'undefined') return undefined
    const measure = () => { if (el.clientWidth > 0) setWidth(Math.round(el.clientWidth)) }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => observer.disconnect()
  }, [el])
  return [setEl, width]
}

// Room a dated tick leaves to the right-aligned « today » label, so the two never overlap on a narrow card
const TODAY_ROOM = 90

/** The fill of a series: its colour, or its hatching over that colour. */
const paint = (s, ids) => (s.hatch ? `url(#${ids[s.key]})` : s.color)

export function IssuanceCard() {
  const { t } = useTranslation()
  const lang = useLang()
  const navigate = useNavigate()
  const page = useContext(OverviewContext)
  const { hasPermission } = usePermission()
  const [days, setDays] = useState(ISSUANCE_DAYS)
  // The strip and the hierarchy read the same 30 days: one request for the three
  const fetcher = () => (days === ISSUANCE_DAYS && page?.share
    ? page.share('issuance', () => overviewService.getIssuance(ISSUANCE_DAYS)) : overviewService.getIssuance(days))
  const state = useCardData(fetcher, ['certificate', 'ca'])
  const first = useRef(true)
  const { refresh } = state
  // The figures stay on screen while the other period loads
  useEffect(() => {
    if (first.current) { first.current = false; return }
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days])

  const flow = state.data?.flow
  const f = flowColumns(flow)
  const [frame, W] = useWidth(560)
  const base = domId(useId())
  const ids = Object.fromEntries(FLOW_SERIES.filter((s) => s.hatch).map((s) => [s.key, `${base}-${s.key}`]))
  const n = f.days.length
  const top = axisTop(f.max)
  const innerW = Math.max(1, W - PAD.left - PAD.right)
  const innerH = H - PAD.top - PAD.bottom
  const slot = innerW / Math.max(1, n)
  const bw = Math.max(2, Math.min(14, slot - 3))
  const y = (v) => PAD.top + innerH - (v / top) * innerH
  const peak = f.max > 0 ? f.days.findIndex((d) => d.total === f.max) : -1
  const name = (key) => t(`overview.flow.series.${key}`)
  const listable = hasPermission('read:certificates')
  const open = (i) => {
    const d = f.days[i]
    if (!d || !listable) return
    navigate(listHref({ created_from: d.date, created_to: nextDay(d.date) }))
  }
  // A series of the legend: the four the mockup names always, WSTEP and import once they count
  const legend = FLOW_SERIES.filter((s) => !s.hatch || f.totals[s.key] > 0)
  const tickEvery = n <= 7 ? 1 : 7
  const trend = f.trend === null ? null : Math.round(f.trend * 100)

  const table = () => [{
    caption: t('overview.flow.tableCaption', { count: n }),
    columns: [t('overview.trend.day'), ...FLOW_SERIES.map((s) => name(s.key)), t('overview.horizon.total')],
    rows: f.days.map((d) => [d.date, ...FLOW_SERIES.map((s) => d.values[s.key]), d.total]),
  }]

  return (
    <OverviewCard id="issuance" state={state} route="GET /api/v2/dashboard/issuance" table={flow ? table : undefined}
      sub={t('overview.flow.sub', { count: days })}
      empty={state.status === 'ready' && f.total === 0 && (
        <div className="panel-content"><p className="empty-line" role="status"><Icon name="check" /><span>{t('overview.flow.quiet', { count: days })}</span></p></div>
      )}
      tools={(
        <div className="segmented" role="group" aria-label={t('overview.trend.period')}>
          {PERIODS.map((d) => (
            <button key={d} type="button" id={`flow-${d}`} aria-pressed={days === d} onClick={() => setDays(d)}
              aria-label={t('overview.days', { count: d })}>
              {t('overview.trend.short', { count: d })}
            </button>
          ))}
        </div>
      )}>
      <div className="panel-content">
        <div className="flow-head">
          <Trans i18nKey="overview.flow.issuances" count={f.total}
            components={[<span key="fig" className="fig" data-total={f.total} />, <span key="word" className="muted" />]} />
          <span className="muted">
            {trend !== null && (
              <>{' · '}<span className={`delta ${trend > 0 ? 'good' : trend < 0 ? 'bad' : 'muted'}`} data-trend={trend}>
                {trend !== 0 && <Icon name={trend > 0 ? 'up' : 'down'} />}{trend > 0 ? `+ ${trend} %` : trend < 0 ? `− ${-trend} %` : '0 %'}
              </span>{' '}{t('overview.flow.vsPrevious', { count: days })}</>
            )}
            {f.automaticShare !== null && <>{' · '}{t('overview.flow.automatic', { pct: f.automaticShare })}</>}
          </span>
        </div>
        <div ref={frame}>
          <SeriesFrame className="flow-frame" count={n}
            label={t('overview.flow.alt', { count: n, max: f.max, date: peak >= 0 ? dayLabel(f.days[peak].date, lang) : '' })}
            onPick={listable ? open : undefined}
            tipModel={(i) => ({
              title: dayLabel(f.days[i].date, lang),
              rows: [{ label: t('overview.horizon.total'), value: f.days[i].total },
                ...legend.map((s) => ({ label: name(s.key), value: f.days[i].values[s.key], color: s.color }))],
              hint: listable && f.days[i].total > 0 ? t('overview.flow.openDay') : null,
            })}>
            {({ at, ref, enter }) => (
              <svg className="flow" viewBox={`0 0 ${W} ${H}`} height={H} aria-hidden="true" data-testid="flow-chart">
                <defs>
                  {FLOW_SERIES.filter((s) => s.hatch).map((s) => (
                    <pattern key={s.key} id={ids[s.key]} width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                      <rect width="5" height="5" style={{ fill: s.color }} />
                      <line x1="0" y1="0" x2="0" y2="5" className="hatch-line" />
                    </pattern>
                  ))}
                </defs>
                {[0, 1, 2, 3, 4].map((g) => (
                  <g key={g}>
                    <line className={g ? 'gridline' : 'axisline'} x1={PAD.left} x2={W - PAD.right} y1={y((top / 4) * g)} y2={y((top / 4) * g)} />
                    <text x={PAD.left - 8} y={y((top / 4) * g) + 4} textAnchor="end">{(top / 4) * g}</text>
                  </g>
                ))}
                {at !== null && <line className="cross" x1={PAD.left + at * slot + slot / 2} x2={PAD.left + at * slot + slot / 2} y1={PAD.top} y2={PAD.top + innerH} />}
                {f.days.map((d, i) => {
                  const x = PAD.left + i * slot + (slot - bw) / 2
                  return (
                    <g key={d.date} ref={ref(i)} data-day={d.date} data-total={d.total} className={at === i ? 'col on' : 'col'}
                      onPointerEnter={enter(i)} onClick={listable ? () => open(i) : undefined}>
                      <rect className="hit" x={PAD.left + i * slot} y={PAD.top} width={slot} height={innerH} />
                      {d.segments.map((sg, k) => {
                        const s = FLOW_SERIES.find((x2) => x2.key === sg.key)
                        const y1 = y(sg.from + sg.value)
                        const h = Math.max(1, y(sg.from) - y1 - (k < d.segments.length - 1 ? 2 : 0))
                        return <rect key={sg.key} data-series={sg.key} className={sg.key === 'acme' ? 'col1' : undefined} x={x} y={y1} width={bw} height={h}
                          rx={k === d.segments.length - 1 ? 2 : 0} style={{ fill: paint(s, ids) }} />
                      })}
                      {i === peak && <text className="lab" x={x + bw / 2} y={y(d.total) - 6} textAnchor="middle">{d.total}</text>}
                      {(i === n - 1 || ((n - 1 - i) % tickEvery === 0 && (n <= 7 || (n - 1 - i) * slot >= TODAY_ROOM))) && (
                        <text x={x + bw / 2} y={H - 6} textAnchor={i === n - 1 ? 'end' : 'middle'}>
                          {i === n - 1 ? t('overview.activity.today') : dayLabel(d.date, lang)}
                        </text>
                      )}
                    </g>
                  )
                })}
              </svg>
            )}
          </SeriesFrame>
        </div>
        <ul className="legend flow-legend">
          {legend.map((s) => (
            <li key={s.key} data-series={s.key}>
              <i className={s.hatch ? 'swatch hatch' : 'swatch'} style={{ '--swatch': s.color }} />
              {name(s.key)}<b>{f.totals[s.key].toLocaleString(lang)}</b>
            </li>
          ))}
        </ul>
      </div>
    </OverviewCard>
  )
}
