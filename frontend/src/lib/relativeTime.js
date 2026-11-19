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

/** 'bad' once the date is past, 'warn' inside warnDays, '' beyond or without a date. */
export function dueTone(date, { now = new Date(), warnDays = 7 } = {}) {
  const ms = toTime(date)
  if (ms === null) return ''
  const left = ms - new Date(now).getTime()
  if (left <= 0) return 'bad'
  return left < warnDays * DAY ? 'warn' : ''
}
