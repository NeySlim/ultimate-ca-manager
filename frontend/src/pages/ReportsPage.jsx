/**
 * Reports: the mockup's reports module, a workView() of the scheduled reports grouped by their
 * next run, each downloadable now, and its moduleInspector() dock (Rapport, Exécutions, then the
 * product's Aperçu). The reports without a schedule take the folded section below the queue, where
 * the mockup lists its runs (the server keeps none it serves). Page actions: compose a PDF,
 * schedule a report (the mockup's scheduleDialog()).
 */
import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Zone, PageHead, WorkView, Btn, RecordRow, LoadError, LoadCause } from '../components/atelier'
import { reportsService, certificatesService } from '../services'
import { usePermission } from '../hooks'
import { formatDate } from '../lib/utils'
import { compactDue } from '../lib/relativeTime'
import {
  REPORT_KEYS, reportName, reportDescription, scheduleOf, reportGroups, frequencyPill, formatLabel, reportFigure,
} from './reports/reportModel'
import { useReportActions } from './reports/useReportActions'
import { ReportDock } from './reports/ReportDetail'

export default function ReportsPage() {
  const { t } = useTranslation()
  const { hasPermission, canWrite, canRead } = usePermission()

  const [schedules, setSchedules] = useState({})
  const [pdfSections, setPdfSections] = useState([])
  const [state, setState] = useState('loading')
  const [failure, setFailure] = useState(null)
  const [stats, setStats] = useState(null)
  const [openKey, setOpenKey] = useState(null)
  const [section, setSection] = useState('report')
  const readsCertificates = canRead('certificates')

  const load = useCallback(async ({ quiet = false } = {}) => {
    if (!quiet) setState((s) => (s === 'ready' ? s : 'loading'))
    try {
      // The certificate counters give the figure of the reports that count the same thing
      const [scheduleRes, pdfRes, statsRes] = await Promise.all([
        reportsService.getSchedule(),
        reportsService.getPdfTemplates().catch(() => ({ data: null })),
        readsCertificates ? certificatesService.getStats().catch(() => null) : null,
      ])
      setSchedules(scheduleRes?.data || {})
      setPdfSections(pdfRes?.data?.sections || [])
      setStats(statsRes?.data || null)
      setState('ready')
    } catch (err) {
      setFailure(err || null)
      setState('error')
    }
  }, [readsCertificates])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    const onChange = (e) => { if (e.detail?.type === 'report') load({ quiet: true }) }
    window.addEventListener('ucm:data-changed', onChange)
    return () => window.removeEventListener('ucm:data-changed', onChange)
  }, [load])

  const canExport = hasPermission('export:audit')
  const canSchedule = canWrite('settings')
  const actions = useReportActions({ schedules, pdfSections, onDone: () => load({ quiet: true }) })
  // The figure, else the format: the second line says what the report holds, then who gets it
  const factsOf = (e) => [
    reportFigure(e.key, stats, t) || formatLabel(e.key, e.schedule),
    e.schedule.recipients?.length ? e.schedule.recipients.join(', ') : t('reports.work.noRecipient'),
  ]

  const entries = REPORT_KEYS.map((key) => ({ key, schedule: scheduleOf(schedules, key) }))
  const unscheduled = entries.filter((e) => !e.schedule.enabled)
  const opened = entries.find((e) => e.key === openKey) || null
  const open = (e) => {
    if (e.key !== openKey) setSection('report')
    setOpenKey(e.key)
  }

  const downloadButton = (e, disabled) => canExport && (
    <Btn icon="download" disabled={disabled || undefined} onClick={() => actions.download(e.key)}
      aria-label={t('reports.work.downloadNamed', { name: reportName(e.key, t) })}>{t('reports.download')}</Btn>
  )

  const groups = reportGroups(entries, t).map((g) => ({
    ...g,
    items: g.entries.map((e) => ({
      id: e.key,
      title: reportName(e.key, t),
      kind: frequencyPill(e.schedule, t),
      facts: factsOf(e),
      due: e.next,
      dueLabel: compactDue(e.next, t),
      dueDate: formatDate(e.next, { time: true }),
      // A next run is no urgency: the due date stays neutral
      tone: '',
      onOpen: () => open(e),
      actions: (disabled) => downloadButton(e, disabled),
    })),
  }))
  const scheduledCount = entries.length - unscheduled.length

  const bulk = (canExport || canSchedule) ? (ids, clear) => (
    <>
      {canExport && <Btn icon="download" onClick={() => actions.downloadMany(ids)}>{t('reports.download')}</Btn>}
      {canSchedule && <Btn icon="block" write onClick={async () => { await actions.suspend(ids); clear() }}>{t('reports.work.suspend')}</Btn>}
    </>
  ) : undefined

  const dock = opened && (
    <ReportDock entry={opened} section={section} onSection={setSection} onClose={() => setOpenKey(null)} actions={actions} />
  )

  return (
    <Zone dock={dock} after={actions.dialog}>
      <PageHead title={t('reports.title')} total={state === 'ready' ? t('reports.work.total', { count: scheduledCount }) : ''}
        intent={t('reports.work.intent')}
        actions={(canExport || canSchedule) && (
          <>
            {canExport && <Btn icon="file" id="report-pdf" onClick={() => actions.openPdf('report-pdf')}>{t('reports.work.customPdf')}</Btn>}
            {canSchedule && <Btn tone="primary" icon="plus" id="report-schedule" data-action="report-schedule" onClick={() => actions.openSchedule()}>{t('reports.work.schedule')}</Btn>}
          </>
        )} />
      <WorkView
        label={t('reports.title')}
        state={state}
        error={(
          <LoadError id="reports" title={t('reports.loadFailed')} onRetry={() => load()} journal={hasPermission('read:audit') && '/audit'}
            cause={failure && <LoadCause error={{ status: failure.status, request: failure.status && 'GET /api/v2/reports/schedule', message: failure.message }} />} />
        )}
        hint={bulk ? t('reports.work.hint') : t('reports.work.hintRead')}
        groups={groups}
        bulk={bulk}
        openedId={openKey}
        empty={{
          title: t('reports.work.emptyTitle'),
          text: t('reports.work.emptyText'),
          action: canSchedule && <Btn icon="plus" data-action="report-schedule" onClick={() => actions.openSchedule()}>{t('reports.work.schedule')}</Btn>,
        }}
        history={{
          label: t('reports.work.unscheduled'),
          count: unscheduled.length,
          children: unscheduled.map((e) => (
            <RecordRow key={e.key}
              title={<button type="button" className="text-link" data-item={e.key} data-open={e.key} onClick={() => open(e)}>{reportName(e.key, t)}</button>}
              meta={reportDescription(e.key, t)}
              action={<>
                {downloadButton(e, false)}
                {canSchedule && (
                  <Btn icon="clock" write onClick={() => actions.openSchedule(e.key)}
                    aria-label={t('reports.work.scheduleNamed', { name: reportName(e.key, t) })}>{t('reports.work.scheduleAsk')}</Btn>
                )}
              </>} />
          )),
        }}
        after={canExport && <p className="phone-only"><Btn icon="file" onClick={() => actions.openPdf()}>{t('reports.work.customPdf')}</Btn></p>}
      />
    </Zone>
  )
}
