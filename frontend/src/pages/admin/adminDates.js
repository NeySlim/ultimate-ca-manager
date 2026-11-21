/**
 * Dates of the administration pages in the mockup's forms: « 8 nov. 2026 » (date) and
 * « 8 nov. 2026, 11:58 » (dateTime), in the interface's language and the application's time zone.
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
const TIME = { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }

const valid = (value) => {
  if (value === null || value === undefined || value === '') return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d
}

export function dateOf(value, locale) {
  const d = valid(value)
  return d ? fmt(locale, DATE).format(d) : ''
}

export function dateTimeOf(value, locale) {
  const d = valid(value)
  return d ? `${fmt(locale, DATE).format(d)}, ${fmt(locale, TIME).format(d)}` : ''
}
