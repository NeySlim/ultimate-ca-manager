/**
 * A report in the module dock: the mockup's moduleInspector() for reports, reportPanel()
 * (Planification, Chiffre actuel) and reportRunsPanel() (Exécutions). The server keeps no run
 * history it serves (G06): Exécutions says so and the « Dernière exécution » section is left out.
 * The product's Aperçu tab comes last; its further actions sit behind the heading's « ⋯ ».
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, Dock, DockBody, Facts, Icon, IconBtn, Pill, Section, TextLink } from '../../components/atelier'
import { usePermission } from '../../hooks'
import { reportsService, certificatesService } from '../../services'
import { formatDate } from '../../lib/utils'
import {
  isPdf, reportName, nextRun, frequencyLong, formatLabel, scheduleOf, scheduleState, parseReport, reportFigure, CERTIFICATE_LINKS,
} from './reportModel'
import { ReportPreview } from './ReportPreview'

/** The dock of the open report. `actions` is the page's useReportActions(). */
export function ReportDock({ entry, section, onSection, onClose, actions }) {
  const { t } = useTranslation()
  const { hasPermission, canWrite, canRead } = usePermission()
  const { key } = entry
  const schedule = scheduleOf({ [key]: entry.schedule }, key)
  const canExport = hasPermission('export:audit')
  const canSchedule = canWrite('settings')
  const title = reportName(key, t)
  const state = scheduleState(schedule, t)
  const [report, setReport] = useState(null)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)
  const [figure, setFigure] = useState(null)
  // A figure the certificate counters already hold is shown as it is, without computing the report
  const counted = key === 'expiring_certificates' && canRead('certificates')
  useEffect(() => {
    setReport(null); setFailed(false); setFigure(null)
    if (!counted) return undefined
    let live = true
    Promise.resolve(certificatesService?.getStats?.())
      .then((res) => { if (live) setFigure(reportFigure(key, res?.data, t)) })
      .catch(() => {})
    return () => { live = false }
  }, [counted, key, t])

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
    canSchedule && { id: 'schedule', icon: 'clock', label: t(schedule.enabled ? 'reports.work.editSchedule' : 'reports.work.scheduleAsk'), onClick: () => actions.openSchedule(key, 'report-more') },
    canSchedule && schedule.enabled && { id: 'suspend', icon: 'block', label: t('reports.work.suspend'), onClick: () => actions.suspend([key]) },
    canSchedule && { id: 'test', icon: 'send', label: t('reports.work.testAsk'), onClick: () => actions.openTest(key, 'report-more') },
  ].filter(Boolean)
  const certLink = CERTIFICATE_LINKS[key]

  return (
    <Dock label={t('atelier.detailOf', { name: t('reports.title') })} tabsLabel={t('atelier.openItem')} activeKey={key}
      tabs={[{ key, title, icon: 'chart' }]} onClose={onClose}>
      <DockBody icon="chart" title={title} badge={<Pill label={state.label} tone={state.tone} />}
        actions={<>
          {canExport && <Btn icon="download" id="report-download" onClick={() => actions.download(key)}>{t('reports.download')}</Btn>}
          {menu.length > 0 && (
            <IconBtn quiet icon="more" id="report-more" label={t('inspector.moreActions', { name: title })} onClick={() => actions.openMenu(key, menu)} />
          )}
        </>}
        sections={[['report', t('reports.work.sections.report')], ['runs', t('reports.work.sections.runs')], ['preview', t('reports.work.sections.preview')]]}
        section={section} onSection={onSection} sectionsLabel={t('atelier.sectionsOf', { name: title })}>
        {section === 'report' && (
          <div className="module-detail">
            <Section title={t('reports.work.detail.schedule')}>
              <Facts items={[
                [t('reports.work.dialog.content'), title],
                schedule.enabled ? [t('reports.frequency'), frequencyLong(schedule, t)] : { label: t('reports.frequency'), absent: t('reports.work.state.unscheduled') },
                schedule.enabled && (next ? [t('reports.work.detail.next'), formatDate(next, { time: true })] : { label: t('reports.work.detail.next'), absent: '—' }),
                schedule.recipients?.length
                  ? { label: t('reports.recipients'), value: schedule.recipients.join(', '), long: schedule.recipients.length > 1 }
                  : { label: t('reports.recipients'), absent: t('reports.work.noRecipient') },
                [t('reports.format'), formatLabel(key, schedule)],
              ]} />
            </Section>
            {!isPdf(key) && (
              <Section title={t('reports.work.detail.figure')}>
                {figure ? (
                  <>
                    <p className="report-figure"><strong>{figure}</strong></p>
                    <p className="small muted">{t('reports.work.figure.expiringNote', { days: 30 })}</p>
                  </>
                ) : report ? (
                  <>
                    <p className="report-figure"><strong>{t('reports.work.items', { count: report.items.length })}</strong></p>
                    <p className="small muted">{t('reports.work.generatedAt', { date: formatDate(report.generatedAt, { time: true }) })}</p>
                  </>
                ) : (
                  <p><Btn icon="refresh" disabled={!canExport || busy || undefined} onClick={generate}>{t('reports.work.compute')}</Btn></p>
                )}
                {failed && <p className="notice warn" role="alert"><Icon name="warning" />{t('reports.generateFailed')}</p>}
                {certLink && <TextLink iconFirst icon="right" to={certLink}>{t('reports.work.seeCertificates')}</TextLink>}
              </Section>
            )}
          </div>
        )}
        {section === 'runs' && <p className="muted small">{t('reports.work.noRuns')}</p>}
        {section === 'preview' && (
          isPdf(key) ? <p className="muted small">{t('reports.work.pdfPreview')}</p>
            : <ReportPreview report={report} busy={busy} failed={failed} canGenerate={canExport} onGenerate={generate} />
        )}
      </DockBody>
    </Dock>
  )
}
