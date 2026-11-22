import { describe, it, expect } from 'vitest'
import { axisTop, expiryCalendar, flowColumns, heatLevel, horizonDays, nextDay, weekday } from '../overviewHorizon'

const period = (date, manual = 0, automatic = 0, extra = {}) => ({ date, total: manual + automatic, manual, automatic, cas: 0, signers: 0, ...extra })
const days = (from, count) => Array.from({ length: count }, (_, i) => new Date(Date.parse(`${from}T00:00:00Z`) + i * 86400000).toISOString().slice(0, 10))

describe('the horizon window', () => {
  it('reads weekdays Monday first, in UTC', () => {
    expect(weekday('2026-11-23')).toBe(0) // a Monday
    expect(weekday('2026-11-22')).toBe(6) // a Sunday
  })

  it('asks the days that end on the Sunday of the last week, the current week counting as the first', () => {
    expect(horizonDays(13, '2026-11-23')).toBe(91)
    expect(horizonDays(13, '2026-11-25')).toBe(89) // Wednesday: two days of this week are behind
    expect(horizonDays(13, '2026-11-29')).toBe(85) // Sunday
    const from = '2026-11-25'
    const last = days(from, horizonDays(13, from)).at(-1)
    expect(weekday(last)).toBe(6)
  })

  it('names the exclusive bound of a day across a month and a year', () => {
    expect(nextDay('2026-12-31')).toBe('2027-01-01')
    expect(nextDay('2028-02-28')).toBe('2028-02-29')
  })
})

describe('expiryCalendar', () => {
  const from = '2026-11-25' // a Wednesday
  const periods = days(from, horizonDays(2, from)).map((d) => period(d))
  periods[0] = period(from, 1, 2) // Wednesday, today
  periods[4] = period('2026-11-29', 0, 1, { cas: 1, infrastructure: true }) // Sunday of the first week
  periods[5] = period('2026-11-30', 4, 0) // Monday of the second week

  it('lays the days out in Monday-first UTC weeks, the days before today outside the window', () => {
    const weeks = expiryCalendar(periods, from)
    expect(weeks).toHaveLength(2)
    expect(weeks[0].start).toBe('2026-11-23')
    expect(weeks[0].days.map((d) => d.out)).toEqual([true, true, false, false, false, false, false])
    expect(weeks[1].days.every((d) => !d.out)).toBe(true)
  })

  it('sums a week over its days in the window and bounds it by its first and last day there', () => {
    const [first, second] = expiryCalendar(periods, from)
    expect(first).toMatchObject({ from: '2026-11-25', to: '2026-11-29', total: 4, manual: 1, automatic: 3, cas: 1 })
    expect(second).toMatchObject({ from: '2026-11-30', to: '2026-12-06', total: 4, manual: 4, automatic: 0 })
  })

  it('marks a day where an authority or a signer expires', () => {
    const sunday = expiryCalendar(periods, from)[0].days[6]
    expect(sunday).toMatchObject({ date: '2026-11-29', infrastructure: true })
    expect(expiryCalendar(periods, from)[0].days[2].infrastructure).toBe(false)
  })

  it('gives nothing without a window', () => {
    expect(expiryCalendar([], null)).toEqual([])
    expect(expiryCalendar(undefined, 'x')).toEqual([])
  })
})

describe('heatLevel', () => {
  it('has five steps: nothing, then quarters of the busiest day', () => {
    expect([0, 1, 2, 3, 4, 8].map((v) => heatLevel(v, 8))).toEqual([0, 1, 1, 2, 2, 4])
    expect(heatLevel(5, 8)).toBe(3)
    // A day past a quarter steps up: a third of the busiest day is the second step, not the first
    expect([1, 2, 3].map((v) => heatLevel(v, 3))).toEqual([2, 3, 4])
  })

  it('gives one expiry at least the first step', () => {
    expect(heatLevel(1, 400)).toBe(1)
  })
})

describe('flowColumns', () => {
  const flow = {
    periods: [
      { date: '2026-11-20', acme: 3, scep: 1, est: 0, wstep: 0, import: 1, manual: 2, total: 7 },
      { date: '2026-11-21', acme: 0, scep: 0, est: 2, wstep: 1, import: 0, manual: 0, total: 3 },
    ],
    previous: { total: 8 },
  }

  it('stacks the sources bottom-up in a fixed order, each segment from the top of the one below', () => {
    const { days: cols } = flowColumns(flow)
    expect(cols[0].segments).toEqual([
      { key: 'acme', from: 0, value: 3 }, { key: 'scep', from: 3, value: 1 },
      { key: 'import', from: 4, value: 1 }, { key: 'manual', from: 5, value: 2 },
    ])
    expect(cols[0].total).toBe(7)
    expect(cols[1].segments.map((s) => s.key)).toEqual(['est', 'wstep'])
  })

  it('sums the window, its gap with the previous one and the automated share', () => {
    const f = flowColumns(flow)
    expect(f.total).toBe(10)
    expect(f.max).toBe(7)
    expect(f.totals).toMatchObject({ acme: 3, scep: 1, est: 2, wstep: 1, import: 1, manual: 2 })
    expect(f.trend).toBeCloseTo(0.25)
    expect(f.automaticShare).toBe(70)
  })

  it('has no gap without a previous window and no share without issuances', () => {
    const f = flowColumns({ periods: [{ date: '2026-11-21' }], previous: { total: 0 } })
    expect(f.trend).toBeNull()
    expect(f.automaticShare).toBeNull()
  })
})

describe('axisTop', () => {
  it('rounds up to four whole steps', () => {
    expect([0, 3, 4, 5, 11, 12, 13].map(axisTop)).toEqual([4, 4, 4, 8, 12, 12, 16])
  })
})
