/**
 * ReportsPage — Report Generation & Scheduling
 * Generate, download, and schedule compliance reports.
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ChartBar, Download, PaperPlaneTilt, CalendarBlank, FileText,
  FileCsv, FileJs, Play, CheckCircle, Clock, Gear, FilePdf,
  Certificate, ShieldCheck, ClockCounterClockwise, Gavel, TreeStructure
} from '@phosphor-icons/react'
import {
  ResponsiveLayout, Card, Button, Badge, Input, Modal,
  LoadingSpinner, Select
} from '../components'
import { reportsService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { cn } from '../lib/utils'
import { getAppTimezone } from '../stores/timezoneStore'

const REPORT_ICONS = {
  certificate_inventory: Certificate,
  expiring_certificates: Clock,
  ca_hierarchy: TreeStructure,
  audit_summary: ClockCounterClockwise,
  compliance_status: Gavel,
}

const REPORT_VARIANTS = {
  certificate_inventory: 'info',
  expiring_certificates: 'warning',
  ca_hierarchy: 'success',
  audit_summary: 'default',
  compliance_status: 'danger',
}

export default function ReportsPage() {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const { canRead, canWrite } = usePermission()

  // Report types
  const [reportTypes, setReportTypes] = useState({})
  const [loading, setLoading] = useState(true)

  // Schedule
  const [schedule, setSchedule] = useState(null)
  const [scheduleLoading, setScheduleLoading] = useState(false)

  // Generation
  const [generating, setGenerating] = useState(null)
  const [generatedReport, setGeneratedReport] = useState(null)

  // Test send modal
  const [testSendModal, setTestSendModal] = useState(null)
  const [testEmail, setTestEmail] = useState('')
  const [testSending, setTestSending] = useState(false)

  // Schedule edit modal
  const [showScheduleModal, setShowScheduleModal] = useState(false)
  const [scheduleForm, setScheduleForm] = useState({})
  const [scheduleSaving, setScheduleSaving] = useState(false)
  const [recipientInputs, setRecipientInputs] = useState({})
  const [generatingPdf, setGeneratingPdf] = useState(false)

  // All schedulable report configs
  const SCHEDULE_REPORTS = useMemo(() => [
    { key: 'certificate_inventory', icon: Certificate, label: t('reports.types.certificate_inventory.name', { defaultValue: 'Certificate Inventory' }), variant: 'info' },
    { key: 'expiring_certificates', icon: Clock, label: t('reports.types.expiring_certificates.name', { defaultValue: 'Expiring Certificates' }), variant: 'warning' },
    { key: 'ca_hierarchy', icon: TreeStructure, label: t('reports.types.ca_hierarchy.name', { defaultValue: 'CA Hierarchy' }), variant: 'success' },
    { key: 'audit_summary', icon: ClockCounterClockwise, label: t('reports.types.audit_summary.name', { defaultValue: 'Audit Summary' }), variant: 'default' },
    { key: 'compliance_status', icon: Gavel, label: t('reports.types.compliance_status.name', { defaultValue: 'Compliance Status' }), variant: 'danger' },
    { key: 'executive_pdf', icon: FilePdf, label: t('reports.executiveReport'), variant: 'info', formatLocked: 'pdf' },
  ], [t])

  const hasWriteSettings = canWrite('settings')

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      const [typesRes, scheduleRes] = await Promise.all([
        reportsService.getTypes(),
        hasWriteSettings ? reportsService.getSchedule().catch(() => ({ data: null })) : Promise.resolve({ data: null }),
      ])
      setReportTypes(typesRes.data || {})
      if (scheduleRes.data) setSchedule(scheduleRes.data)
    } catch (err) {
      showError(t('reports.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [showError, t, hasWriteSettings])

  useEffect(() => { loadData() }, [loadData])

  const handleGenerate = async (reportType, format = 'json') => {
    try {
      setGenerating(reportType)
      const res = await reportsService.generate(reportType, { format, days: 30 })
      setGeneratedReport({ type: reportType, data: res.data })
      showSuccess(t('reports.generated'))
    } catch (err) {
      showError(t('reports.generateFailed'))
    } finally {
      setGenerating(null)
    }
  }

  const handleDownload = async (reportType, format = 'csv') => {
    try {
      setGenerating(reportType)
      const res = await reportsService.download(reportType, format, 30)

      // Create blob for download
      let content
      if (typeof res === 'string') {
        content = res
      } else if (res.data && typeof res.data === 'string') {
        content = res.data
      } else {
        content = JSON.stringify(res.data || res, null, 2)
      }
      const mimeType = format === 'csv' ? 'text/csv' : 'application/json'
      const blob = new Blob([content], { type: mimeType })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `ucm-report-${reportType}.${format}`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)

      showSuccess(t('reports.downloaded'))
    } catch (err) {
      showError(t('reports.downloadFailed'))
    } finally {
      setGenerating(null)
    }
  }

  const handleTestSend = async () => {
    const email = testEmail.trim()
    if (!email || !testSendModal) return
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      showError(t('reports.invalidEmail', { defaultValue: 'Invalid email address' }))
      return
    }
    try {
      setTestSending(true)
      await reportsService.sendTest(testSendModal, email)
      showSuccess(t('reports.testSent'))
      setTestSendModal(null)
      setTestEmail('')
    } catch (err) {
      showError(t('reports.testFailed'))
    } finally {
      setTestSending(false)
    }
  }

  const openScheduleModal = () => {
    // Initialize form from schedule data (new format: keyed by report type)
    const form = {}
    const inputs = {}
    SCHEDULE_REPORTS.forEach(r => {
      const s = schedule?.[r.key] || {}
      form[r.key] = {
        enabled: s.enabled || false,
        frequency: s.frequency || 'weekly',
        time: s.time || '08:00',
        day_of_week: s.day_of_week ?? 1,
        day_of_month: s.day_of_month ?? 1,
        recipients: s.recipients || [],
        format: r.formatLocked || s.format || 'csv',
      }
      inputs[r.key] = ''
    })
    setScheduleForm(form)
    setRecipientInputs(inputs)
    setShowScheduleModal(true)
  }

  const handleSaveSchedule = async () => {
    try {
      setScheduleSaving(true)
      await reportsService.updateSchedule(scheduleForm)
      showSuccess(t('reports.scheduleUpdated'))
      setShowScheduleModal(false)
      loadData()
    } catch (err) {
      showError(t('reports.scheduleFailed'))
    } finally {
      setScheduleSaving(false)
    }
  }

  const updateScheduleField = (key, field, value) => {
    setScheduleForm(prev => ({
      ...prev,
      [key]: { ...prev[key], [field]: value },
    }))
  }

  const addRecipient = (key) => {
    const email = (recipientInputs[key] || '').trim()
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return
    setScheduleForm(prev => ({
      ...prev,
      [key]: {
        ...prev[key],
        recipients: [...prev[key].recipients.filter(r => r !== email), email],
      },
    }))
    setRecipientInputs(prev => ({ ...prev, [key]: '' }))
  }

  const removeRecipient = (key, email) => {
    setScheduleForm(prev => ({
      ...prev,
      [key]: {
        ...prev[key],
        recipients: prev[key].recipients.filter(r => r !== email),
      },
    }))
  }

  const handleDownloadPDF = async () => {
    try {
      setGeneratingPdf(true)
      const response = await reportsService.downloadExecutivePDF()
      const blob = response instanceof Blob ? response : new Blob([response], { type: 'application/pdf' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `ucm-executive-report-${new Date().toISOString().slice(0, 10)}.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      showSuccess(t('reports.pdfGenerated'))
    } catch (err) {
      showError(t('reports.pdfFailed'))
    } finally {
      setGeneratingPdf(false)
    }
  }

  const reportEntries = Object.entries(reportTypes)
  const enabledSchedules = schedule ? SCHEDULE_REPORTS.filter(r => schedule[r.key]?.enabled).length : 0

  const stats = useMemo(() => [
    { icon: FileText, label: t('reports.dataReports'), value: reportEntries.length, variant: 'info' },
    { icon: CalendarBlank, label: t('reports.scheduledReports'), value: enabledSchedules, variant: 'success' },
    { icon: Download, label: t('reports.exportFormats'), value: 3, variant: 'default' },
    { icon: Clock, label: t('reports.expiryReport'), value: schedule?.expiry_report?.enabled ? t('common.enabled') : t('common.disabled'), variant: 'warning' },
  ], [reportEntries.length, enabledSchedules, schedule, t])

  if (loading) {
    return (
      <ResponsiveLayout title={t('reports.title')} subtitle={t('reports.subtitle')} icon={ChartBar} loading>
        <div className="flex items-center justify-center py-20">
          <LoadingSpinner size="lg" />
        </div>
      </ResponsiveLayout>
    )
  }

  // Parse report content and render a proper table + summary
  const renderReportPreview = (report) => {
    let parsed = report.data
    // Parse content if it's a nested JSON string
    if (parsed?.content && typeof parsed.content === 'string') {
      try { parsed = JSON.parse(parsed.content) } catch { /* keep original */ }
    }

    const items = parsed?.items || []
    const columns = parsed?.columns || []
    const summary = parsed?.summary || report.data?.summary || {}

    // Summary badges
    const summaryBadges = Object.entries(summary).map(([key, val]) => {
      const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
      let variant = 'default'
      if (key === 'valid' || key === 'passed' || key === 'root') variant = 'success'
      else if (key === 'overall_score' && val === 'healthy') variant = 'success'
      else if (key === 'expired' || key === 'failed' || key === 'revoked') variant = 'danger'
      else if (key === 'overall_score' && val === 'critical') variant = 'danger'
      else if (key === 'expiring' || key === 'warnings') variant = 'warning'
      else if (key === 'overall_score' && val === 'warning') variant = 'warning'
      else if (key === 'total' || key === 'total_events' || key === 'total_checks') variant = 'info'
      return (
        <Badge key={key} variant={variant} size="sm" className="text-xs">
          {label}: {typeof val === 'number' ? val.toLocaleString() : String(val)}
        </Badge>
      )
    })

    // Column display names
    const colLabel = (col) => col.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())

    // Format cell value
    const formatCell = (val, col) => {
      if (val === null || val === undefined) return '—'
      if (col === 'status') {
        const v = { valid: 'success', expired: 'danger', revoked: 'danger', expiring: 'warning', pass: 'success', fail: 'danger', warning: 'warning' }
        return <Badge variant={v[val] || 'default'} size="sm">{val}</Badge>
      }
      if (col === 'is_root') return val ? '✓ Root' : 'Intermediate'
      if (col === 'severity') {
        const v = { high: 'danger', medium: 'warning', none: 'default' }
        return <Badge variant={v[val] || 'default'} size="sm">{val}</Badge>
      }
      if (typeof val === 'boolean') return val ? '✓' : '✗'
      if (typeof val === 'object') return JSON.stringify(val)
      const str = String(val)
      return str.length > 60 ? str.slice(0, 57) + '…' : str
    }

    // For audit_summary which has a different structure (categories with data objects)
    if (report.type === 'audit_summary' && items.length > 0 && items[0]?.category) {
      return (
        <div className="space-y-3">
          {summaryBadges.length > 0 && (
            <div className="flex flex-wrap gap-2">{summaryBadges}</div>
          )}
          {items.map((item) => (
            <div key={item.category}>
              <h4 className="text-xs font-semibold text-text-primary mb-1 capitalize">{item.category}</h4>
              <div className="bg-bg-tertiary rounded-lg overflow-hidden">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border-primary">
                      <th className="text-left px-3 py-1.5 text-text-secondary font-medium">{item.category === 'actions' ? 'Action' : item.category === 'users' ? 'User' : 'Resource'}</th>
                      <th className="text-right px-3 py-1.5 text-text-secondary font-medium">Count</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(item.data || {}).map(([k, v]) => (
                      <tr key={k} className="border-b border-border-primary-op50 last:border-0">
                        <td className="px-3 py-1.5 text-text-primary font-mono">{k}</td>
                        <td className="px-3 py-1.5 text-text-primary text-right font-semibold">{v}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      )
    }

    // Standard table with items
    return (
      <div className="space-y-3">
        {summaryBadges.length > 0 && (
          <div className="flex flex-wrap gap-2">{summaryBadges}</div>
        )}
        {items.length > 0 && columns.length > 0 ? (
          <div className="bg-bg-tertiary rounded-lg overflow-auto max-h-96">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-bg-tertiary">
                <tr className="border-b border-border-primary">
                  {columns.map((col) => (
                    <th key={col} className="text-left px-3 py-2 text-text-secondary font-medium whitespace-nowrap">
                      {colLabel(col)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map((item, i) => (
                  <tr key={item.id || i} className="border-b border-border-primary-op50 last:border-0 hover:bg-secondary-op50">
                    {columns.map((col) => (
                      <td key={col} className="px-3 py-1.5 text-text-primary whitespace-nowrap">
                        {formatCell(item[col], col)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : items.length === 0 ? (
          <p className="text-xs text-text-tertiary italic py-2">{t('common.noData')}</p>
        ) : null}
        <p className="text-xs text-text-tertiary">
          {t('common.countItems', { count: items.length })} • {t('reports.generatedAt')} {new Date().toLocaleString(undefined, { timeZone: getAppTimezone() })}
        </p>
      </div>
    )
  }

  return (
    <>
      <ResponsiveLayout
        title={t('reports.title')}
        subtitle={t('reports.subtitle')}
        icon={ChartBar}
        helpPageKey="reports"
        stats={stats}
        actions={
          <div className="flex items-center gap-2">
            <Button type="button" onClick={handleDownloadPDF} disabled={generatingPdf}>
              {generatingPdf ? <LoadingSpinner size="sm" /> : (
                <><FilePdf size={16} className="mr-1.5" /> {t('reports.downloadPDF')}</>
              )}
            </Button>
            {canWrite('settings') && (
              <Button type="button" variant="secondary" onClick={openScheduleModal}>
                <Gear size={16} className="mr-1.5" /> {t('reports.scheduleReports')}
              </Button>
            )}
          </div>
        }
      >
        <div className="space-y-6">
        {/* Data Reports — list format matching other pages */}
        <Card>
          <div className="px-4 py-3 border-b border-border flex items-center justify-between">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <ChartBar size={16} className="text-accent-primary" />
              {t('reports.dataReports')}
            </h3>
            <span className="text-xs text-text-muted">{reportEntries.length} {t('reports.available')}</span>
          </div>
          <div className="divide-y divide-border">
            {reportEntries.map(([key, report]) => {
              const Icon = REPORT_ICONS[key] || FileText
              const variant = REPORT_VARIANTS[key] || 'default'
              const isGenerating = generating === key

              return (
                <div key={key} className="flex items-center gap-4 px-4 py-3 hover:bg-secondary-op50 transition-colors">
                  <div className={cn(
                    'w-8 h-8 rounded-lg flex items-center justify-center shrink-0',
                    variant === 'info' ? 'icon-bg-blue' :
                    variant === 'warning' ? 'icon-bg-yellow' :
                    variant === 'success' ? 'icon-bg-green' :
                    variant === 'danger' ? 'icon-bg-red' :
                    'icon-bg-gray'
                  )}>
                    <Icon size={18} weight="duotone" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-text-primary">
                      {t(`reports.types.${key}.name`, { defaultValue: report.name })}
                    </div>
                    <div className="text-xs text-text-muted mt-0.5 truncate">
                      {t(`reports.types.${key}.description`, { defaultValue: report.description })}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <Button
                      size="sm"
                      onClick={() => handleGenerate(key)}
                      disabled={isGenerating}
                    >
                      {isGenerating ? <LoadingSpinner size="sm" /> : (
                        <><Play size={14} className="mr-1" /> {t('reports.generate')}</>
                      )}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      onClick={() => handleDownload(key, 'csv')}
                      disabled={isGenerating}
                      aria-label={t('reports.downloadCSV')}
                    >
                      <FileCsv size={16} />
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      onClick={() => handleDownload(key, 'json')}
                      disabled={isGenerating}
                      aria-label={t('reports.downloadJSON')}
                    >
                      <FileJs size={16} />
                    </Button>
                    {canWrite('settings') && (
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        onClick={() => { setTestSendModal(key); setTestEmail('') }}
                        aria-label={t('reports.testSend')}
                      >
                        <PaperPlaneTilt size={16} />
                      </Button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </Card>

        {/* Schedule Status — all 6 report types */}
        {schedule && (
          <Card>
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <CalendarBlank size={16} className="text-accent-primary" />
                {t('reports.scheduledReports')}
              </h3>
              {canWrite('settings') && (
                <Button type="button" size="sm" variant="secondary" onClick={openScheduleModal}>
                  <Gear size={14} className="mr-1" /> {t('common.configure')}
                </Button>
              )}
            </div>
            <div className="divide-y divide-border">
              {SCHEDULE_REPORTS.map(r => {
                const s = schedule[r.key] || {}
                const Icon = r.icon
                const freqLabel = s.frequency === 'daily' ? t('reports.daily')
                  : s.frequency === 'monthly' ? t('reports.monthly')
                  : t('reports.weekly')
                return (
                  <div key={r.key} className="flex items-center gap-4 px-4 py-2.5">
                    <Icon size={18} className={`shrink-0 ${s.enabled ? 'text-accent-primary' : 'text-text-muted'}`} />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-text-primary">{r.label}</div>
                      {s.enabled && (
                        <div className="text-xs text-text-muted mt-0.5 truncate">
                          {freqLabel} · {s.time || '08:00'}
                          {s.recipients?.length > 0 && <> · {s.recipients.join(', ')}</>}
                        </div>
                      )}
                    </div>
                    <Badge variant={s.enabled ? 'success' : 'default'} size="sm">
                      {s.enabled ? t('common.enabled') : t('common.disabled')}
                    </Badge>
                  </div>
                )
              })}
            </div>
          </Card>
        )}

        {/* Generated Report Preview */}
        {generatedReport && (
          <Card>
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <CheckCircle size={16} className="text-status-success" weight="fill" />
                {t('reports.generatedPreview')} — {reportTypes[generatedReport.type]?.name}
              </h3>
              <div className="flex items-center gap-2">
                <Button type="button" size="sm" variant="primary" onClick={() => handleDownload(generatedReport.type, 'csv')}>
                  <FileCsv size={14} className="mr-1" /> CSV
                </Button>
                <Button type="button" size="sm" variant="primary" onClick={() => handleDownload(generatedReport.type, 'json')}>
                  <FileJs size={14} className="mr-1" /> JSON
                </Button>
                <Button type="button" size="sm" variant="secondary" onClick={() => setGeneratedReport(null)}>
                  {t('common.close')}
                </Button>
              </div>
            </div>
            <div className="p-4">
              {renderReportPreview(generatedReport)}
            </div>
          </Card>
        )}
        </div>
      </ResponsiveLayout>

      {/* Test Send Modal */}
      <Modal
        open={!!testSendModal}
        onOpenChange={(open) => { if (!open) { setTestSendModal(null); setTestEmail('') } }}
        title={t('reports.testSend')}
        size="sm"
      >
        <div className="p-4 space-y-4">
          <p className="text-sm text-text-secondary">
            {t('reports.testSendDesc', { type: reportTypes[testSendModal]?.name || testSendModal })}
          </p>
          <Input
            label={t('reports.recipientEmail')}
            type="email"
            value={testEmail}
            onChange={(e) => setTestEmail(e.target.value)}
            placeholder="admin@example.com"
            required
          />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => { setTestSendModal(null); setTestEmail('') }}>
              {t('common.cancel')}
            </Button>
            <Button type="button" onClick={handleTestSend} disabled={testSending || !testEmail.trim()}>
              {testSending ? <LoadingSpinner size="sm" /> : (
                <><PaperPlaneTilt size={14} className="mr-1" /> {t('reports.send')}</>
              )}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Schedule Modal — all 6 report types with full config */}
      <Modal
        open={showScheduleModal}
        onOpenChange={(open) => { if (!open) setShowScheduleModal(false) }}
        title={t('reports.scheduleReports')}
        size="lg"
      >
        <div className="p-4 space-y-4 max-h-[70vh] overflow-y-auto">
          {SCHEDULE_REPORTS.map((r, idx) => {
            const form = scheduleForm[r.key] || {}
            const Icon = r.icon
            return (
              <div key={r.key} className={idx > 0 ? 'border-t border-border pt-4' : ''}>
                {/* Report header with toggle */}
                <div className="flex items-center gap-3 mb-2">
                  <label className="flex items-center gap-2 cursor-pointer flex-1 min-w-0">
                    <input
                      type="checkbox"
                      checked={form.enabled || false}
                      onChange={(e) => updateScheduleField(r.key, 'enabled', e.target.checked)}
                      className="rounded border-border"
                    />
                    <Icon size={18} className="text-accent-primary shrink-0" />
                    <span className="text-sm font-medium text-text-primary truncate">{r.label}</span>
                  </label>
                </div>

                {/* Expanded config when enabled */}
                {form.enabled && (
                  <div className="pl-8 space-y-3">
                    {/* Frequency + Time row */}
                    <div className="flex flex-wrap gap-3 items-end">
                      <div>
                        <label className="text-xs text-text-muted mb-1 block">{t('reports.frequency')}</label>
                        <select
                          value={form.frequency || 'weekly'}
                          onChange={(e) => updateScheduleField(r.key, 'frequency', e.target.value)}
                          className="bg-bg-secondary border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary"
                        >
                          <option value="daily">{t('reports.daily')}</option>
                          <option value="weekly">{t('reports.weekly')}</option>
                          <option value="monthly">{t('reports.monthly')}</option>
                        </select>
                      </div>
                      <div>
                        <label className="text-xs text-text-muted mb-1 block">{t('reports.time')}</label>
                        <input
                          type="time"
                          value={form.time || '08:00'}
                          onChange={(e) => updateScheduleField(r.key, 'time', e.target.value)}
                          className="bg-bg-secondary border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary"
                        />
                      </div>
                      {form.frequency === 'weekly' && (
                        <div>
                          <label className="text-xs text-text-muted mb-1 block">{t('reports.dayOfWeek')}</label>
                          <select
                            value={form.day_of_week ?? 1}
                            onChange={(e) => updateScheduleField(r.key, 'day_of_week', parseInt(e.target.value))}
                            className="bg-bg-secondary border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary"
                          >
                            {[t('reports.days.mon'), t('reports.days.tue'), t('reports.days.wed'), t('reports.days.thu'), t('reports.days.fri'), t('reports.days.sat'), t('reports.days.sun')].map((day, i) => (
                              <option key={i} value={i}>{day}</option>
                            ))}
                          </select>
                        </div>
                      )}
                      {form.frequency === 'monthly' && (
                        <div>
                          <label className="text-xs text-text-muted mb-1 block">{t('reports.dayOfMonth')}</label>
                          <select
                            value={form.day_of_month ?? 1}
                            onChange={(e) => updateScheduleField(r.key, 'day_of_month', parseInt(e.target.value))}
                            className="bg-bg-secondary border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary"
                          >
                            {Array.from({ length: 28 }, (_, i) => i + 1).map(d => (
                              <option key={d} value={d}>{d}</option>
                            ))}
                          </select>
                        </div>
                      )}
                      {!r.formatLocked && (
                        <div>
                          <label className="text-xs text-text-muted mb-1 block">{t('reports.format')}</label>
                          <select
                            value={form.format || 'csv'}
                            onChange={(e) => updateScheduleField(r.key, 'format', e.target.value)}
                            className="bg-bg-secondary border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary"
                          >
                            <option value="csv">CSV</option>
                            <option value="json">JSON</option>
                          </select>
                        </div>
                      )}
                      {r.formatLocked && (
                        <div>
                          <label className="text-xs text-text-muted mb-1 block">{t('reports.format')}</label>
                          <span className="inline-block bg-bg-secondary border border-border rounded-md px-2.5 py-1.5 text-sm text-text-muted">PDF</span>
                        </div>
                      )}
                    </div>

                    {/* Recipients */}
                    <div>
                      <label className="text-xs text-text-muted mb-1 block">{t('reports.recipients')}</label>
                      <div className="flex gap-2 mb-2">
                        <Input
                          value={recipientInputs[r.key] || ''}
                          onChange={(e) => setRecipientInputs(prev => ({ ...prev, [r.key]: e.target.value }))}
                          placeholder="email@example.com"
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.preventDefault()
                              addRecipient(r.key)
                            }
                          }}
                          className="flex-1"
                        />
                        <Button type="button" size="sm" variant="secondary" onClick={() => addRecipient(r.key)}>
                          {t('common.add')}
                        </Button>
                      </div>
                      {form.recipients?.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                          {form.recipients.map(email => (
                            <Badge key={email} variant="default" size="sm" className="pr-1">
                              {email}
                              <button
                                type="button"
                                onClick={() => removeRecipient(r.key, email)}
                                className="ml-1.5 text-text-muted hover:text-status-danger"
                              >×</button>
                            </Badge>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )
          })}

          {/* Footer */}
          <div className="flex justify-end gap-2 pt-4 border-t border-border">
            <Button type="button" variant="secondary" onClick={() => setShowScheduleModal(false)}>
              {t('common.cancel')}
            </Button>
            <Button type="button" onClick={handleSaveSchedule} disabled={scheduleSaving}>
              {scheduleSaving ? <LoadingSpinner size="sm" /> : t('common.save')}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}
