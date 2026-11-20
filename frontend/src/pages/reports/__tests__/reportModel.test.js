/**
 * Next run of a report schedule, as the UTC scheduler runs it (report_service.run_scheduled_reports):
 * HH:MM in UTC, weekly on day_of_week with 0 for Monday, monthly on day_of_month.
 */
import { describe, it, expect } from 'vitest'
import { nextRun, reportGroups, scheduleOf, parseReport } from '../reportModel'

// Wednesday 18 November 2026, 10:30 UTC
const NOW = new Date(Date.UTC(2026, 10, 18, 10, 30))
const t = (key) => key

describe('nextRun', () => {
  it('is none for a disabled schedule', () => {
    expect(nextRun({ enabled: false, frequency: 'daily', time: '08:00' }, NOW)).toBeNull()
  })

  it('runs a daily report today when its time is still ahead, else tomorrow', () => {
    expect(nextRun({ enabled: true, frequency: 'daily', time: '11:00' }, NOW).toISOString()).toBe('2026-11-18T11:00:00.000Z')
    expect(nextRun({ enabled: true, frequency: 'daily', time: '10:30' }, NOW).toISOString()).toBe('2026-11-19T10:30:00.000Z')
  })

  it('counts the weekday from Monday, as Python does', () => {
    // 0 is Monday: the next Monday after Wednesday 18 is the 23rd
    expect(nextRun({ enabled: true, frequency: 'weekly', time: '08:00', day_of_week: 0 }, NOW).toISOString()).toBe('2026-11-23T08:00:00.000Z')
    // 2 is Wednesday: today has passed 08:00, so next week
    expect(nextRun({ enabled: true, frequency: 'weekly', time: '08:00', day_of_week: 2 }, NOW).toISOString()).toBe('2026-11-25T08:00:00.000Z')
    expect(nextRun({ enabled: true, frequency: 'weekly', time: '23:00', day_of_week: 2 }, NOW).toISOString()).toBe('2026-11-18T23:00:00.000Z')
  })

  it('runs a monthly report on its day, next month once passed', () => {
    expect(nextRun({ enabled: true, frequency: 'monthly', time: '06:45', day_of_month: 1 }, NOW).toISOString()).toBe('2026-12-01T06:45:00.000Z')
    expect(nextRun({ enabled: true, frequency: 'monthly', time: '06:45', day_of_month: 28 }, NOW).toISOString()).toBe('2026-11-28T06:45:00.000Z')
  })
})

describe('reportGroups', () => {
  it('puts the runs of the next 24 h first, the others after, both by date', () => {
    const entries = [
      { key: 'a', schedule: { enabled: true, frequency: 'weekly', time: '08:00', day_of_week: 0 } },
      { key: 'b', schedule: { enabled: true, frequency: 'daily', time: '06:00' } },
      { key: 'c', schedule: { enabled: true, frequency: 'daily', time: '11:00' } },
      { key: 'd', schedule: { enabled: false, frequency: 'daily', time: '11:00' } },
    ]
    const [today, later] = reportGroups(entries, t, NOW.getTime())
    expect(today.entries.map((e) => e.key)).toEqual(['c', 'b'])
    expect(later.entries.map((e) => e.key)).toEqual(['a'])
  })
})

describe('scheduleOf', () => {
  it('fills a missing schedule with the server defaults, PDF for a template', () => {
    expect(scheduleOf({}, 'audit_summary')).toMatchObject({ enabled: false, frequency: 'weekly', format: 'csv' })
    expect(scheduleOf({}, 'pdf_executive')).toMatchObject({ frequency: 'monthly', format: 'pdf' })
  })
})

describe('parseReport', () => {
  it('reads the rows of the JSON content the generate route returns', () => {
    const r = parseReport({ content: JSON.stringify({ items: [{ id: 1, common_name: 'a' }], columns: ['id', 'common_name'], summary: { total: 1 } }), generated_at: 'x' })
    expect(r).toEqual({ items: [{ id: 1, common_name: 'a' }], columns: ['id', 'common_name'], summary: { total: 1 }, generatedAt: 'x' })
  })
})
