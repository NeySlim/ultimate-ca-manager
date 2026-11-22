/** Figures the overview widgets draw, computed from the /dashboard/* answers (no request here). */

// One request each, shared by the strip and the cards: the health card's 30 days (the strip reads
// the last 14), the strip's 30 days of issuance (the hierarchy counts the last 7)
export const HEALTH_DAYS = 30
export const ISSUANCE_DAYS = 30

const n = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : Number(v) || 0)

/** A daily series read as the strip writes it: today, its gap with yesterday, the mean, the latest peak. */
export function seriesStats(values) {
  if (!Array.isArray(values) || values.length === 0) return null
  const v = values.map(n)
  const sum = v.reduce((a, b) => a + b, 0)
  const max = Math.max(...v)
  const today = v[v.length - 1]
  const yesterday = v.length > 1 ? v[v.length - 2] : null
  return {
    sum, today, yesterday, delta: yesterday === null ? null : today - yesterday,
    mean: Math.round((sum / v.length) * 10) / 10, max, maxIndex: v.lastIndexOf(max),
  }
}

function daysBack(to, count) {
  const end = Date.parse(`${to}T00:00:00Z`)
  if (Number.isNaN(end)) return null
  return Array.from({ length: count }, (_, i) => new Date(end - (count - 1 - i) * 86400000).toISOString().slice(0, 10))
}

/** Certificates issued per UTC day, every CA together, from GET /dashboard/issuance; null without per-CA series. */
export function issuedPerDay(data) {
  const byCa = data?.by_ca
  if (!Array.isArray(byCa)) return null
  const first = byCa.find((e) => Array.isArray(e?.periods) && e.periods.length > 0)
  const dates = first ? first.periods.map((p) => p.date) : daysBack(data.to, n(data.days))
  if (!dates || dates.length === 0) return null
  const index = new Map(dates.map((d, i) => [d, i]))
  const values = dates.map(() => 0)
  for (const entry of byCa) {
    for (const p of Array.isArray(entry?.periods) ? entry.periods : []) {
      if (index.has(p.date)) values[index.get(p.date)] += n(p.issued)
    }
  }
  return { dates, values }
}

/** Issued and renewed of one CA over its last `days` periods; without periods, the window's own total. */
export function recentTotal(entry, days) {
  if (Array.isArray(entry?.periods) && entry.periods.length > 0) {
    return entry.periods.slice(-days).reduce((sum, p) => sum + n(p.issued) + n(p.renewed), 0)
  }
  return entry?.total ?? entry?.issued
}

/** Protocol failures per UTC day, the protocols added, over the last `days`; null when none has a series. */
export function failuresPerDay(protocols, names, days) {
  const series = names.map((p) => protocols?.[p]?.periods).filter((s) => Array.isArray(s) && s.length > 0)
  if (series.length === 0) return null
  const length = Math.min(days, Math.max(...series.map((s) => s.length)))
  return Array.from({ length }, (_, i) => series.reduce((sum, s) => sum + n(s[s.length - length + i]?.failed), 0))
}

/** Activité on one UTC day's failed ACME operations: the series of the card is the audit trail's acme.* entries. */
export const failuresHref = (date) => `/audit?${new URLSearchParams({ type: 'acme', success: 'false', date_from: date, date_to: date })}`

/** Share of successful operations in percent, one decimal, rounded down so that one failure never reads 100 %. */
export function successRate(ok, failed) {
  const total = n(ok) + n(failed)
  if (total === 0) return null
  return Math.floor((n(ok) / total) * 1000) / 10
}

// A plain count, not a weakness: drawn in the neutral grey whatever its figure
export const NEUTRAL_RULES = ['no_private_key']

/** Conforming share of a rule in whole percent, rounded down while one certificate is in gap; null when unknown. */
export function rulePercent(count, total) {
  if (typeof count !== 'number' || !Number.isFinite(count) || !(total > 0)) return null
  if (count <= 0) return 100
  return Math.max(0, Math.floor(((total - count) / total) * 100))
}

/** good: no gap; warn: 90 % and more conform; bad: a major gap; info: a plain count; '' when unknown. */
export function ruleTone(name, count, total) {
  if (NEUTRAL_RULES.includes(name)) return 'info'
  const pct = rulePercent(count, total)
  if (pct === null) return ''
  if (count <= 0) return 'good'
  return pct >= 90 ? 'warn' : 'bad'
}

// The server's GRADE_THRESHOLDS (services/compliance_service.py), applied to the average score
const GRADES = [[95, 'A+'], [85, 'A'], [70, 'B'], [55, 'C'], [40, 'D'], [0, 'F']]
export const GRADE_ORDER = GRADES.map(([, g]) => g)

export function gradeOfScore(score) {
  if (typeof score !== 'number' || !Number.isFinite(score)) return null
  return GRADES.find(([min]) => score >= min)[1]
}

// Successful sign-ins: the noise of the trail, folded when one user repeats them
const FOLDED = ['login_success']

/**
 * The latest entries, newest first, with each run of successive successful sign-ins of one user folded
 * into `{folded: true, count, user, action, first, last, entries}`; any other entry is `{folded: false, entry}`.
 */
export function foldActivity(rows) {
  const out = []
  for (const entry of Array.isArray(rows) ? rows : []) {
    const prev = out[out.length - 1]
    const foldable = FOLDED.includes(entry?.action)
    const same = prev && foldable && (prev.folded ? prev : prev.entry).action === entry.action
      && (prev.folded ? prev.user : prev.entry.user) === entry.user
    if (!same) { out.push({ folded: false, entry }); continue }
    if (!prev.folded) {
      out[out.length - 1] = { folded: true, count: 1, user: prev.entry.user, action: prev.entry.action,
        last: prev.entry.timestamp, first: prev.entry.timestamp, entries: [prev.entry] }
    }
    const run = out[out.length - 1]
    run.count += 1
    run.first = entry.timestamp
    run.entries.push(entry)
  }
  return out
}

// A text cell starting with one of these runs as a formula in a spreadsheet (CSV injection)
const FORMULA = /^[=+\-@\t\r]/

function cell(value) {
  if (value === null || value === undefined) return ''
  let text = String(value)
  if (typeof value === 'string' && FORMULA.test(text)) text = `'${text}`
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

/** RFC 4180 text of a table: a header line, then one CRLF-ended line per row. */
export function toCsv(columns, rows) {
  return [columns, ...rows].map((r) => `${r.map(cell).join(',')}\r\n`).join('')
}
