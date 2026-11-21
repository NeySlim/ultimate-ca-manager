/**
 * The reports of the queue: every schedulable report (data reports, PDF templates),
 * their schedule and next run. The scheduler (services/report_service.py) runs on
 * UTC time: a weekly report on day_of_week (0 is Monday), a monthly one on day_of_month.
 * The page reads and types those in the user's timezone, converted both ways.
 */
import { reportsService } from '../../services'
import { getAppTimezone } from '../../stores/timezoneStore'

export const DATA_REPORTS = ['certificate_inventory', 'expiring_certificates', 'ca_hierarchy', 'audit_summary', 'compliance_status', 'revoked_certificates']
export const PDF_REPORTS = ['pdf_executive', 'pdf_certificate_inventory', 'pdf_compliance', 'pdf_ca_overview', 'pdf_security_audit']
export const REPORT_KEYS = [...DATA_REPORTS, ...PDF_REPORTS]
export const DEFAULT_SCHEDULE = { enabled: false, frequency: 'weekly', time: '08:00', day_of_week: 1, day_of_month: 1, recipients: [], format: 'csv' }

const HOUR = 3600000
export const isPdf = (key) => String(key || '').startsWith('pdf_')

// A PDF template says so in its name: two reports must not read the same ("Certificate inventory")
export function reportName(key, t) {
  if (isPdf(key)) return t('reports.work.pdfName', { name: t(`reports.pdf.template.${key.slice(4)}.name`) })
  return t(`reports.types.${key}.name`)
}
export function reportDescription(key, t) {
  if (isPdf(key)) return t(`reports.pdf.template.${key.slice(4)}.description`)
  return t(`reports.types.${key}.description`)
}

/** The list of certificates a report carries, as a certificate list link; null for the others. */
export const CERTIFICATE_LINKS = {
  certificate_inventory: '/certificates',
  expiring_certificates: '/certificates?status=expiring',
  revoked_certificates: '/certificates?status=revoked',
}

export const scheduleOf = (schedules, key) => ({ ...DEFAULT_SCHEDULE, ...(isPdf(key) ? { format: 'pdf', frequency: 'monthly' } : {}), ...(schedules?.[key] || {}) })

/** Next run of an enabled schedule after `now`, as the UTC scheduler would run it; null when disabled. */
export function nextRun(schedule, now = new Date()) {
  if (!schedule?.enabled) return null
  const [h, m] = String(schedule.time || '08:00').split(':').map(Number)
  const at = (y, mo, d) => new Date(Date.UTC(y, mo, d, h || 0, m || 0))
  const base = new Date(now)
  for (let i = 0; i <= 62; i++) {
    const day = new Date(Date.UTC(base.getUTCFullYear(), base.getUTCMonth(), base.getUTCDate() + i))
    const run = at(day.getUTCFullYear(), day.getUTCMonth(), day.getUTCDate())
    if (run <= base) continue
    const weekday = (day.getUTCDay() + 6) % 7 // 0 is Monday, as Python's weekday()
    if (schedule.frequency === 'weekly' && weekday !== Number(schedule.day_of_week ?? 1)) continue
    if (schedule.frequency === 'monthly' && day.getUTCDate() !== Number(schedule.day_of_month ?? 1)) continue
    return run
  }
  return null
}

/** The scheduled reports by their next run: within 24 h, later. Empty groups are left out by the queue. */
export function reportGroups(entries, t, now = Date.now()) {
  const runs = entries.map((e) => ({ ...e, next: nextRun(e.schedule, new Date(now)) })).filter((e) => e.next)
    .sort((a, b) => a.next - b.next)
  return [
    { id: 'today', label: t('reports.work.groups.today'), icon: 'clock', tone: '', test: (e) => e.next - now < 24 * HOUR },
    { id: 'later', label: t('reports.work.groups.later'), icon: 'chart', tone: '', test: (e) => e.next - now >= 24 * HOUR },
  ].map(({ test, ...g }) => ({ ...g, entries: runs.filter(test) }))
}

const DAY_KEYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']

/** Wall clock of `date` in `tz`: hour, minute, weekday (0 is Monday), day of the month, offset from UTC in minutes. */
export function wallClock(date, tz) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-US', {
    timeZone: tz, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', weekday: 'short',
  }).formatToParts(date).map((p) => [p.type, p.value]))
  const hour = Number(parts.hour) % 24
  const wall = Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day), hour, Number(parts.minute))
  return {
    hour,
    minute: Number(parts.minute),
    weekday: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].indexOf(parts.weekday),
    day: Number(parts.day),
    offset: Math.round((wall - Math.floor(date.getTime() / 60000) * 60000) / 60000),
  }
}

const pad = (n) => String(n).padStart(2, '0')

/**
 * The schedule's time and day as the user reads them: its next run (UTC on the server)
 * in the app's timezone. A weekly or monthly run the conversion moves to another day
 * stays in UTC, said so (`utc`): its day is the scheduler's.
 */
export function scheduleClock(schedule, { now = new Date(), tz = getAppTimezone() } = {}) {
  const asUtc = { time: schedule.time, weekday: Number(schedule.day_of_week ?? 1), day: Number(schedule.day_of_month ?? 1), utc: false }
  const next = nextRun({ ...schedule, enabled: true }, now)
  let clock
  try { clock = next && wallClock(next, tz) } catch { clock = null }
  if (!clock) return { ...asUtc, utc: true }
  if (clock.offset === 0) return asUtc
  if (schedule.frequency === 'weekly' && clock.weekday !== asUtc.weekday) return { ...asUtc, utc: true }
  if (schedule.frequency === 'monthly' && clock.day !== asUtc.day) return { ...asUtc, utc: true }
  return { time: `${pad(clock.hour)}:${pad(clock.minute)}`, weekday: clock.weekday, day: clock.day, utc: false }
}

/** The dialog's copy of a schedule: the time and day its row reads, in UTC (`utc`) when the row says UTC. */
export function scheduleForm(schedule, opts) {
  const clock = scheduleClock(schedule, opts)
  return {
    utc: clock.utc,
    time: clock.time,
    day_of_week: schedule.frequency === 'weekly' ? clock.weekday : Number(schedule.day_of_week ?? 1),
    day_of_month: schedule.frequency === 'monthly' ? clock.day : Number(schedule.day_of_month ?? 1),
  }
}

/**
 * A time and day typed on the user's clock, as the UTC scheduler stores them: the next
 * such run, moved by the offset in force on its day; a weekly day follows the run. Null
 * when it cannot be stored: a monthly run moved out of days 1 to 28, or an unknown timezone.
 */
export function toSchedulerClock({ frequency, time, day_of_week, day_of_month }, { now = new Date(), tz = getAppTimezone() } = {}) {
  const offsetAt = (d) => wallClock(d, tz).offset * 60000
  let local, at
  try {
    local = nextRun({ enabled: true, frequency, time, day_of_week, day_of_month }, new Date(now.getTime() + offsetAt(now)))
    if (!local) return null
    at = new Date(local.getTime() - offsetAt(new Date(local.getTime() - offsetAt(now))))
  } catch { return null }
  const dayOf = (d) => Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate())
  const shift = Math.round((dayOf(at) - dayOf(local)) / 86400000)
  const out = { time: `${pad(at.getUTCHours())}:${pad(at.getUTCMinutes())}`, day_of_week: Number(day_of_week), day_of_month: Number(day_of_month) }
  if (frequency === 'weekly') out.day_of_week = (out.day_of_week + shift + 7) % 7
  if (frequency === 'monthly') {
    out.day_of_month += shift
    if (out.day_of_month < 1 || out.day_of_month > 28) return null
  }
  return out
}

const clockTime = (clock, t) => (clock.utc ? t('reports.work.utcTime', { time: clock.time }) : clock.time)

/** "Weekly · 08:00", in the user's timezone */
export const frequencyPill = (schedule, t, opts) => t(`reports.work.freq.${schedule.frequency}`, { time: clockTime(scheduleClock(schedule, opts), t) })

/** "Weekly, on Monday, at 08:00", in the user's timezone */
export function frequencyLong(schedule, t, opts) {
  const clock = scheduleClock(schedule, opts)
  return t(`reports.work.freqLong.${schedule.frequency}`, {
    time: clockTime(clock, t),
    day: schedule.frequency === 'weekly' ? t(`reports.work.dayName.${DAY_KEYS[clock.weekday] || 'mon'}`) : t('reports.work.monthDay', { count: clock.day }),
  })
}

/**
 * The figure of a report read from the certificate counters, when they hold the report's
 * own count: certificates expiring within 30 days (not revoked, not yet expired), the
 * window and filter of report_service. Null for the others: they are computed on demand.
 */
export const FIGURE_DAYS = 30
export function reportFigure(key, stats, t) {
  if (key === 'expiring_certificates' && Number.isFinite(stats?.expiring)) {
    return t('reports.work.figure.expiring', { count: stats.expiring, days: FIGURE_DAYS })
  }
  return null
}

export const formatLabel = (key, schedule) => (isPdf(key) ? 'PDF' : String(schedule?.format || 'csv').toUpperCase())

/** Downloads a report now: the data report in its schedule's format, or the PDF of its template. */
export async function downloadReport(key, format, downloadBlob) {
  if (isPdf(key)) {
    const response = await reportsService.generateCustomPDF({ template: key.slice(4) })
    const blob = response instanceof Blob ? response : new Blob([response], { type: 'application/pdf' })
    downloadBlob(blob, `ucm-report-${key.slice(4)}-${new Date().toISOString().slice(0, 10)}.pdf`)
    return
  }
  const fmt = format === 'json' ? 'json' : 'csv'
  const res = await reportsService.download(key, fmt, 30)
  const content = typeof res === 'string' ? res : typeof res?.data === 'string' ? res.data : JSON.stringify(res?.data ?? res, null, 2)
  downloadBlob(new Blob([content], { type: fmt === 'csv' ? 'text/csv' : 'application/json' }), `ucm-report-${key}.${fmt}`)
}

/** The pill of a report: scheduled or not. */
export const scheduleState = (schedule, t) => (schedule?.enabled
  ? { tone: 'good', label: t('reports.work.state.scheduled') }
  : { tone: 'muted', label: t('reports.work.state.unscheduled') })

/** The generate route's answer as { items, columns, summary, generatedAt }. */
export function parseReport(data) {
  let parsed = data
  if (typeof data?.content === 'string') {
    try { parsed = JSON.parse(data.content) } catch { parsed = data }
  }
  const items = Array.isArray(parsed?.items) ? parsed.items : []
  return {
    items,
    columns: Array.isArray(parsed?.columns) ? parsed.columns : Object.keys(items[0] || {}),
    summary: parsed?.summary || data?.summary || {},
    generatedAt: data?.generated_at || new Date().toISOString(),
  }
}
