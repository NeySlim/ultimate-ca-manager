/**
 * The reports of the queue: every schedulable report (data reports, PDF templates),
 * their schedule and next run. The scheduler (services/report_service.py) runs on
 * UTC time: a weekly report on day_of_week (0 is Monday), a monthly one on day_of_month.
 */
import { Clock, ChartBar } from '@phosphor-icons/react'
import { reportsService } from '../../services'

export const DATA_REPORTS = ['certificate_inventory', 'expiring_certificates', 'ca_hierarchy', 'audit_summary', 'compliance_status', 'revoked_certificates']
export const PDF_REPORTS = ['pdf_executive', 'pdf_certificate_inventory', 'pdf_compliance', 'pdf_ca_overview', 'pdf_security_audit']
export const REPORT_KEYS = [...DATA_REPORTS, ...PDF_REPORTS]
export const DEFAULT_SCHEDULE = { enabled: false, frequency: 'weekly', time: '08:00', day_of_week: 1, day_of_month: 1, recipients: [], format: 'csv' }

const HOUR = 3600000
export const isPdf = (key) => String(key || '').startsWith('pdf_')

export function reportName(key, t) {
  if (isPdf(key)) return t(`reports.pdf.template.${key.slice(4)}.name`)
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
    { id: 'today', label: t('reports.work.groups.today'), icon: Clock, tone: '', test: (e) => e.next - now < 24 * HOUR },
    { id: 'later', label: t('reports.work.groups.later'), icon: ChartBar, tone: '', test: (e) => e.next - now >= 24 * HOUR },
  ].map(({ test, ...g }) => ({ ...g, entries: runs.filter(test) }))
}

/** "Weekly · 08:00 UTC" */
export const frequencyPill = (schedule, t) => t(`reports.work.freq.${schedule.frequency}`, { time: schedule.time })

/** "Weekly, on Monday, at 08:00 UTC" */
export function frequencyLong(schedule, t) {
  const days = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
  return t(`reports.work.freqLong.${schedule.frequency}`, {
    time: schedule.time,
    day: schedule.frequency === 'weekly' ? t(`reports.work.dayName.${days[Number(schedule.day_of_week ?? 1)] || 'mon'}`) : schedule.day_of_month,
  })
}

export const formatLabel = (key, schedule) => (isPdf(key) ? 'PDF' : String(schedule?.format || 'csv').toUpperCase())

/** The inspector's copy of a report: its key and schedule, read from the schedule route. */
export async function fetchReport(key) {
  const res = await reportsService.getSchedule()
  return { data: { key, schedule: scheduleOf(res?.data, key) } }
}

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
