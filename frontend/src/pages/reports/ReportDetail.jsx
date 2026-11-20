/**
 * Report in the inspector: heading (schedule state, Download, « ⋯ » for the rest),
 * then the Report, Runs and Preview sections. The server keeps no run history it
 * serves: Runs says so; Preview generates the report now.
 */
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { DownloadSimple, Clock, PaperPlaneTilt, PauseCircle, CaretRight, Play } from '@phosphor-icons/react'
import { StatusPill } from '../../components/list'
import { WorkButton, ChartIcon } from '../../components/work'
import { SectionTabs, tabId, panelId } from '../../components/inspector/InspectorTabs'
import { MoreActionsMenu } from '../../components/inspector/certificate/MoreActionsMenu'
import { usePermission } from '../../hooks'
import { reportsService, certificatesService } from '../../services'
import { formatDate } from '../../lib/utils'
import {
  isPdf, reportName, nextRun, frequencyLong, formatLabel, scheduleOf, scheduleState, parseReport, reportFigure, CERTIFICATE_LINKS,
} from './reportModel'
import { useReportActions } from './useReportActions'
import { ReportPreview } from './ReportPreview'
import '../../components/work/work.css'

function Props({ rows }) {
  return (
    <dl className="ins-props">
      {rows.filter(Boolean).map(([k, v]) => <div key={k} style={{ display: 'contents' }}><dt>{k}</dt><dd>{v}</dd></div>)}
    </dl>
  )
}

export function ReportDetail({ data, objectKey, title, section, onSection, onChanged }) {
  const { t } = useTranslation()
  const { hasPermission, canWrite, canRead } = usePermission()
  const { key } = data
  const schedule = scheduleOf({ [key]: data.schedule }, key)
  const canExport = hasPermission('export:audit')
  const canSchedule = canWrite('settings')
  const [report, setReport] = useState(null)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)
  const [figure, setFigure] = useState(null)
  const more = useRef(null)
  // A figure the certificate counters already hold is shown as it is, without computing the report
  const counted = key === 'expiring_certificates' && canRead('certificates')
  useEffect(() => {
    if (!counted) return undefined
    let live = true
    Promise.resolve(certificatesService?.getStats?.())
      .then((res) => { if (live) setFigure(reportFigure(key, res?.data, t)) })
      .catch(() => {})
    return () => { live = false }
  }, [counted, key, t])
  const fromMenu = () => more.current?.querySelector('button')
  const actions = useReportActions({
    schedules: { [key]: schedule },
    onDone: () => reportsService.getSchedule().then((res) => onChanged?.({ key, schedule: scheduleOf(res?.data, key) })).catch(() => {}),
  })

  const generate = async () => {
    setBusy(true); setFailed(false)
    try {
      const res = await reportsService.generate(key, { format: 'json', days: 30 })
      setReport(parseReport(res?.data))
    } catch {
      setFailed(true)
    } finally {
      setBusy(false)
    }
  }

  const next = nextRun(schedule)
  const menu = [
    canSchedule && { id: 'schedule', icon: Clock, label: t(schedule.enabled ? 'reports.work.editSchedule' : 'reports.work.scheduleAsk'), onClick: () => actions.openSchedule(key, fromMenu) },
    canSchedule && schedule.enabled && { id: 'suspend', icon: PauseCircle, label: t('reports.work.suspend'), onClick: () => actions.suspend([key]) },
    canSchedule && { id: 'test', icon: PaperPlaneTilt, label: t('reports.work.testAsk'), onClick: () => actions.openTest(key, fromMenu) },
  ].filter(Boolean)
  const certLink = CERTIFICATE_LINKS[key]

  return (
    <>
      <header className="ins-heading">
        <div className="ins-title">
          <ChartIcon className="ins-title-icon" aria-hidden="true" />
          <h2>{title}</h2>
          <StatusPill {...scheduleState(schedule, t)} />
        </div>
        <div className="ins-actions">
          {canExport && <WorkButton icon={DownloadSimple} onClick={() => actions.download(key)}>{t('reports.download')}</WorkButton>}
          <span ref={more} style={{ display: 'contents' }}>
            <MoreActionsMenu items={menu} label={t('inspector.moreActions', { name: title })}
              title={t('reports.work.actionsTitle')} name={title} />
          </span>
        </div>
      </header>
      <SectionTabs objectKey={objectKey} sections={['report', 'runs', 'preview']} current={section} onSelect={onSection}
        labelOf={(s) => t(`reports.work.sections.${s}`)} />
      <div role="tabpanel" id={`${panelId(objectKey)}-section`} aria-labelledby={`${tabId(objectKey)}-${section}`}
        className="ins-panel" tabIndex={0}>
        {section === 'report' && (
          <div className="wk-detail-grid">
            <section>
              <h3 className="ins-section-title">{t('reports.work.detail.schedule')}</h3>
              <Props rows={[
                [t('reports.work.dialog.content'), reportName(key, t)],
                [t('reports.frequency'), schedule.enabled ? frequencyLong(schedule, t) : <span className="ins-muted">{t('reports.work.state.unscheduled')}</span>],
                schedule.enabled && [t('reports.work.detail.next'), next ? formatDate(next, { time: true }) : '—'],
                [t('reports.recipients'), schedule.recipients?.length ? schedule.recipients.join(', ') : <span className="ins-muted">{t('reports.work.noRecipient')}</span>],
                [t('reports.format'), formatLabel(key, schedule)],
              ]} />
            </section>
            {!isPdf(key) && (
              <section>
                <h3 className="ins-section-title">{t('reports.work.detail.figure')}</h3>
                {figure ? (
                  <>
                    <p className="wk-figure"><strong>{figure}</strong></p>
                    <p className="ins-muted">{t('reports.work.figure.expiringNote', { days: 30 })}</p>
                  </>
                ) : report ? (
                  <>
                    <p className="wk-figure"><strong>{t('reports.work.items', { count: report.items.length })}</strong></p>
                    <p className="ins-muted">{t('reports.work.generatedAt', { date: formatDate(report.generatedAt, { time: true }) })}</p>
                  </>
                ) : (
                  <WorkButton icon={Play} disabled={!canExport || busy} onClick={generate}>{t('reports.work.compute')}</WorkButton>
                )}
                {failed && <p className="ins-notice is-bad" role="alert">{t('reports.generateFailed')}</p>}
                {certLink && (
                  <p>
                    <Link className="lv-text-link" to={certLink}><CaretRight size={14} aria-hidden="true" />{t('reports.work.seeCertificates')}</Link>
                  </p>
                )}
              </section>
            )}
          </div>
        )}
        {section === 'runs' && <p className="wk-none">{t('reports.work.noRuns')}</p>}
        {section === 'preview' && (
          isPdf(key) ? (
            <p className="wk-none">{t('reports.work.pdfPreview')}</p>
          ) : (
            <ReportPreview report={report} busy={busy} failed={failed} canGenerate={canExport} onGenerate={generate} />
          )
        )}
      </div>
      {actions.dialog}
    </>
  )
}

export default ReportDetail
