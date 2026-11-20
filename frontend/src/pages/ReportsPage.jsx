/**
 * ReportsPage: the scheduled reports as a work queue grouped by next run, each
 * downloadable now; the reports without a schedule in the folded section below,
 * downloadable and schedulable. A name opens the report in the inspector
 * (schedule, runs, preview). Page actions: build a PDF, schedule a report.
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { DownloadSimple, Plus, FilePdf, PauseCircle, Clock } from '@phosphor-icons/react'
import { ResponsiveLayout } from '../components'
import { WorkQueue, WorkButton, WorkRecord, WorkRecords, loadCause } from '../components/work'
import { reportsService, certificatesService } from '../services'
import { useInspector } from '../contexts'
import { usePermission } from '../hooks'
import { useOpenEntity } from '../hooks/useOpenEntity'
import { formatDate } from '../lib/utils'
import { compactDue } from '../lib/relativeTime'
import {
  REPORT_KEYS, reportName, reportDescription, scheduleOf, reportGroups, frequencyPill, formatLabel, reportFigure,
} from './reports/reportModel'
import { useReportActions } from './reports/useReportActions'

export default function ReportsPage() {
  const { t } = useTranslation()
  const { hasPermission, canWrite, canRead } = usePermission()
  const inspector = useInspector()
  const openEntity = useOpenEntity()
  const root = useRef(null)

  const [schedules, setSchedules] = useState({})
  const [pdfSections, setPdfSections] = useState([])
  const [state, setState] = useState('loading')
  const [failure, setFailure] = useState(null)
  const [stats, setStats] = useState(null)
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
  const open = (e) => openEntity('report', e.key, { data: e })
  const activeKey = inspector?.activeKey || ''
  const openedId = activeKey.startsWith('report:') ? activeKey.slice(7) : undefined

  const downloadButton = (e, disabled) => canExport && (
    <WorkButton icon={DownloadSimple} disabled={disabled} onClick={() => actions.download(e.key)}
      aria-label={t('reports.work.downloadNamed', { name: reportName(e.key, t) })}>{t('reports.download')}</WorkButton>
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

  const bulkActions = (canExport || canSchedule) ? (ids, clear) => (
    <>
      {canExport && <WorkButton icon={DownloadSimple} onClick={() => actions.downloadMany(ids)}>{t('reports.download')}</WorkButton>}
      {canSchedule && <WorkButton icon={PauseCircle} onClick={async () => { await actions.suspend(ids); clear() }}>{t('reports.work.suspend')}</WorkButton>}
    </>
  ) : undefined

  return (
    <>
      <ResponsiveLayout
        className="wk-page"
        title={t('reports.title')}
        total={state === 'ready' ? t('reports.work.total', { count: scheduledCount }) : ''}
        intent={t('reports.work.intent')}
        helpPageKey="reports"
        actions={(canExport || canSchedule) && (
          <>
            {canExport && (
              <WorkButton quiet icon={FilePdf} onClick={actions.openPdf} className="lv-hide-mobile"
                aria-label={t('reports.work.customPdf')}>{t('reports.work.customPdf')}</WorkButton>
            )}
            {canSchedule && <WorkButton primary icon={Plus} onClick={() => actions.openSchedule()}>{t('reports.work.schedule')}</WorkButton>}
          </>
        )}
      >
        <WorkQueue
          rootRef={root}
          label={t('reports.title')}
          state={state}
          error={{ title: t('reports.loadFailed'), cause: loadCause(failure, t), onRetry: () => load(), journal: hasPermission('read:audit') && '/audit' }}
          hint={bulkActions ? t('reports.work.hint') : t('reports.work.hintRead')}
          groups={groups}
          bulkActions={bulkActions}
          openedId={openedId}
          empty={{
            title: t('reports.work.emptyTitle'),
            text: t('reports.work.emptyText'),
            action: canSchedule && <WorkButton icon={Plus} onClick={() => actions.openSchedule()}>{t('reports.work.schedule')}</WorkButton>,
          }}
          history={{
            label: t('reports.work.unscheduled'),
            count: unscheduled.length,
            children: (
              <WorkRecords empty={t('work.historyEmpty')}>
                {unscheduled.map((e) => (
                  <WorkRecord key={e.key}
                    title={<button type="button" className="wk-subject" onClick={() => open(e)}>{reportName(e.key, t)}</button>}
                    meta={reportDescription(e.key, t)}
                    action={<>
                      {downloadButton(e, false)}
                      {canSchedule && (
                        <WorkButton icon={Clock} onClick={() => actions.openSchedule(e.key)}
                          aria-label={t('reports.work.scheduleNamed', { name: reportName(e.key, t) })}>{t('reports.work.scheduleAsk')}</WorkButton>
                      )}
                    </>} />
                ))}
              </WorkRecords>
            ),
          }}
        />
      </ResponsiveLayout>
      {actions.dialog}
    </>
  )
}
