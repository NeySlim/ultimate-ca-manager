/**
 * The expiry horizon (maquette-2) over GET /dashboard/expirations: the weekly columns of the Atelier
 * mockup, manual under automatic, on a calendar of the same weeks (one cell per UTC day, denser is
 * busier, a diamond where an authority or a signer expires). A day or a week fills the side list,
 * which opens Certificates on exactly that interval (`expires_from`, `expires_to`).
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Icon } from '../atelier'
import { certificatesService, overviewService } from '../../services'
import { usePermission } from '../../hooks/usePermission'
import { listHref } from '../../lib/overviewFilters'
import { HORIZONS, expiryCalendar, heatLevel, horizonDays } from '../../lib/overviewHorizon'
import { extractCN } from '../../lib/utils'
import { sourceLabel, sourceOf } from '../../pages/certificates/certificateSources'
import { OverviewCard, SEP, useCardData, useLang } from './shared'
import { useChartTip } from './viz'

const SIDE_ROWS = 5
const DAY = 86400000
const utcToday = () => new Date().toISOString().slice(0, 10)

function fmt(date, lang, options) {
  try { return new Intl.DateTimeFormat(lang, { timeZone: 'UTC', ...options }).format(new Date(`${date}T00:00:00Z`)) } catch { return date }
}

/** The busiest day of the window, the earliest of equals; null when nothing expires. */
function busiest(weeks) {
  let best = null
  for (const w of weeks) for (const d of w.days) if (!d.out && d.total > 0 && (!best || d.total > best.total)) best = d
  return best
}

/** The certificates of the chosen interval, the soonest first, and the link to all of them. */
function SideList({ query, count, automatic, t }) {
  const { hasPermission } = usePermission()
  const allowed = hasPermission('read:certificates')
  const [rows, setRows] = useState(null)
  const key = JSON.stringify(query)
  useEffect(() => {
    if (!allowed || count === 0) { setRows([]); return undefined }
    let live = true
    setRows(null)
    certificatesService.getAll({ ...query, per_page: SIDE_ROWS, sort_by: 'valid_to', sort_order: 'asc' })
      .then((res) => { if (live) setRows(Array.isArray(res?.data) ? res.data : []) })
      .catch(() => { if (live) setRows([]) })
    return () => { live = false }
  }, [key, allowed, count]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <>
      {rows && rows.length > 0 && (
        <ul className="side-list" aria-label={t('overview.horizon.listLabel')}>
          {rows.map((c) => {
            const source = sourceOf(c)
            return (
              <li key={c.id}>
                <Link to={`/certificates/${c.id}`}>{c.common_name || c.cn || c.descr || `#${c.id}`}</Link>
                <span className={automatic.includes(source) ? 'chip' : 'chip warn'}>{sourceLabel(source, t)}</span>
                <small>{extractCN(c.issuer) || c.issuer || '–'}</small>
              </li>
            )
          })}
        </ul>
      )}
      {allowed && count > 0 && (
        <p className="side-open">
          <Link className="text-link" data-action="open-expiring" to={listHref(query)}>
            {t('overview.horizon.open', { count })} <Icon name="right" />
          </Link>
        </p>
      )}
    </>
  )
}

/** Arrow keys move the focus over a set of buttons kept in `els` (roving focus: one tab stop). */
function rove(e, els, index, step) {
  const moves = { ArrowLeft: -step.x, ArrowRight: step.x, ArrowUp: -step.y, ArrowDown: step.y }
  let next = null
  if (e.key in moves) next = index + moves[e.key]
  else if (e.key === 'Home') next = 0
  else if (e.key === 'End') next = els.length - 1
  if (next === null) return
  e.preventDefault()
  // A move off the edge or onto a day outside the window stays where it is
  if (next >= 0 && next < els.length && els[next]) els[next].focus()
}

export function HorizonCard() {
  const { t } = useTranslation()
  const lang = useLang()
  const tip = useChartTip()
  const [choice, setChoice] = useState(1)
  const weeksAsked = HORIZONS[choice].weeks
  const state = useCardData(() => overviewService.getExpirations(horizonDays(weeksAsked, utcToday())), ['certificate', 'ca'])
  const first = useRef(true)
  const { refresh } = state
  // The figures stay on screen while the other horizon loads
  useEffect(() => {
    if (first.current) { first.current = false; return }
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [choice])

  const data = state.data || {}
  const weeks = useMemo(() => expiryCalendar(data.periods, data.from), [data.periods, data.from])
  const dayMax = Math.max(0, ...weeks.flatMap((w) => w.days.map((d) => d.total)))
  const weekMax = Math.max(0, ...weeks.map((w) => w.total))
  const peak = weekMax > 0 ? weeks.findIndex((w) => w.total === weekMax) : -1
  const automatic = Array.isArray(data.automatic_sources) ? data.automatic_sources : []
  const [picked, setPicked] = useState(null)
  // The pick of an earlier horizon that is no longer drawn falls back to the busiest day
  const days = weeks.flatMap((w) => w.days)
  const pickedDay = picked?.kind === 'day' ? days.find((d) => d.date === picked.date && !d.out) : null
  const pickedWeek = picked?.kind === 'week' ? weeks.find((w) => w.start === picked.start && w.from) : null
  const fallback = busiest(weeks)
  const selection = pickedWeek ? { kind: 'week', week: pickedWeek } : (pickedDay || fallback) ? { kind: 'day', day: pickedDay || fallback } : null

  const dayCells = useRef([])
  const weekCells = useRef([])
  const today = data.from
  const longDay = (date) => fmt(date, lang, { weekday: 'long', day: 'numeric', month: 'long' })
  const weekName = (w) => t('overview.horizon.week', { date: fmt(w.from, lang, { day: 'numeric', month: 'long' }) })
  const dayLabel = (d) => [
    t('overview.horizon.dayAlt', { date: longDay(d.date), count: d.total }),
    d.cas > 0 ? t('overview.horizon.withCas', { count: d.cas }) : null,
    d.signers > 0 ? t('overview.horizon.withSigners', { count: d.signers }) : null,
  ].filter(Boolean).join(', ')
  const rows = (x) => [
    { label: t('overview.horizon.total'), value: x.total },
    { label: t('overview.horizon.manual'), value: x.manual, color: 'var(--warn-fill)' },
    { label: t('overview.horizon.automatic'), value: x.automatic, color: 'var(--s0)' },
    ...(x.cas > 0 ? [{ label: t('overview.horizon.cas'), value: x.cas }] : []),
    ...(x.signers > 0 ? [{ label: t('overview.horizon.signers'), value: x.signers }] : []),
  ]
  const query = (from, to) => overviewService.expirationQuery(data.filter_hint, from, to)

  // The column order is the calendar's: the tab stop is the selected cell, else the first of the window
  const flatDays = []
  weeks.forEach((w, wi) => w.days.forEach((d, di) => { flatDays[di * weeks.length + wi] = d }))
  const focusDate = selection?.kind === 'day' ? selection.day.date : days.find((d) => !d.out)?.date
  const months = weeks.map((w, i) => {
    const one = w.days.find((d) => d.date.endsWith('-01'))
    if (one) return fmt(one.date, lang, { month: 'short' })
    return i === 0 && !weeks[1]?.days.some((d) => d.date.endsWith('-01')) ? fmt(w.start, lang, { month: 'short' }) : ''
  })

  const table = () => [{
    caption: t('overview.horizon.tableCaption', { count: weeks.length }),
    columns: [t('overview.horizon.weekCol'), t('overview.horizon.total'), t('overview.horizon.manual'),
      t('overview.horizon.automatic'), t('overview.horizon.cas'), t('overview.horizon.signers')],
    rows: weeks.map((w) => [w.from, w.total, w.manual, w.automatic, w.cas, w.signers]),
  }]

  const total = typeof data.total === 'number' ? data.total : 0
  const side = () => {
    if (!selection) return <p className="muted small">{t('overview.horizon.nothing')}</p>
    const x = selection.kind === 'week' ? selection.week : selection.day
    const from = selection.kind === 'week' ? x.from : x.date
    const to = selection.kind === 'week' ? x.to : x.date
    const inDays = Math.round((Date.parse(`${from}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`)) / DAY)
    return (
      <>
        <div className="side-head">
          <span className="fig">{x.total}</span>
          <p>
            <b>{selection.kind === 'week' ? weekName(x) : longDay(x.date)}</b>
            {SEP}{inDays === 0 ? t('overview.activity.today') : t('overview.horizon.inDays', { count: inDays })}
          </p>
          <p className="side-chips">
            {x.manual > 0 && <span className="chip warn"><Icon name="warning" />{t('overview.horizon.toRenew', { count: x.manual })}</span>}
            {x.automatic > 0 && <span className="chip">{t('overview.horizon.automaticCount', { count: x.automatic })}</span>}
            {x.cas > 0 && <span className="chip warn"><i className="mark" aria-hidden="true" />{t('overview.horizon.casCount', { count: x.cas })}</span>}
          </p>
        </div>
        <SideList key={`${from}-${to}`} query={query(from, to)} count={x.total} automatic={automatic} t={t} />
      </>
    )
  }

  return (
    <OverviewCard id="horizon" state={state} route="GET /api/v2/dashboard/expirations" table={table}
      sub={data.to ? t('overview.horizon.subWindow', { count: total, date: fmt(data.to, lang, { day: 'numeric', month: 'long' }) }) : undefined}
      empty={state.status === 'ready' && total === 0 && weeks.every((w) => w.cas === 0) && (
        <div className="panel-content">
          <p className="empty-line" role="status"><Icon name="check" />
            <span>{t('overview.horizon.quiet', { date: data.to ? fmt(data.to, lang, { day: 'numeric', month: 'long' }) : '' })}</span>
          </p>
        </div>
      )}
      tools={(
        <div className="segmented" role="group" aria-label={t('overview.horizon.period')}>
          {HORIZONS.map((h, i) => (
            <button key={h.days} type="button" id={`horizon-${h.days}`} aria-pressed={choice === i} onClick={() => setChoice(i)}>
              {h.days === 365 ? t('overview.horizon.year') : t('overview.trend.short', { count: h.days })}
            </button>
          ))}
        </div>
      )}>
      <div className="hz">
        <div className="hz-main">
          <div className="cal" style={{ '--weeks': weeks.length }} data-weeks={weeks.length}>
            <span />
            {months.map((m, i) => <span key={`m${i}`} className="mon" aria-hidden="true">{m}</span>)}
            <span className="axis" aria-hidden="true"><span>{weekMax}</span><span>0</span></span>
            <div className="wk-row" role="group" aria-label={t('overview.horizon.weeksLabel')}>
              {weeks.map((w, i) => {
                const px = (v) => `${weekMax > 0 ? Math.round((v / weekMax) * 72) : 0}px`
                const active = selection?.kind === 'week' && selection.week.start === w.start
                return (
                  <button key={w.start} type="button" className="wk" data-week={w.start} aria-pressed={active}
                    ref={(el) => { weekCells.current[i] = el }} tabIndex={i === 0 ? 0 : -1}
                    aria-label={t('overview.horizon.weekAlt', { name: weekName(w), count: w.total, manual: w.manual, automatic: w.automatic })}
                    onClick={() => setPicked({ kind: 'week', start: w.start })}
                    onKeyDown={(e) => rove(e, weekCells.current, i, { x: 1, y: 0 })}
                    {...tip.bind({ title: weekName(w), rows: rows(w), hint: w.total ? t('overview.horizon.openWeek') : null })}>
                    {i === peak && <b>{w.total}</b>}
                    {w.automatic > 0 && <i className="auto" style={{ height: px(w.automatic) }} />}
                    {w.manual > 0 && <i className="manual" style={{ height: px(w.manual) }} />}
                  </button>
                )
              })}
            </div>
            <span className="gap" />
            <div className="day-grid" role="group" aria-label={t('overview.horizon.daysLabel')}>
              {[0, 1, 2, 3, 4, 5, 6].map((r) => (
                <div key={r} className="day-row">
                  <span className="dow" aria-hidden="true">
                    {r % 2 === 0 ? fmt(weeks[0]?.days[r].date || '2026-11-23', lang, { weekday: 'short' }) : ''}
                  </span>
                  {weeks.map((w, wi) => {
                    const d = w.days[r]
                    const index = r * weeks.length + wi
                    if (d.out) return <span key={d.date} className="day out" aria-hidden="true" />
                    const pressed = selection?.kind === 'day' && selection.day.date === d.date
                    return (
                      <button key={d.date} type="button" className={d.date === today ? 'day today' : 'day'} data-date={d.date}
                        data-l={heatLevel(d.total, dayMax)} aria-pressed={pressed} aria-label={dayLabel(d)}
                        ref={(el) => { dayCells.current[index] = el }} tabIndex={d.date === focusDate ? 0 : -1}
                        onClick={() => setPicked({ kind: 'day', date: d.date })}
                        onKeyDown={(e) => {
                          // Up and down move a day, left and right a week, Home and End to the ends of the window
                          const step = { ArrowUp: -1, ArrowDown: 1, ArrowLeft: -7, ArrowRight: 7 }[e.key]
                          const inside = days.filter((x) => !x.out)
                          let next = null
                          if (step !== undefined) next = new Date(Date.parse(`${d.date}T00:00:00Z`) + step * DAY).toISOString().slice(0, 10)
                          else if (e.key === 'Home') next = inside[0]?.date
                          else if (e.key === 'End') next = inside.at(-1)?.date
                          if (next === null) return
                          e.preventDefault()
                          const k = flatDays.findIndex((x) => x && !x.out && x.date === next)
                          if (k >= 0) dayCells.current[k]?.focus()
                        }}
                        {...tip.bind({ title: longDay(d.date), rows: rows(d), hint: d.total ? t('overview.horizon.openDay') : t('overview.horizon.nothingDay') })}>
                        {d.infrastructure && <i className="mark" />}
                      </button>
                    )
                  })}
                </div>
              ))}
            </div>
          </div>
          <div className="cal-foot">
            <ul className="legend">
              <li><i className="swatch manual" />{t('overview.horizon.legendManual')}</li>
              <li><i className="swatch auto" />{t('overview.horizon.legendAutomatic')}</li>
              <li><i className="swatch diamond" />{t('overview.horizon.legendInfra')}</li>
            </ul>
            <span className="scale" aria-hidden="true">
              {t('overview.horizon.less')} {[0, 1, 2, 3, 4].map((l) => <i key={l} data-l={l} />)} {t('overview.horizon.more')}
            </span>
          </div>
        </div>
        <aside className="hz-side" aria-live="polite" data-testid="horizon-side">{side()}</aside>
      </div>
      {tip.node}
    </OverviewCard>
  )
}
