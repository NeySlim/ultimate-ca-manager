/**
 * ReportsPage — Report Generation & Scheduling
 * Generate, download, and schedule compliance reports.
 */
import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ChartBar, Download, PaperPlaneTilt, CalendarBlank, FileText,
  FileCsv, FileJs, Play, CheckCircle, Clock, Gear,
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
  const [generating, setGenerating] = useState(null) // report_type being generated
  const [generatedReport, setGeneratedReport] = useState(null) // { type, data }

  // Test send modal
  const [testSendModal, setTestSendModal] = useState(null) // report_type
  const [testEmail, setTestEmail] = useState('')
  const [testSending, setTestSending] = useState(false)

  // Schedule edit modal
  const [showScheduleModal, setShowScheduleModal] = useState(false)
  const [scheduleForm, setScheduleForm] = useState({
    expiry_report: { enabled: false, recipients: [] },
    compliance_report: { enabled: false, recipients: [] },
  })
  const [scheduleSaving, setScheduleSaving] = useState(false)

  // Recipient inputs for schedule form
  const [expiryRecipientInput, setExpiryRecipientInput] = useState('')
  const [complianceRecipientInput, setComplianceRecipientInput] = useState('')

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      const [typesRes, scheduleRes] = await Promise.all([
        reportsService.getTypes(),
        reportsService.getSchedule().catch(() => ({ data: null })),
      ])
      setReportTypes(typesRes.data || {})
      if (scheduleRes.data) setSchedule(scheduleRes.data)
    } catch (err) {
      showError(t('reports.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [showError, t])

  useEffect(() => { loadData() }, [loadData])

  const handleGenerate = async (reportType, format = 'json') => {
    try {
      setGenerating(reportType)
      const res = await reportsService.generate(reportType, { format, days: 30 })
      setGeneratedReport({ type: reportType, data: res.data })
      showSuccess(t('reports.generated'))
    } catch (err) {
      showError(err.message || t('reports.generateFailed'))
    } finally {
      setGenerating(null)
    }
  }

  const handleDownload = async (reportType, format = 'csv') => {
    try {
      setGenerating(reportType)
      const res = await reportsService.download(reportType, format, 30)

      // Create blob for download
      const content = typeof res === 'string' ? res : (res.data ? (typeof res.data === 'string' ? res.data : JSON.stringify(res.data, null, 2)) : JSON.stringify(res, null, 2))
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
      showError(err.message || t('reports.downloadFailed'))
    } finally {
      setGenerating(null)
    }
  }

  const handleTestSend = async () => {
    if (!testEmail.trim() || !testSendModal) return
    try {
      setTestSending(true)
      await reportsService.sendTest(testSendModal, testEmail)
      showSuccess(t('reports.testSent'))
      setTestSendModal(null)
      setTestEmail('')
    } catch (err) {
      showError(err.message || t('reports.testFailed'))
    } finally {
      setTestSending(false)
    }
  }

  const openScheduleModal = () => {
    setScheduleForm({
      expiry_report: {
        enabled: schedule?.expiry_report?.enabled || false,
        recipients: schedule?.expiry_report?.recipients || [],
      },
      compliance_report: {
        enabled: schedule?.compliance_report?.enabled || false,
        recipients: schedule?.compliance_report?.recipients || [],
      },
    })
    setExpiryRecipientInput('')
    setComplianceRecipientInput('')
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
      showError(err.message || t('reports.scheduleFailed'))
    } finally {
      setScheduleSaving(false)
    }
  }

  const addRecipient = (type, input, setInput) => {
    const email = input.trim()
    if (!email || !email.includes('@')) return
    setScheduleForm(prev => ({
      ...prev,
      [type]: {
        ...prev[type],
        recipients: [...prev[type].recipients.filter(r => r !== email), email],
      },
    }))
    setInput('')
  }

  const removeRecipient = (type, email) => {
    setScheduleForm(prev => ({
      ...prev,
      [type]: {
        ...prev[type],
        recipients: prev[type].recipients.filter(r => r !== email),
      },
    }))
  }

  if (loading) {
    return (
      <ResponsiveLayout title={t('reports.title')} subtitle={t('reports.subtitle')} icon={ChartBar} loading>
        <div className="flex items-center justify-center py-20">
          <LoadingSpinner size="lg" />
        </div>
      </ResponsiveLayout>
    )
  }

  return (
    <>
      <ResponsiveLayout
        title={t('reports.title')}
        subtitle={t('reports.subtitle')}
        icon={ChartBar}
        helpPageKey="reports"
        actions={canWrite('settings') ? (
          <Button variant="secondary" onClick={openScheduleModal}>
            <CalendarBlank size={16} className="mr-1.5" /> {t('reports.scheduleReports')}
          </Button>
        ) : null}
      >
        {/* Schedule Status */}
        {schedule && (
          <Card className="mb-4">
            <div className="p-4">
              <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
                <CalendarBlank size={16} className="text-accent-primary" />
                {t('reports.scheduledReports')}
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="flex items-center justify-between p-3 rounded-lg bg-bg-tertiary">
                  <div className="flex items-center gap-2">
                    <Clock size={16} className="text-yellow-500" />
                    <div>
                      <div className="text-sm font-medium text-text-primary">{t('reports.expiryReport')}</div>
                      <div className="text-xs text-text-muted">{t('reports.daily')}</div>
                    </div>
                  </div>
                  <Badge variant={schedule.expiry_report?.enabled ? 'success' : 'default'}>
                    {schedule.expiry_report?.enabled ? t('common.enabled') : t('common.disabled')}
                  </Badge>
                </div>
                <div className="flex items-center justify-between p-3 rounded-lg bg-bg-tertiary">
                  <div className="flex items-center gap-2">
                    <Gavel size={16} className="text-red-500" />
                    <div>
                      <div className="text-sm font-medium text-text-primary">{t('reports.complianceReport')}</div>
                      <div className="text-xs text-text-muted">{t('reports.weekly')}</div>
                    </div>
                  </div>
                  <Badge variant={schedule.compliance_report?.enabled ? 'success' : 'default'}>
                    {schedule.compliance_report?.enabled ? t('common.enabled') : t('common.disabled')}
                  </Badge>
                </div>
              </div>
            </div>
          </Card>
        )}

        {/* Report Type Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Object.entries(reportTypes).map(([key, report]) => {
            const Icon = REPORT_ICONS[key] || FileText
            const variant = REPORT_VARIANTS[key] || 'default'
            const isGenerating = generating === key

            return (
              <Card key={key} className="overflow-hidden">
                <div className="p-4">
                  {/* Header */}
                  <div className="flex items-start gap-3 mb-3">
                    <div className={cn(
                      'w-10 h-10 rounded-lg flex items-center justify-center shrink-0',
                      variant === 'info' ? 'bg-blue-500/10 text-blue-500' :
                      variant === 'warning' ? 'bg-yellow-500/10 text-yellow-500' :
                      variant === 'success' ? 'bg-green-500/10 text-green-500' :
                      variant === 'danger' ? 'bg-red-500/10 text-red-500' :
                      'bg-gray-500/10 text-gray-500'
                    )}>
                      <Icon size={22} weight="duotone" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="text-sm font-semibold text-text-primary">{report.name}</h3>
                      <p className="text-xs text-text-muted mt-0.5">{report.description}</p>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2 mt-4 pt-3 border-t border-border">
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => handleGenerate(key)}
                      disabled={isGenerating}
                      className="flex-1"
                    >
                      {isGenerating ? <LoadingSpinner size="sm" /> : (
                        <><Play size={14} className="mr-1" /> {t('reports.generate')}</>
                      )}
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => handleDownload(key, 'csv')}
                      disabled={isGenerating}
                      title={t('reports.downloadCSV')}
                    >
                      <FileCsv size={16} />
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => handleDownload(key, 'json')}
                      disabled={isGenerating}
                      title={t('reports.downloadJSON')}
                    >
                      <FileJs size={16} />
                    </Button>
                    {canWrite('settings') && (
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => { setTestSendModal(key); setTestEmail('') }}
                        title={t('reports.testSend')}
                      >
                        <PaperPlaneTilt size={16} />
                      </Button>
                    )}
                  </div>
                </div>
              </Card>
            )
          })}
        </div>

        {/* Generated Report Preview */}
        {generatedReport && (
          <Card className="mt-4">
            <div className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                  <CheckCircle size={16} className="text-green-500" weight="fill" />
                  {t('reports.generatedPreview')} — {reportTypes[generatedReport.type]?.name}
                </h3>
                <Button size="sm" variant="secondary" onClick={() => setGeneratedReport(null)}>
                  {t('common.close')}
                </Button>
              </div>
              <div className="bg-bg-tertiary rounded-lg p-4 max-h-80 overflow-auto">
                <pre className="text-xs text-text-secondary font-mono whitespace-pre-wrap">
                  {typeof generatedReport.data === 'string'
                    ? generatedReport.data
                    : JSON.stringify(generatedReport.data, null, 2)
                  }
                </pre>
              </div>
            </div>
          </Card>
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
            <Button variant="secondary" onClick={() => { setTestSendModal(null); setTestEmail('') }}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleTestSend} disabled={testSending || !testEmail.trim()}>
              {testSending ? <LoadingSpinner size="sm" /> : (
                <><PaperPlaneTilt size={14} className="mr-1" /> {t('reports.send')}</>
              )}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Schedule Modal */}
      <Modal
        open={showScheduleModal}
        onOpenChange={(open) => { if (!open) setShowScheduleModal(false) }}
        title={t('reports.scheduleReports')}
        size="lg"
      >
        <div className="p-4 space-y-6 max-h-[70vh] overflow-y-auto">
          {/* Expiry Report */}
          <div>
            <div className="flex items-center gap-3 mb-3">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={scheduleForm.expiry_report.enabled}
                  onChange={(e) => setScheduleForm(prev => ({
                    ...prev,
                    expiry_report: { ...prev.expiry_report, enabled: e.target.checked },
                  }))}
                  className="rounded border-border"
                />
                <Clock size={18} className="text-yellow-500" />
                <span className="text-sm font-medium text-text-primary">{t('reports.expiryReport')}</span>
              </label>
              <Badge variant="default" size="sm">{t('reports.daily')}</Badge>
            </div>
            {scheduleForm.expiry_report.enabled && (
              <div className="pl-8">
                <label className="text-sm text-text-secondary mb-1.5 block">{t('reports.recipients')}</label>
                <div className="flex gap-2 mb-2">
                  <Input
                    value={expiryRecipientInput}
                    onChange={(e) => setExpiryRecipientInput(e.target.value)}
                    placeholder="email@example.com"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        addRecipient('expiry_report', expiryRecipientInput, setExpiryRecipientInput)
                      }
                    }}
                    className="flex-1"
                  />
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    onClick={() => addRecipient('expiry_report', expiryRecipientInput, setExpiryRecipientInput)}
                  >
                    {t('common.add')}
                  </Button>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {scheduleForm.expiry_report.recipients.map(email => (
                    <Badge key={email} variant="default" size="sm" className="pr-1">
                      {email}
                      <button
                        type="button"
                        onClick={() => removeRecipient('expiry_report', email)}
                        className="ml-1.5 text-text-muted hover:text-red-500"
                      >×</button>
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Compliance Report */}
          <div className="border-t border-border pt-4">
            <div className="flex items-center gap-3 mb-3">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={scheduleForm.compliance_report.enabled}
                  onChange={(e) => setScheduleForm(prev => ({
                    ...prev,
                    compliance_report: { ...prev.compliance_report, enabled: e.target.checked },
                  }))}
                  className="rounded border-border"
                />
                <Gavel size={18} className="text-red-500" />
                <span className="text-sm font-medium text-text-primary">{t('reports.complianceReport')}</span>
              </label>
              <Badge variant="default" size="sm">{t('reports.weekly')}</Badge>
            </div>
            {scheduleForm.compliance_report.enabled && (
              <div className="pl-8">
                <label className="text-sm text-text-secondary mb-1.5 block">{t('reports.recipients')}</label>
                <div className="flex gap-2 mb-2">
                  <Input
                    value={complianceRecipientInput}
                    onChange={(e) => setComplianceRecipientInput(e.target.value)}
                    placeholder="email@example.com"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        addRecipient('compliance_report', complianceRecipientInput, setComplianceRecipientInput)
                      }
                    }}
                    className="flex-1"
                  />
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    onClick={() => addRecipient('compliance_report', complianceRecipientInput, setComplianceRecipientInput)}
                  >
                    {t('common.add')}
                  </Button>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {scheduleForm.compliance_report.recipients.map(email => (
                    <Badge key={email} variant="default" size="sm" className="pr-1">
                      {email}
                      <button
                        type="button"
                        onClick={() => removeRecipient('compliance_report', email)}
                        className="ml-1.5 text-text-muted hover:text-red-500"
                      >×</button>
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="flex justify-end gap-2 pt-4 border-t border-border">
            <Button variant="secondary" onClick={() => setShowScheduleModal(false)}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleSaveSchedule} disabled={scheduleSaving}>
              {scheduleSaving ? <LoadingSpinner size="sm" /> : t('common.save')}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}
