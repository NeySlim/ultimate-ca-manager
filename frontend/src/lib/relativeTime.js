/**
 * Relative wording of a date ("in 3 days", "expired 5 days ago", "20 hours ago")
 * and the urgency tone of a due date. Days follow daysRemaining (lib/utils):
 * time left rounds up, time past rounds down, as the server counts them.
 */
import { daysRemaining } from './utils'

const HOUR = 3600000
const DAY = 24 * HOUR
// Below this the count is in hours
const HOURS_WINDOW = 48 * HOUR

const toTime = (date) => {
  if (date === null || date === undefined || date === '') return null
  const ms = new Date(date).getTime()
  return Number.isNaN(ms) ? null : ms
}

/**
 * The i18n key and count that word a date against now, or null without a date.
 * mode 'due' (default) words a past date as overdue, 'event' as "ago".
 */
export function relativeParts(date, { now = new Date(), mode = 'due' } = {}) {
  const ms = toTime(date)
  if (ms === null) return null
  const left = ms - new Date(now).getTime()
  if (left > 0) {
    return left < HOURS_WINDOW
      ? { key: 'time.inHours', count: Math.max(1, Math.round(left / HOUR)) }
      : { key: 'time.inDays', count: daysRemaining(date, now) }
  }
  if (mode === 'event') {
    return -left < HOURS_WINDOW
      ? { key: 'time.hoursAgo', count: Math.max(1, Math.round(-left / HOUR)) }
      : { key: 'time.daysAgo', count: Math.floor(-left / DAY) }
  }
  return { key: 'time.overdueDays', count: Math.max(1, Math.abs(daysRemaining(date, now))) }
}

const say = (parts, t) => (parts ? t(parts.key, { count: parts.count }) : '')

/** "in 28 hours", "in 3 days", "expired 5 days ago"; '' without a date. */
export const relativeDue = (date, t, opts) => say(relativeParts(date, { ...opts, mode: 'due' }), t)

/** "20 hours ago", "3 days ago"; '' without a date. */
export const relativeAgo = (date, t, opts) => say(relativeParts(date, { ...opts, mode: 'event' }), t)

// Below these the short count is in days, then in months, then in years
const SHORT_DAYS_BELOW = 60
const SHORT_MONTHS_BELOW = 730

/**
 * The key and count of the short wording of a due date ("3 d", "16 mo", "9 y", "Lapsed"):
 * the unit follows the size. null without a date.
 */
export function shortParts(date, { now = new Date() } = {}) {
  const days = daysRemaining(date, now)
  if (days === null) return null
  if (days <= 0) return { key: 'time.lapsed' }
  if (days < SHORT_DAYS_BELOW) return { key: 'time.shortDays', count: days }
  if (days < SHORT_MONTHS_BELOW) return { key: 'time.shortMonths', count: Math.round(days / 30.4375) }
  return { key: 'time.shortYears', count: Math.round(days / 365.25) }
}

/** "3 d", "16 mo", "9 y", "Lapsed"; '' without a date. */
export const shortDue = (date, t, opts) => {
  const parts = shortParts(date, opts)
  if (!parts) return ''
  return parts.count === undefined ? t(parts.key) : t(parts.key, { count: parts.count })
}

/** 'bad' once the date is past, 'warn' inside warnDays, '' beyond or without a date. */
export function dueTone(date, { now = new Date(), warnDays = 7 } = {}) {
  const ms = toTime(date)
  if (ms === null) return ''
  const left = ms - new Date(now).getTime()
  if (left <= 0) return 'bad'
  return left < warnDays * DAY ? 'warn' : ''
}
