/**
 * ReportsPage — Report Generation & Scheduling
 * Sidebar tab layout: Data Reports, Schedule, Executive Report.
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ChartBar, Download, PaperPlaneTilt, CalendarBlank, FileText,
  FileCsv, FileJs, Play, CheckCircle, Clock, Gear, FilePdf,
  Certificate, ShieldCheck, ClockCounterClockwise, Gavel, TreeStructure,
  Checks, SlidersHorizontal, FileArrowDown
} from '@phosphor-icons/react'
import {
  ResponsiveLayout, Card, Button, Badge, Input, Modal,
  LoadingSpinner, Select
} from '../components'
import { reportsService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { cn, formatDate , downloadBlob} from '../lib/utils'

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

  const [activeTab, setActiveTab] = useState('reports')

  // Report types
  const [reportTypes, setReportTypes] = useState({})
  const [loading, setLoading] = useState(true)

  // Schedule
  const [schedule, setSchedule] = useState(null)

  // Generation
  const [generating, setGenerating] = useState(null)
  const [generatedReport, setGeneratedReport] = useState(null)

  // Test send modal
  const [testSendModal, setTestSendModal] = useState(null)
  const [testEmail, setTestEmail] = useState('')
  const [testSending, setTestSending] = useState(false)

  // Schedule form (inline in schedule tab)
  const [scheduleForm, setScheduleForm] = useState({})
  const [scheduleSaving, setScheduleSaving] = useState(false)
  const [recipientInputs, setRecipientInputs] = useState({})
  const [generatingPdf, setGeneratingPdf] = useState(false)

  // PDF Reports tab
  const [pdfTemplates, setPdfTemplates] = useState({})
  const [pdfSections, setPdfSections] = useState([])
  const [selectedSections, setSelectedSections] = useState([])
  const [generatingCustomPdf, setGeneratingCustomPdf] = useState(null)

  // All schedulable report configs — data reports + PDF templates
  const SCHEDULE_REPORTS = useMemo(() => [
    // Data reports (CSV/JSON)
    { key: 'certificate_inventory', icon: Certificate, label: t('reports.types.certificate_inventory.name', { defaultValue: 'Certificate Inventory' }), variant: 'info', group: 'data' },
    { key: 'expiring_certificates', icon: Clock, label: t('reports.types.expiring_certificates.name', { defaultValue: 'Expiring Certificates' }), variant: 'warning', group: 'data' },
    { key: 'ca_hierarchy', icon: TreeStructure, label: t('reports.types.ca_hierarchy.name', { defaultValue: 'CA Hierarchy' }), variant: 'success', group: 'data' },
    { key: 'audit_summary', icon: ClockCounterClockwise, label: t('reports.types.audit_summary.name', { defaultValue: 'Audit Summary' }), variant: 'default', group: 'data' },
    { key: 'compliance_status', icon: Gavel, label: t('reports.types.compliance_status.name', { defaultValue: 'Compliance Status' }), variant: 'danger', group: 'data' },
    // PDF templates
    { key: 'pdf_executive', icon: FilePdf, label: t('reports.pdf.template.executive.name', { defaultValue: 'Executive Summary' }), variant: 'purple', formatLocked: 'pdf', group: 'pdf' },
    { key: 'pdf_certificate_inventory', icon: FilePdf, label: t('reports.pdf.template.certificate_inventory.name', { defaultValue: 'Certificate Inventory' }), variant: 'purple', formatLocked: 'pdf', group: 'pdf' },
    { key: 'pdf_compliance', icon: FilePdf, label: t('reports.pdf.template.compliance.name', { defaultValue: 'Compliance Report' }), variant: 'purple', formatLocked: 'pdf', group: 'pdf' },
    { key: 'pdf_ca_overview', icon: FilePdf, label: t('reports.pdf.template.ca_overview.name', { defaultValue: 'CA Overview' }), variant: 'purple', formatLocked: 'pdf', group: 'pdf' },
    { key: 'pdf_security_audit', icon: FilePdf, label: t('reports.pdf.template.security_audit.name', { defaultValue: 'Security & Audit' }), variant: 'purple', formatLocked: 'pdf', group: 'pdf' },
  ], [t])

  const hasWriteSettings = canWrite('settings')

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      const [typesRes, scheduleRes, pdfRes] = await Promise.all([
        reportsService.getTypes(),
        hasWriteSettings ? reportsService.getSchedule().catch(() => ({ data: null })) : Promise.resolve({ data: null }),
        reportsService.getPdfTemplates().catch(() => ({ data: null })),
      ])
      setReportTypes(typesRes.data || {})
      if (scheduleRes.data) setSchedule(scheduleRes.data)
      if (pdfRes.data) {
        setPdfTemplates(pdfRes.data.templates || {})
        setPdfSections(pdfRes.data.sections || [])
      }
    } catch (err) {
      showError(t('reports.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [showError, t, hasWriteSettings])

  useEffect(() => { loadData() }, [loadData])

  // Initialize schedule form when switching to the schedule tab
  useEffect(() => {
    if (activeTab !== 'schedule') return
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
  }, [activeTab, schedule, SCHEDULE_REPORTS])

  const handleGenerate = useCallback(async (reportType, format = 'json') => {
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
  }, [showSuccess, showError, t])

  const handleDownload = useCallback(async (reportType, format = 'csv') => {
    try {
      setGenerating(reportType)
      const res = await reportsService.download(reportType, format, 30)

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
      downloadBlob(blob, `ucm-report-${reportType}.${format}`)

      showSuccess(t('reports.downloaded'))
    } catch (err) {
      showError(t('reports.downloadFailed'))
    } finally {
      setGenerating(null)
    }
  }, [showSuccess, showError, t])

  const handleTestSend = useCallback(async () => {
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
  }, [testEmail, testSendModal, showSuccess, showError, t])

  const handleSaveSchedule = useCallback(async () => {
    try {
      setScheduleSaving(true)
      await reportsService.updateSchedule(scheduleForm)
      showSuccess(t('reports.scheduleUpdated'))
      loadData()
    } catch (err) {
      showError(t('reports.scheduleFailed'))
    } finally {
      setScheduleSaving(false)
    }
  }, [scheduleForm, showSuccess, showError, t, loadData])

  const updateScheduleField = useCallback((key, field, value) => {
    setScheduleForm(prev => ({
      ...prev,
      [key]: { ...prev[key], [field]: value },
    }))
  }, [])

  const addRecipient = useCallback((key) => {
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
  }, [recipientInputs])

  const removeRecipient = useCallback((key, email) => {
    setScheduleForm(prev => ({
      ...prev,
      [key]: {
        ...prev[key],
        recipients: prev[key].recipients.filter(r => r !== email),
      },
    }))
  }, [])

  const handleDownloadPDF = useCallback(async () => {
    try {
      setGeneratingPdf(true)
      const response = await reportsService.downloadExecutivePDF()
      const blob = response instanceof Blob ? response : new Blob([response], { type: 'application/pdf' })
      downloadBlob(blob, `ucm-executive-report-${new Date().toISOString().slice(0, 10)}.pdf`)
      showSuccess(t('reports.pdfGenerated'))
    } catch (err) {
      showError(t('reports.pdfFailed'))
    } finally {
      setGeneratingPdf(false)
    }
  }, [showSuccess, showError, t])

  const handleGeneratePdf = useCallback(async (templateKey) => {
    try {
      setGeneratingCustomPdf(templateKey || 'custom')
      const options = templateKey ? { template: templateKey } : { sections: selectedSections }
      const response = await reportsService.generateCustomPDF(options)
      const blob = response instanceof Blob ? response : new Blob([response], { type: 'application/pdf' })
      downloadBlob(blob, `ucm-report-${templateKey || 'custom'}-${new Date().toISOString().slice(0, 10)}.pdf`)
      showSuccess(t('reports.pdfGenerated'))
    } catch (err) {
      showError(t('reports.pdfFailed'))
    } finally {
      setGeneratingCustomPdf(null)
    }
  }, [selectedSections, showSuccess, showError, t])

  const toggleSection = useCallback((sectionId) => {
    setSelectedSections(prev =>
      prev.includes(sectionId) ? prev.filter(s => s !== sectionId) : [...prev, sectionId]
    )
  }, [])

  const renderScheduleFields = useCallback((r, form) => {
    if (!form.enabled) return null
    return (
      <div className="pl-8 space-y-3">
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
    )
  }, [t, recipientInputs, updateScheduleField, addRecipient, removeRecipient])

  const reportEntries = Object.entries(reportTypes)
  const enabledSchedules = schedule ? SCHEDULE_REPORTS.filter(r => schedule[r.key]?.enabled).length : 0

  const tabs = useMemo(() => [
    { id: 'reports', label: t('reports.tabs.reports'), icon: ChartBar },
    { id: 'pdf', label: t('reports.tabs.pdf'), icon: FilePdf },
    { id: 'schedule', label: t('reports.tabs.schedule'), icon: CalendarBlank },
  ], [t])

  const headerStats = useMemo(() => [
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
    if (parsed?.content && typeof parsed.content === 'string') {
      try { parsed = JSON.parse(parsed.content) } catch { /* keep original */ }
    }

    const items = parsed?.items || []
    const columns = parsed?.columns || []
    const summary = parsed?.summary || report.data?.summary || {}

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

    const colLabel = (col) => col.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())

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
          {t('common.countItems', { count: items.length })} • {t('reports.generatedAt')} {formatDate(new Date())}
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
        stats={headerStats}
        tabs={tabs}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        tabLayout="sidebar"
        tabGroups={[
          { labelKey: 'reports.groups.management', tabs: ['reports', 'pdf'], color: 'icon-bg-blue' },
          { labelKey: 'reports.groups.settings', tabs: ['schedule'], color: 'icon-bg-emerald' },
        ]}
      >
        {/* Data Reports tab */}
        {activeTab === 'reports' && (
          <div className="space-y-6">
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
                          type="button"
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

            {/* Inline report preview */}
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
        )}

        {/* Schedule tab — inline form */}
        {activeTab === 'schedule' && (
          <Card>
            <div className="px-4 py-3 border-b border-border">
              <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <CalendarBlank size={16} className="text-accent-primary" />
                {t('reports.scheduleReports')}
              </h3>
            </div>
            <div className="p-4 space-y-4">
              {/* Data Reports group */}
              <div className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                {t('reports.tabs.reports')}
              </div>
              {SCHEDULE_REPORTS.filter(r => r.group === 'data').map((r, idx) => {
                const form = scheduleForm[r.key] || {}
                const Icon = r.icon
                return (
                  <div key={r.key} className={idx > 0 ? 'border-t border-border pt-4' : ''}>
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
                    {renderScheduleFields(r, form)}
                  </div>
                )
              })}

              {/* PDF Reports group */}
              <div className="border-t border-border pt-4 mt-4">
                <div className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                  {t('reports.tabs.pdf')}
                </div>
              </div>
              {SCHEDULE_REPORTS.filter(r => r.group === 'pdf').map((r, idx) => {
                const form = scheduleForm[r.key] || {}
                const Icon = r.icon
                return (
                  <div key={r.key} className={idx > 0 ? 'border-t border-border pt-4' : ''}>
                    <div className="flex items-center gap-3 mb-2">
                      <label className="flex items-center gap-2 cursor-pointer flex-1 min-w-0">
                        <input
                          type="checkbox"
                          checked={form.enabled || false}
                          onChange={(e) => updateScheduleField(r.key, 'enabled', e.target.checked)}
                          className="rounded border-border"
                        />
                        <Icon size={18} className="text-purple-500 shrink-0" />
                        <span className="text-sm font-medium text-text-primary truncate">{r.label}</span>
                        <Badge variant="default" size="sm" className="ml-1">PDF</Badge>
                      </label>
                    </div>
                    {renderScheduleFields(r, form)}
                  </div>
                )
              })}
              <div className="flex justify-end gap-2 pt-4 border-t border-border">
                <Button type="button" onClick={handleSaveSchedule} disabled={scheduleSaving}>
                  {scheduleSaving ? <LoadingSpinner size="sm" /> : t('common.save')}
                </Button>
              </div>
            </div>
          </Card>
        )}

        {/* Executive Report tab */}
        {/* PDF Reports tab */}
        {activeTab === 'pdf' && (
          <div className="space-y-6">
            {/* Pre-defined templates */}
            <Card>
              <div className="px-4 py-3 border-b border-border">
                <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                  <FilePdf size={16} className="text-purple-500" />
                  {t('reports.pdf.templates')}
                </h3>
              </div>
              <div className="p-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {Object.entries(pdfTemplates).map(([key, tmpl]) => {
                    const isGen = generatingCustomPdf === key
                    return (
                      <div
                        key={key}
                        className="p-4 rounded-lg border-2 border-border hover:border-purple-400 bg-tertiary-50 transition-all flex flex-col gap-3"
                      >
                        <div className="flex items-center gap-3">
                          <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0 icon-bg-purple">
                            <FilePdf size={20} weight="duotone" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium text-text-primary">
                              {t(`reports.pdf.template.${key}.name`, { defaultValue: tmpl.name })}
                            </div>
                            <div className="text-xs text-text-muted mt-0.5">
                              {tmpl.sections?.length || 0} {t('reports.pdf.sections').toLowerCase()}
                            </div>
                          </div>
                        </div>
                        <p className="text-xs text-text-secondary leading-relaxed">
                          {t(`reports.pdf.template.${key}.description`, { defaultValue: tmpl.description })}
                        </p>
                        <div className="mt-auto pt-1">
                          <Button
                            type="button"
                            size="sm"
                            className="w-full"
                            onClick={() => handleGeneratePdf(key)}
                            disabled={!!generatingCustomPdf}
                          >
                            {isGen ? <LoadingSpinner size="sm" /> : (
                              <><FilePdf size={14} className="mr-1.5" /> {t('reports.downloadPDF')}</>
                            )}
                          </Button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            </Card>

            {/* Custom Report Builder */}
            <Card>
              <div className="px-4 py-3 border-b border-border">
                <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                  <SlidersHorizontal size={16} className="text-accent-primary" />
                  {t('reports.pdf.customBuilder')}
                </h3>
              </div>
              <div className="p-4 space-y-4">
                <p className="text-sm text-text-secondary">
                  {t('reports.pdf.customDesc')}
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                  {pdfSections.map(sectionId => {
                    const checked = selectedSections.includes(sectionId)
                    const sectionIcons = {
                      executive_summary: ChartBar,
                      risk_assessment: ShieldCheck,
                      certificate_status: Certificate,
                      compliance_overview: Gavel,
                      expiry: Clock,
                      lifecycle: ClockCounterClockwise,
                      ca_hierarchy: TreeStructure,
                      audit: FileText,
                      recommendations: Checks,
                    }
                    const SIcon = sectionIcons[sectionId] || FileText
                    return (
                      <label
                        key={sectionId}
                        className={cn(
                          'flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors',
                          checked
                            ? 'border-accent-primary bg-accent-primary-op5'
                            : 'border-border hover:bg-bg-tertiary'
                        )}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleSection(sectionId)}
                          className="rounded border-border"
                        />
                        <SIcon size={16} className={checked ? 'text-accent-primary' : 'text-text-muted'} />
                        <span className="text-sm text-text-primary">
                          {t(`reports.pdf.section.${sectionId}`, { defaultValue: sectionId.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) })}
                        </span>
                      </label>
                    )
                  })}
                </div>
                <div className="flex items-center gap-3 pt-2">
                  <Button
                    type="button"
                    onClick={() => handleGeneratePdf(null)}
                    disabled={selectedSections.length === 0 || !!generatingCustomPdf}
                  >
                    {generatingCustomPdf === 'custom' ? <LoadingSpinner size="sm" /> : (
                      <><FileArrowDown size={16} className="mr-1.5" /> {t('reports.pdf.generateCustom')}</>
                    )}
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() => setSelectedSections([...pdfSections])}
                  >
                    {t('common.selectAll')}
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() => setSelectedSections([])}
                  >
                    {t('common.deselectAll')}
                  </Button>
                  {selectedSections.length > 0 && (
                    <span className="text-xs text-text-muted">
                      {selectedSections.length} / {pdfSections.length} {t('reports.pdf.sections').toLowerCase()}
                    </span>
                  )}
                </div>
              </div>
            </Card>
          </div>
        )}
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
    </>
  )
}
