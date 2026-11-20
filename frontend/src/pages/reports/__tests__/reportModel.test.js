/**
 * Next run of a report schedule, as the UTC scheduler runs it (report_service.run_scheduled_reports):
 * HH:MM in UTC, weekly on day_of_week with 0 for Monday, monthly on day_of_month.
 */
import { describe, it, expect } from 'vitest'
import { nextRun, reportGroups, scheduleOf, parseReport, scheduleClock, scheduleForm, toSchedulerClock, frequencyPill, frequencyLong, reportFigure, reportName } from '../reportModel'
import { frT } from '../../../components/work/__tests__/frI18n'

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

describe('scheduleClock: the hour of a schedule in the user\'s timezone', () => {
  const daily = { enabled: true, frequency: 'daily', time: '06:00' }
  it('keeps the hour as it is for a user on UTC, without a suffix', () => {
    expect(frequencyPill(daily, frT, { now: NOW, tz: 'UTC' })).toBe('Quotidien · 06:00')
  })

  it('converts the next run to the user\'s clock, winter and summer time both', () => {
    expect(frequencyPill(daily, frT, { now: NOW, tz: 'Europe/Paris' })).toBe('Quotidien · 07:00')
    expect(frequencyPill(daily, frT, { now: new Date(Date.UTC(2026, 6, 1, 3)), tz: 'Europe/Paris' })).toBe('Quotidien · 08:00')
  })

  it('converts a weekly run that stays on its day, keeps UTC, said, for one the conversion moves', () => {
    const early = { enabled: true, frequency: 'weekly', time: '08:00', day_of_week: 0 }
    expect(frequencyLong(early, frT, { now: NOW, tz: 'Europe/Paris' })).toBe('Hebdomadaire, le lundi, à 09:00')
    const late = { enabled: true, frequency: 'weekly', time: '23:30', day_of_week: 0 }
    expect(frequencyLong(late, frT, { now: NOW, tz: 'Europe/Paris' })).toBe('Hebdomadaire, le lundi, à 23:30 UTC')
    expect(frequencyPill(late, frT, { now: NOW, tz: 'Europe/Paris' })).toBe('Hebdomadaire · 23:30 UTC')
    expect(frequencyLong(late, frT, { now: NOW, tz: 'UTC' })).toBe('Hebdomadaire, le lundi, à 23:30')
  })

  it('keeps UTC, said, for a monthly run the conversion moves to another day', () => {
    const first = { enabled: true, frequency: 'monthly', time: '02:00', day_of_month: 1 }
    expect(scheduleClock(first, { now: NOW, tz: 'America/New_York' })).toEqual({ time: '02:00', weekday: 1, day: 1, utc: true })
    expect(frequencyLong(first, frT, { now: NOW, tz: 'America/New_York' })).toBe('Mensuel, le 1er, à 02:00 UTC')
    expect(frequencyLong(first, frT, { now: NOW, tz: 'Europe/Paris' })).toBe('Mensuel, le 1er, à 03:00')
  })

})

describe('the schedule dialog: typed in the user\'s timezone, stored in UTC', () => {
  const paris = { now: NOW, tz: 'Europe/Paris' }
  it('opens on the time and day the row reads', () => {
    expect(scheduleForm({ frequency: 'monthly', time: '06:45', day_of_month: 1 }, paris)).toMatchObject({ utc: false, time: '07:45', day_of_month: 1 })
    expect(scheduleForm({ frequency: 'weekly', time: '23:30', day_of_week: 6 }, paris)).toMatchObject({ utc: true, time: '23:30', day_of_week: 6 })
    expect(scheduleForm({ frequency: 'daily', time: '06:00' }, { now: NOW, tz: 'UTC' })).toMatchObject({ utc: false, time: '06:00' })
  })

  it('stores a typed time back at the scheduler\'s hour, summer time too', () => {
    expect(toSchedulerClock({ frequency: 'monthly', time: '07:45', day_of_week: 1, day_of_month: 1 }, paris)).toEqual({ time: '06:45', day_of_week: 1, day_of_month: 1 })
    expect(toSchedulerClock({ frequency: 'daily', time: '08:00', day_of_week: 1, day_of_month: 1 }, { now: new Date(Date.UTC(2026, 6, 1, 3)), tz: 'Europe/Paris' }))
      .toMatchObject({ time: '06:00' })
    // Typed in summer for a run after the clocks go back: the offset of the run's day counts
    expect(toSchedulerClock({ frequency: 'monthly', time: '07:45', day_of_week: 1, day_of_month: 1 }, { now: new Date(Date.UTC(2026, 9, 20, 10)), tz: 'Europe/Paris' }))
      .toMatchObject({ time: '06:45', day_of_month: 1 })
    expect(toSchedulerClock({ frequency: 'daily', time: '20:00', day_of_week: 1, day_of_month: 1 }, { now: NOW, tz: 'America/New_York' })).toMatchObject({ time: '01:00' })
  })

  it('moves a weekly or monthly day with the run, refuses a monthly one out of days 1 to 28', () => {
    expect(toSchedulerClock({ frequency: 'weekly', time: '00:30', day_of_week: 0, day_of_month: 1 }, paris)).toMatchObject({ time: '23:30', day_of_week: 6 })
    expect(toSchedulerClock({ frequency: 'monthly', time: '00:30', day_of_week: 0, day_of_month: 15 }, paris)).toMatchObject({ time: '23:30', day_of_month: 14 })
    expect(toSchedulerClock({ frequency: 'monthly', time: '00:30', day_of_week: 0, day_of_month: 1 }, paris)).toBeNull()
    expect(toSchedulerClock({ frequency: 'monthly', time: '22:00', day_of_week: 0, day_of_month: 28 }, { now: NOW, tz: 'America/New_York' })).toBeNull()
  })

  it('reads back what it stores: the row and the dialog give the same hour', () => {
    for (const tz of ['Europe/Paris', 'America/New_York', 'Asia/Kolkata', 'UTC']) {
      const typed = { frequency: 'monthly', time: '10:15', day_of_week: 2, day_of_month: 12 }
      const stored = toSchedulerClock(typed, { now: NOW, tz })
      expect(scheduleForm({ ...typed, ...stored }, { now: NOW, tz })).toMatchObject({ utc: false, time: '10:15', day_of_month: 12 })
    }
  })
})

describe('reportFigure', () => {
  it('reads the expiring certificates from the counters, as the report counts them', () => {
    expect(reportFigure('expiring_certificates', { expiring: 8 }, frT)).toBe('8 certificats à J+30')
    expect(reportFigure('expiring_certificates', { expiring: 1 }, frT)).toBe('1 certificat à J+30')
  })

  it('has none for a report the counters do not hold, nor without counters', () => {
    expect(reportFigure('certificate_inventory', { expiring: 8, total: 282 }, frT)).toBeNull()
    expect(reportFigure('expiring_certificates', null, frT)).toBeNull()
  })
})

describe('reportName', () => {
  it('names a PDF template apart from the data report of the same title', () => {
    expect(reportName('certificate_inventory', frT)).not.toBe(reportName('pdf_certificate_inventory', frT))
    expect(reportName('pdf_certificate_inventory', frT)).toMatch(/\(PDF\)$/)
  })
})
