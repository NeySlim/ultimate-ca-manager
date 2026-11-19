/** Delays of the overview: the unit follows the length, the words follow the language. */
import { describe, it, expect } from 'vitest'
import { daysUntil, elapsedPercent, relativeTime, spanOf, spanText, urgencyOf } from '../overviewTime'

const NOW = Date.parse('2026-11-19T12:00:00Z')
const HOUR = 3600000
const DAY = 24 * HOUR

describe('span', () => {
  it.each([
    [20 * 60000, 20, 'minute'], [10, 1, 'minute'], [5 * HOUR, 5, 'hour'], [47 * HOUR, 47, 'hour'],
    [3 * DAY, 3, 'day'], [59 * DAY, 59, 'day'], [190 * DAY, 6, 'month'], [800 * DAY, 2, 'year'],
  ])('%i ms reads %i %s', (ms, value, unit) => {
    expect(spanOf(ms)).toEqual({ value, unit })
    expect(spanOf(-ms)).toEqual({ value, unit })
  })
})

describe('relative time', () => {
  it('reads forward and backward, in the interface language', () => {
    expect(relativeTime(NOW + 12 * DAY, 'en', NOW)).toBe('in 12 days')
    expect(relativeTime(NOW - 4 * HOUR, 'en', NOW)).toBe('4 hours ago')
    expect(relativeTime(NOW - 190 * DAY, 'fr', NOW)).toBe('il y a 6 mois')
    expect(relativeTime('2026-11-20T12:00:00Z', 'fr', NOW)).toBe('dans 24 heures')
  })

  it('gives the bare length for "overdue by"', () => {
    // The browser may put a no-break space between the figure and its unit
    expect(spanText(NOW - 190 * DAY, 'en', NOW).replace(/\s/g, ' ')).toBe('6 months')
    expect(spanText(NOW - 190 * DAY, 'fr', NOW).replace(/\s/g, ' ')).toBe('6 mois')
  })

  it('is null without a readable date, and falls back to English for an unknown language tag', () => {
    expect(relativeTime(null, 'en', NOW)).toBeNull()
    expect(spanText('nope', 'en', NOW)).toBeNull()
    expect(relativeTime(NOW + 3 * DAY, 'not a tag', NOW)).toBe('in 3 days')
  })
})

describe('expiry', () => {
  it('counts whole days, rounded up, negative once past', () => {
    expect(daysUntil(NOW + 1, NOW)).toBe(1)
    expect(daysUntil(NOW + 3 * DAY, NOW)).toBe(3)
    expect(daysUntil(NOW - 2 * DAY, NOW)).toBe(-2)
    expect(daysUntil(undefined, NOW)).toBeNull()
  })

  it('is urgent within 7 days, to watch within 30, fine beyond', () => {
    expect([-3, 7, 8, 30, 31, null].map(urgencyOf)).toEqual(['bad', 'bad', 'warn', 'warn', 'good', undefined])
  })

  it('gives the share of the validity spent, bounded, and nothing without both dates', () => {
    const from = new Date(NOW - 75 * DAY).toISOString()
    const to = new Date(NOW + 25 * DAY).toISOString()
    expect(elapsedPercent(from, to, NOW)).toBe(75)
    expect(elapsedPercent(from, new Date(NOW - DAY).toISOString(), NOW)).toBe(100)
    expect(elapsedPercent(new Date(NOW + DAY).toISOString(), to, NOW)).toBe(0)
    expect(elapsedPercent(null, to, NOW)).toBeNull()
    expect(elapsedPercent(to, from, NOW)).toBeNull()
  })
})
