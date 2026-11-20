/**
 * What can be done with a report, from the queue or the inspector: download it
 * now, schedule it (or change its schedule), suspend its schedule, send a test
 * e-mail, build a PDF from chosen sections. Several downloads run one after the
 * other and end on one message, or on a line-by-line outcome when one failed; a
 * suspension of several is one update.
 */
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { PaperPlaneTilt, FilePdf, Warning, Question } from '@phosphor-icons/react'
import { Modal } from '../../components/Modal'
import { WorkButton, BulkOutcome, runEach, rememberFocus, ClockIcon } from '../../components/work'
import { reportsService } from '../../services'
import { useNotification } from '../../contexts'
import { downloadBlob } from '../../lib/utils'
import { REPORT_KEYS, isPdf, reportName, scheduleOf, downloadReport, scheduleForm, toSchedulerClock } from './reportModel'

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const TIME = /^([01]\d|2[0-3]):[0-5]\d$/
const DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
export const reportsChanged = () => window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'report' } }))

export function useReportActions({ schedules, pdfSections = [], onDone } = {}) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const [dlg, setDlg] = useState(null) // { kind: 'schedule'|'test'|'pdf'|'outcome', ... }
  const [form, setForm] = useState({})
  const [errors, setErrors] = useState({})
  const [busy, setBusy] = useState(false)
  const back = useRef(null)
  const close = () => { setDlg(null); setErrors({}) }
  // Every way out gives the focus back to the control that opened the dialog (or `from`, when that one left)
  const show = (next, from) => { back.current = rememberFocus(from); setErrors({}); setDlg(next) }
  const leave = () => { close(); back.current?.() }

  const done = async () => { reportsChanged(); await onDone?.() }

  const download = async (key) => {
    try {
      await downloadReport(key, scheduleOf(schedules, key).format, downloadBlob)
      showSuccess(t(isPdf(key) ? 'reports.pdfGenerated' : 'reports.downloaded'))
    } catch {
      showError(t(isPdf(key) ? 'reports.pdfFailed' : 'reports.downloadFailed'))
    }
  }
  const downloadMany = async (keys) => {
    if (keys.length === 1) return download(keys[0])
    const outcome = await runEach(keys, (key) => downloadReport(key, scheduleOf(schedules, key).format, downloadBlob))
    if (outcome.every((o) => o.ok)) showSuccess(t('reports.work.downloadedMany', { count: outcome.length }))
    else show({ kind: 'outcome', outcome })
    return undefined
  }

  // The dialog shows the time and day the row reads, in the user's timezone (or UTC, said)
  const formOf = (key) => {
    const s = scheduleOf(schedules, key)
    return { key, editing: s.enabled, ...s, ...scheduleForm(s), recipients: (s.recipients || []).join(', ') }
  }
  const openSchedule = (key, from) => {
    const first = key || REPORT_KEYS.find((k) => !scheduleOf(schedules, k).enabled) || REPORT_KEYS[0]
    setForm({ fixed: !!key, ...formOf(first) })
    show({ kind: 'schedule' }, from)
  }
  const pick = (key) => setForm((f) => ({ ...f, ...formOf(key) }))
  const saveSchedule = async () => {
    const recipients = String(form.recipients || '').split(/[,;\s]+/).map((r) => r.trim()).filter(Boolean)
    const errs = {}
    const typed = { frequency: form.frequency, time: String(form.time || '').trim(), day_of_week: form.day_of_week, day_of_month: form.day_of_month }
    // Typed on the user's clock unless the dialog says UTC; stored on the scheduler's
    const stored = TIME.test(typed.time) && (form.utc ? typed : toSchedulerClock(typed))
    if (!TIME.test(typed.time)) errs.time = t('reports.work.dialog.timeInvalid')
    else if (!stored) errs.time = t('reports.work.dialog.timeDayShift')
    if (!recipients.length) errs.recipients = t('reports.work.dialog.recipientsRequired')
    else if (recipients.some((r) => !EMAIL.test(r))) errs.recipients = t('reports.work.dialog.recipientsInvalid')
    setErrors(errs)
    if (Object.keys(errs).length) {
      document.getElementById(errs.time ? 'sch-time' : 'sch-to')?.focus()
      return
    }
    setBusy(true)
    try {
      await reportsService.updateSchedule({ [form.key]: {
        enabled: true, frequency: form.frequency, time: stored.time,
        day_of_week: Number(stored.day_of_week), day_of_month: Number(stored.day_of_month),
        recipients, format: isPdf(form.key) ? 'pdf' : form.format,
      } })
      showSuccess(t('reports.scheduleUpdated'))
      leave()
      await done()
    } catch {
      showError(t('reports.scheduleFailed'))
    } finally {
      setBusy(false)
    }
  }

  // The schedule route takes several reports at once: one update suspends them all
  const suspend = async (keys) => {
    const body = Object.fromEntries(keys.map((k) => [k, { ...scheduleOf(schedules, k), enabled: false }]))
    try {
      await reportsService.updateSchedule(body)
      showSuccess(t('reports.work.suspended', { count: keys.length }))
      await done()
    } catch {
      showError(t('reports.scheduleFailed'))
    }
  }

  const openTest = (key, from) => { setForm({ key, email: '' }); show({ kind: 'test' }, from) }
  const sendTest = async () => {
    const email = String(form.email || '').trim()
    if (!EMAIL.test(email)) { setErrors({ email: t('reports.work.dialog.emailInvalid') }); document.getElementById('test-email')?.focus(); return }
    setBusy(true)
    try {
      await reportsService.sendTest(form.key, email)
      showSuccess(t('reports.testSent'))
      leave()
    } catch {
      showError(t('reports.testFailed'))
    } finally {
      setBusy(false)
    }
  }

  const openPdf = () => { setForm({ sections: [] }); show({ kind: 'pdf' }) }
  const buildPdf = async () => {
    setBusy(true)
    try {
      const response = await reportsService.generateCustomPDF({ sections: form.sections })
      const blob = response instanceof Blob ? response : new Blob([response], { type: 'application/pdf' })
      downloadBlob(blob, `ucm-report-custom-${new Date().toISOString().slice(0, 10)}.pdf`)
      showSuccess(t('reports.pdfGenerated'))
      leave()
    } catch {
      showError(t('reports.pdfFailed'))
    } finally {
      setBusy(false)
    }
  }

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }))
  const fieldError = (name) => errors[name] && (
    <p className="wk-field-error" id={`err-${name}`}><Warning aria-hidden="true" /><span>{errors[name]}</span></p>
  )
  // The error comes first, then the hint, as the mockup reads them
  const describe = (hint, name) => [errors[name] && `err-${name}`, hint].filter(Boolean).join(' ')
  const utc = !!form.utc

  const titles = {
    schedule: form.editing ? t('reports.work.dialog.editTitle') : t('reports.work.schedule'),
    test: t('reports.testSend'),
    pdf: t('reports.work.dialog.pdfTitle'),
    outcome: t('work.bulk.title'),
  }
  const subtitles = {
    schedule: form.fixed ? reportName(form.key, t) : t('reports.work.dialog.scheduleSubtitle'),
    test: reportName(form.key, t),
    pdf: t('reports.work.dialog.pdfSubtitle'),
    outcome: t('reports.work.downloadedOutcome', { count: dlg?.outcome?.length || 0 }),
  }

  const dialog = (
    <Modal open={!!dlg} onOpenChange={(v) => { if (!v) leave() }} title={dlg ? titles[dlg.kind] : ''}
      subtitle={dlg ? subtitles[dlg.kind] : ''} size={dlg?.kind === 'schedule' || dlg?.kind === 'test' ? 'sm' : 'md'}>
      {dlg?.kind === 'outcome' && (
        <BulkOutcome outcome={dlg.outcome} nameOf={(key) => reportName(key, t)} onClose={leave} />
      )}
      {dlg?.kind === 'schedule' && (
        <form className="wk-dialog" noValidate onSubmit={(e) => { e.preventDefault(); saveSchedule() }} data-testid="schedule-form">
          <div className="wk-fields">
            <div className="wk-field is-full">
              <label htmlFor="sch-kind">{t('reports.work.dialog.content')}</label>
              <select id="sch-kind" value={form.key} disabled={form.fixed} onChange={(e) => pick(e.target.value)} autoFocus={!form.fixed}>
                {REPORT_KEYS.map((k) => <option key={k} value={k}>{reportName(k, t)}</option>)}
              </select>
            </div>
            <div className="wk-field">
              <label htmlFor="sch-freq">{t('reports.frequency')}</label>
              <select id="sch-freq" value={form.frequency} onChange={set('frequency')} autoFocus={form.fixed}>
                <option value="daily">{t('reports.daily')}</option>
                <option value="weekly">{t('reports.weekly')}</option>
                <option value="monthly">{t('reports.monthly')}</option>
              </select>
            </div>
            <div className="wk-field">
              <label htmlFor="sch-time">{t(utc ? 'reports.work.dialog.timeUtc' : 'reports.work.dialog.time')}</label>
              <input id="sch-time" value={form.time || ''} onChange={set('time')} inputMode="numeric" autoComplete="off"
                aria-invalid={!!errors.time || undefined} aria-describedby={describe('hint-sch-time', 'time')} />
              {fieldError('time')}
              <small id="hint-sch-time">{t(utc ? 'reports.work.dialog.timeHintUtc' : 'reports.work.dialog.timeHint')}</small>
            </div>
            {form.frequency === 'weekly' && (
              <div className="wk-field">
                <label htmlFor="sch-dow">{t('reports.dayOfWeek')}</label>
                <select id="sch-dow" value={form.day_of_week} onChange={set('day_of_week')}>
                  {DAYS.map((d, i) => <option key={d} value={i}>{t(`reports.days.${d}`)}</option>)}
                </select>
              </div>
            )}
            {form.frequency === 'monthly' && (
              <div className="wk-field">
                <label htmlFor="sch-dom">{t('reports.dayOfMonth')}</label>
                <select id="sch-dom" value={form.day_of_month} onChange={set('day_of_month')}>
                  {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
              </div>
            )}
            {!isPdf(form.key) && (
              <div className="wk-field">
                <label htmlFor="sch-format">{t('reports.format')}</label>
                <select id="sch-format" value={form.format} onChange={set('format')}>
                  <option value="csv">CSV</option>
                  <option value="json">JSON</option>
                </select>
              </div>
            )}
            <div className="wk-field is-full">
              <label htmlFor="sch-to">{t('reports.recipients')}</label>
              <input id="sch-to" value={form.recipients || ''} onChange={set('recipients')} autoComplete="off" spellCheck={false}
                placeholder="pki@example.com" aria-invalid={!!errors.recipients || undefined} aria-describedby={describe('hint-sch-to', 'recipients')} />
              {fieldError('recipients')}
              <small id="hint-sch-to">{t('reports.work.dialog.recipientsHint')}</small>
            </div>
          </div>
          <p className="wk-notice"><Question aria-hidden="true" /><span>{t('reports.work.dialog.scheduleNote')}</span></p>
          <div className="lv-dialog-actions">
            <WorkButton onClick={leave}>{t('common.cancel')}</WorkButton>
            <WorkButton type="submit" primary icon={ClockIcon} disabled={busy}>{t('reports.work.dialog.save')}</WorkButton>
          </div>
        </form>
      )}
      {dlg?.kind === 'test' && (
        <form className="wk-dialog" noValidate onSubmit={(e) => { e.preventDefault(); sendTest() }}>
          <p className="ui-dialog-message">{t('reports.testSendDesc', { type: reportName(form.key, t) })}</p>
          <div className="wk-field">
            <label htmlFor="test-email">{t('reports.recipientEmail')}</label>
            <input id="test-email" type="email" value={form.email || ''} onChange={set('email')} autoFocus placeholder="admin@example.com"
              aria-invalid={!!errors.email || undefined} aria-describedby={errors.email ? 'err-email' : undefined} />
            {fieldError('email')}
          </div>
          <div className="lv-dialog-actions">
            <WorkButton onClick={leave}>{t('common.cancel')}</WorkButton>
            <WorkButton type="submit" primary icon={PaperPlaneTilt} disabled={busy}>{t('reports.send')}</WorkButton>
          </div>
        </form>
      )}
      {dlg?.kind === 'pdf' && (
        <form className="wk-dialog" noValidate onSubmit={(e) => { e.preventDefault(); buildPdf() }}>
          <fieldset className="wk-fields wk-pdf-sections">
            <legend className="sr-only">{t('reports.pdf.sections')}</legend>
            {pdfSections.map((id) => (
              <label key={id} className="wk-check-line">
                <input type="checkbox" checked={form.sections?.includes(id) || false}
                  onChange={() => setForm((f) => ({ ...f, sections: f.sections.includes(id) ? f.sections.filter((s) => s !== id) : [...f.sections, id] }))} />
                <span>{t(`reports.pdf.section.${id}`, { defaultValue: id.replace(/_/g, ' ') })}</span>
              </label>
            ))}
          </fieldset>
          <div className="lv-dialog-actions">
            <WorkButton quiet onClick={() => setForm((f) => ({ ...f, sections: [...pdfSections] }))}>{t('common.selectAll')}</WorkButton>
            <WorkButton quiet onClick={() => setForm((f) => ({ ...f, sections: [] }))}>{t('common.deselectAll')}</WorkButton>
            <span className="wk-spacer" />
            <WorkButton onClick={leave}>{t('common.cancel')}</WorkButton>
            <WorkButton type="submit" primary icon={FilePdf} disabled={busy || !form.sections?.length}>{t('reports.pdf.generateCustom')}</WorkButton>
          </div>
        </form>
      )}
    </Modal>
  )

  return { download, downloadMany, openSchedule, suspend, openTest, openPdf, dialog }
}
