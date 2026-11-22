/**
 * The expiry horizon and the issuance flow of the overview, laid out from GET /dashboard/expirations
 * and the `flow` of GET /dashboard/issuance (no request here). Every date is a UTC day, YYYY-MM-DD.
 */

const DAY = 86400000
const n = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : Number(v) || 0)
const ms = (date) => Date.parse(`${date}T00:00:00Z`)
const iso = (t) => new Date(t).toISOString().slice(0, 10)

/** The day after `date`: the exclusive bound of a list filter that ends on `date`. */
export const nextDay = (date) => iso(ms(date) + DAY)

// The horizon's choices: weeks shown, the label naming them in days
export const HORIZONS = [{ days: 30, weeks: 5 }, { days: 90, weeks: 13 }, { days: 365, weeks: 52 }]

/** Monday-first index of a UTC day (Monday 0, Sunday 6). */
export const weekday = (date) => (new Date(ms(date)).getUTCDay() + 6) % 7

/**
 * The days to ask from `today` so that the window ends on the Sunday of its `weeks`-th week, the
 * current week counting as the first: the calendar then has exactly `weeks` full columns.
 */
export function horizonDays(weeks, today) {
  return weeks * 7 - weekday(today)
}

/**
 * The calendar of the expirations: one column per Monday-first UTC week from the week of `from`,
 * seven days each. A day before `from` or after the last period is outside the window (`out`, no
 * figure). Each week sums its days in the window; `from`/`to` are its first and last day in it.
 */
export function expiryCalendar(periods, from) {
  const list = Array.isArray(periods) ? periods : []
  const start = from || list[0]?.date
  if (!start || Number.isNaN(ms(start))) return []
  const byDate = new Map(list.map((p) => [p.date, p]))
  const last = list.length > 0 ? list[list.length - 1].date : start
  const monday = ms(start) - weekday(start) * DAY
  const count = Math.max(1, Math.ceil((ms(last) - monday + DAY) / (7 * DAY)))
  return Array.from({ length: count }, (_, w) => {
    const days = Array.from({ length: 7 }, (__, d) => {
      const date = iso(monday + (w * 7 + d) * DAY)
      const p = byDate.get(date)
      if (!p) return { date, out: true, total: 0, manual: 0, automatic: 0, cas: 0, signers: 0 }
      return { date, out: false, total: n(p.total), manual: n(p.manual), automatic: n(p.automatic), cas: n(p.cas),
        signers: n(p.signers), infrastructure: Boolean(p.infrastructure) || n(p.cas) > 0 || n(p.signers) > 0 }
    })
    const inside = days.filter((d) => !d.out)
    const sum = (k) => inside.reduce((s, d) => s + d[k], 0)
    return { start: days[0].date, from: inside[0]?.date ?? null, to: inside.at(-1)?.date ?? null, days,
      total: sum('total'), manual: sum('manual'), automatic: sum('automatic'), cas: sum('cas'), signers: sum('signers') }
  })
}

/** Five steps of the heat ramp: 0 for nothing, then quarters of the busiest day (at least one step per expiry). */
export function heatLevel(count, max) {
  const v = n(count)
  if (v <= 0) return 0
  if (!(max > 0)) return 1
  return Math.min(4, Math.max(1, Math.ceil((v / max) * 4)))
}

// The overview's sources in the stacking order, their group of the flow and their colour; the hatched
// ones share a colour with a neighbour, the hatching tells them apart (colour is never alone)
export const FLOW_SERIES = [
  { key: 'acme', color: 'var(--s1)' },
  { key: 'scep', color: 'var(--s2)' },
  { key: 'est', color: 'var(--s3)' },
  { key: 'wstep', color: 'var(--s3)', hatch: true },
  { key: 'import', color: 'var(--s0)', hatch: true },
  { key: 'manual', color: 'var(--s0)' },
]
export const AUTOMATIC_GROUPS = ['acme', 'scep', 'est', 'wstep']

/**
 * The flow drawn as stacked columns: per day the segments bottom-up `[{key, from, value}]` in the
 * order above, the day's total, the window's totals per group, the gap with the previous window
 * (a share, null without a previous total) and the automated share in whole percent.
 */
export function flowColumns(flow) {
  const periods = Array.isArray(flow?.periods) ? flow.periods : []
  const days = periods.map((p) => {
    let acc = 0
    const segments = []
    for (const s of FLOW_SERIES) {
      const value = n(p[s.key])
      if (value > 0) segments.push({ key: s.key, from: acc, value })
      acc += value
    }
    return { date: p.date, total: acc, segments, values: Object.fromEntries(FLOW_SERIES.map((s) => [s.key, n(p[s.key])])) }
  })
  const totals = Object.fromEntries(FLOW_SERIES.map((s) => [s.key, days.reduce((sum, d) => sum + d.values[s.key], 0)]))
  const total = days.reduce((sum, d) => sum + d.total, 0)
  const previous = n(flow?.previous?.total)
  const automatic = AUTOMATIC_GROUPS.reduce((sum, k) => sum + totals[k], 0)
  return {
    days, totals, total, max: Math.max(0, ...days.map((d) => d.total)),
    trend: previous > 0 ? (total - previous) / previous : null,
    automaticShare: total > 0 ? Math.round((automatic / total) * 100) : null,
  }
}

/** A round top for an axis of columns: 4 steps of a whole number, at least 4. */
export function axisTop(max) {
  const v = Math.max(4, n(max))
  return Math.ceil(v / 4) * 4
}
