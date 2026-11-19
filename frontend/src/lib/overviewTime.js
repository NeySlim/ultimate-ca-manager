/** Relative delays of the overview, written by the browser in the interface language. */
const MINUTE = 60000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

/** The largest unit that keeps the figure readable: minutes, hours up to 2 days, days up to 2 months, months, years. */
export function spanOf(ms) {
  const abs = Math.abs(ms)
  if (abs < HOUR) return { value: Math.max(1, Math.round(abs / MINUTE)), unit: 'minute' }
  if (abs < 48 * HOUR) return { value: Math.round(abs / HOUR), unit: 'hour' }
  if (abs < 60 * DAY) return { value: Math.floor(abs / DAY), unit: 'day' }
  if (abs < 730 * DAY) return { value: Math.floor(abs / (30.44 * DAY)), unit: 'month' }
  return { value: Math.floor(abs / (365.25 * DAY)), unit: 'year' }
}

const time = (date) => {
  if (typeof date === 'number') return date
  return date instanceof Date ? date.getTime() : Date.parse(date)
}

/** "in 12 days" or "3 hours ago"; null without a readable date. */
export function relativeTime(date, lang = 'en', now = Date.now()) {
  const at = time(date)
  if (!Number.isFinite(at)) return null
  const { value, unit } = spanOf(at - now)
  try {
    return new Intl.RelativeTimeFormat(lang, { numeric: 'always' }).format(at < now ? -value : value, unit)
  } catch {
    return new Intl.RelativeTimeFormat('en', { numeric: 'always' }).format(at < now ? -value : value, unit)
  }
}

/** "6 months", the bare length between now and the date; null without a readable date. */
export function spanText(date, lang = 'en', now = Date.now()) {
  const at = time(date)
  if (!Number.isFinite(at)) return null
  const { value, unit } = spanOf(at - now)
  const format = (l) => new Intl.NumberFormat(l, { style: 'unit', unit, unitDisplay: 'long' }).format(value)
  try { return format(lang) } catch { return format('en') }
}

/** Whole days until the date, rounded up; negative once it is past. */
export function daysUntil(date, now = Date.now()) {
  const at = time(date)
  if (!Number.isFinite(at)) return null
  return at >= now ? Math.ceil((at - now) / DAY) : -Math.ceil((now - at) / DAY)
}

// Days left under which the row turns urgent, then worth watching
const URGENT_DAYS = 7
const SOON_DAYS = 30

export const urgencyOf = (days) => (days === null ? undefined : days <= URGENT_DAYS ? 'bad' : days <= SOON_DAYS ? 'warn' : 'good')

/** Share of the validity already spent, 0 to 100; null without both dates. */
export function elapsedPercent(validFrom, validTo, now = Date.now()) {
  const from = Date.parse(validFrom)
  const to = Date.parse(validTo)
  if (!Number.isFinite(from) || !Number.isFinite(to) || to <= from) return null
  return Math.round(Math.min(1, Math.max(0, (now - from) / (to - from))) * 100)
}
