/**
 * Dates of the journal in the mockup's forms: « 8 nov. 2026 » (date), « 10:42:18 » (time),
 * « 7 nov., 18:05:12 » in a row of another day, « 7 nov. 2026, 18:05:12 » in the detail.
 * Locale of the interface, time zone of the application.
 */
import { getAppTimezone } from '../../stores/timezoneStore'

const cache = new Map()
function fmt(locale, options) {
  const tz = getAppTimezone()
  const key = `${locale}|${tz}|${JSON.stringify(options)}`
  if (!cache.has(key)) {
    try { cache.set(key, new Intl.DateTimeFormat(locale, { ...options, timeZone: tz || undefined })) } catch { cache.set(key, new Intl.DateTimeFormat(locale, options)) }
  }
  return cache.get(key)
}

const DATE = { day: 'numeric', month: 'short', year: 'numeric' }
const DAY = { day: 'numeric', month: 'short' }
const TIME = { hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }

const valid = (value) => {
  if (value === null || value === undefined || value === '') return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d
}

export function eventDate(value, locale) { const d = valid(value); return d ? fmt(locale, DATE).format(d) : '' }
export function eventTime(value, locale) { const d = valid(value); return d ? fmt(locale, TIME).format(d) : '' }

/** The row's time: the time alone today, the day without its year and the time otherwise. */
export function rowTime(value, locale, now = new Date()) {
  const d = valid(value)
  if (!d) return ''
  if (eventDate(d, locale) === eventDate(now, locale)) return eventTime(d, locale)
  return `${fmt(locale, DAY).format(d)}, ${eventTime(d, locale)}`
}

export function fullTime(value, locale) {
  const d = valid(value)
  return d ? `${eventDate(d, locale)}, ${eventTime(d, locale)}` : ''
}
