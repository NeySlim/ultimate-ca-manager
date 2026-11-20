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
 * mode 'due' (default) words a past date as overdue, 'event' as "ago"; `minutes`
 * counts minutes under one hour (a task run every few minutes), one at least.
 */
export function relativeParts(date, { now = new Date(), mode = 'due', minutes = false } = {}) {
  const ms = toTime(date)
  if (ms === null) return null
  const left = ms - new Date(now).getTime()
  if (minutes && Math.abs(left) < HOUR && (left > 0 || mode === 'event')) {
    return { key: left > 0 ? 'time.inMinutes' : 'time.minutesAgo', count: Math.max(1, Math.round(Math.abs(left) / 60000)) }
  }
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

// Compact wording of the work queues ("dans 28 h", "il y a 3 j"): same counts, keys under time.compact
const compact = (parts) => (parts ? { ...parts, key: parts.key.replace(/^time\./, 'time.compact.') } : null)

/** "in 28 h", "in 3 d", "overdue by 5 d"; '' without a date. */
export const compactDue = (date, t, opts) => say(compact(relativeParts(date, { ...opts, mode: 'due' })), t)

/** "20 h ago", "3 d ago"; '' without a date. */
export const compactAgo = (date, t, opts) => say(compact(relativeParts(date, { ...opts, mode: 'event' })), t)

/** A run of a task: "56 min ago", "in 5 h", a past due date as "ago"; '' without a date. */
export const compactRun = (date, t, opts) => {
  const ms = toTime(date)
  if (ms === null) return ''
  const past = ms <= new Date(opts?.now ?? new Date()).getTime()
  return say(compact(relativeParts(date, { ...opts, minutes: true, mode: past ? 'event' : 'due' })), t)
}

/** 'bad' once the date is past, 'warn' inside warnDays, '' beyond or without a date. */
export function dueTone(date, { now = new Date(), warnDays = 7 } = {}) {
  const ms = toTime(date)
  if (ms === null) return ''
  const left = ms - new Date(now).getTime()
  if (left <= 0) return 'bad'
  return left < warnDays * DAY ? 'warn' : ''
}

// Short form of a due date: days below two months, then months, then years and the
// months left beyond twelve months ("1 y 4 mo", "9 y" when no month is left)
const SHORT_MONTH_DAYS = 60
const YEAR_DAYS = 365.25
const MONTH_DAYS = 30.44

/** The i18n key and counts of the short form ("3 d", "5 mo", "1 y 4 mo", "Expired"), or null without a date. */
export function shortParts(date, { now = new Date() } = {}) {
  const ms = toTime(date)
  if (ms === null) return null
  if (ms - new Date(now).getTime() <= 0) return { key: 'time.short.expired' }
  const days = daysRemaining(date, now)
  if (days < SHORT_MONTH_DAYS) return { key: 'time.short.days', count: days }
  const years = Math.floor(days / YEAR_DAYS)
  if (years < 1) return { key: 'time.short.months', count: Math.floor(days / MONTH_DAYS) }
  const months = Math.floor((days - years * YEAR_DAYS) / MONTH_DAYS)
  return months > 0
    ? { key: 'time.short.yearsMonths', count: years, months }
    : { key: 'time.short.years', count: years }
}

/** "3 d", "5 mo", "1 y 4 mo", "9 y", "Expired" in the user's language; '' without a date. */
export const relativeShort = (date, t, opts) => {
  const parts = shortParts(date, opts)
  return parts ? t(parts.key, { count: parts.count, months: parts.months }) : ''
}
