/**
 * CSRs (Certificate Signing Requests) Page - With Pending/History Tabs
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { 
  FileText, Upload, SignIn, Trash, Download, 
  Clock, Key, UploadSimple, CheckCircle, Warning,
  ClockCounterClockwise, Certificate, Stamp, ClipboardText
} from '@phosphor-icons/react'
import {
  Badge, Button, Modal, Input, Select, HelpCard, FileUpload, Textarea,
  CompactSection, CompactGrid, CompactField, CompactHeader, CompactStats,
  KeyIndicator
} from '../components'
import { SmartImportModal } from '../components/SmartImport'
import { ResponsiveLayout, ResponsiveDataTable } from '../components/ui/responsive'
import { csrsService, casService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useModals } from '../hooks'
import { useMobile } from '../contexts/MobileContext'
import { extractData, formatDate, cn } from '../lib/utils'
import { VALIDITY } from '../constants/config'
import { ERRORS, SUCCESS, CONFIRM } from '../lib/messages'

export default function CSRsPage() {
  const { t } = useTranslation()
  const { isMobile } = useMobile()
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canWrite, canDelete } = usePermission()
  const [searchParams, setSearchParams] = useSearchParams()
  const { modals, open: openModal, close: closeModal } = useModals(['upload', 'sign'])
  
  // Tab definitions (inside component for translations)
  const TABS = [
    { id: 'pending', label: t('common.pending'), icon: Warning },
    { id: 'history', label: t('common.history'), icon: ClockCounterClockwise }
  ]
  
  // Tab state
  const [activeTab, setActiveTab] = useState(searchParams.get('tab') || 'pending')
  
  // Data state
  const [pendingCSRs, setPendingCSRs] = useState([])
  const [historyCSRs, setHistoryCSRs] = useState([])
  const [loading, setLoading] = useState(true)
  const [cas, setCAs] = useState([])
  
  // Selection & modals
  const [selectedCSR, setSelectedCSR] = useState(null)
  const [showImportModal, setShowImportModal] = useState(false)
  const [signCA, setSignCA] = useState('')
  const [validityDays, setValidityDays] = useState(VALIDITY.DEFAULT_DAYS)
  
  // Upload modal
  const [uploadMode, setUploadMode] = useState('file') // 'file' or 'paste'
  const [pastedPEM, setPastedPEM] = useState('')
  
  // Key upload modal
  const [showKeyModal, setShowKeyModal] = useState(false)
  const [keyPem, setKeyPem] = useState('')
  const [keyPassphrase, setKeyPassphrase] = useState('')

  // Handle tab change
  const handleTabChange = (tabId) => {
    setActiveTab(tabId)
    setSelectedCSR(null)
    setPage(1)
    setSearchParams({ tab: tabId })
  }
  
  // Pagination state
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)

  useEffect(() => {
    loadData()
    if (searchParams.get('action') === 'upload') {
      openModal('upload')
      searchParams.delete('action')
      setSearchParams(searchParams)
    }
  }, [])

  const loadData = async () => {
    try {
      setLoading(true)
      const [pendingRes, historyRes, casRes] = await Promise.all([
        csrsService.getAll(),
        csrsService.getHistory(),
        casService.getAll()
      ])
      setPendingCSRs(pendingRes.data || [])
      setHistoryCSRs(historyRes.data || [])
      setCAs(casRes.data || casRes.cas || [])
    } catch (error) {
      showError(error.message || ERRORS.LOAD_FAILED.CSRS)
    } finally {
      setLoading(false)
    }
  }

  const loadCSRDetails = async (csr) => {
    try {
      const response = await csrsService.getById(csr.id)
      const data = extractData(response)
      setSelectedCSR({ ...data, ...csr }) // Merge to keep signed_by info
    } catch {
      setSelectedCSR(csr)
    }
  }

  const handleUpload = async (files) => {
    try {
      const file = files[0]
      const text = await file.text()
      await csrsService.upload(text)
      showSuccess(SUCCESS.CREATE.CSR)
      closeModal('upload')
      loadData()
    } catch (error) {
      showError(error.message || t('csrs.uploadFailed'))
    }
  }

  const handlePasteUpload = async () => {
    if (!pastedPEM.trim()) {
      showError(t('csrs.csrPEMError'))
      return
    }
    if (!pastedPEM.includes('-----BEGIN') || !pastedPEM.includes('REQUEST')) {
      showError(t('csrs.invalidCSRFormat'))
      return
    }
    try {
      await csrsService.upload(pastedPEM.trim())
      showSuccess(SUCCESS.CREATE.CSR)
      closeModal('upload')
      setPastedPEM('')
      setUploadMode('file')
      loadData()
    } catch (error) {
      showError(error.message || t('csrs.uploadFailed'))
    }
  }

  const handleSign = async () => {
    if (!signCA) {
      showError(t('common.selectCA'))
      return
    }
    try {
      await csrsService.sign(selectedCSR.id, signCA, validityDays)
      showSuccess(SUCCESS.OTHER.SIGNED)
      closeModal('sign')
      loadData()
      setSelectedCSR(null)
    } catch (error) {
      showError(error.message || t('csrs.signFailed'))
    }
  }

  const handleDelete = async (id) => {
    const confirmed = await showConfirm(CONFIRM.DELETE.CSR, {
      title: t('csrs.deleteCSR'),
      confirmText: t('common.delete'),
      variant: 'danger'
    })
    if (!confirmed) return
    try {
      await csrsService.delete(id)
      showSuccess(SUCCESS.DELETE.CSR)
      loadData()
      setSelectedCSR(null)
    } catch (error) {
      showError(error.message || t('csrs.deleteFailed'))
    }
  }

  const handleUploadKey = async () => {
    if (!keyPem.trim()) {
      showError(t('csrs.provideKey'))
      return
    }
    if (!keyPem.includes('PRIVATE KEY')) {
      showError(t('csrs.invalidKeyFormat'))
      return
    }
    try {
      await csrsService.uploadKey(selectedCSR.id, keyPem.trim(), keyPassphrase || null)
      showSuccess(SUCCESS.OTHER.KEY_UPLOADED)
      setShowKeyModal(false)
      setKeyPem('')
      setKeyPassphrase('')
      loadData()
      // Refresh selected CSR
      const updated = await csrsService.getById(selectedCSR.id)
      setSelectedCSR(updated.data || updated)
    } catch (error) {
      showError(error.message || t('csrs.keyUploadFailed'))
    }
  }

  const handleDownload = async (id, filename) => {
    try {
      const blob = await csrsService.download(id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename || 'csr.pem'
      a.click()
      showSuccess(t('common.downloadSuccess'))
    } catch (error) {
      showError(error.message || t('csrs.downloadFailed'))
    }
  }

  // Current data based on tab
  const currentData = activeTab === 'pending' ? pendingCSRs : historyCSRs

  // Stats
  const stats = useMemo(() => [
    { icon: Warning, label: t('common.pending'), value: pendingCSRs.length, variant: 'warning' },
    { icon: CheckCircle, label: t('csrs.signed'), value: historyCSRs.length, variant: 'success' },
    { icon: FileText, label: t('common.total'), value: pendingCSRs.length + historyCSRs.length, variant: 'primary' }
  ], [pendingCSRs, historyCSRs, t])

  // Pending table columns
  const pendingColumns = useMemo(() => [
    {
      key: 'cn',
      header: t('common.commonName'),
      priority: 1,
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 icon-bg-orange">
            <FileText size={14} weight="duotone" />
          </div>
          <span className="font-medium truncate">{row.common_name || row.cn || val || t('common.unnamed')}</span>
          <KeyIndicator hasKey={row.has_private_key} size={14} />
        </div>
      ),
      mobileRender: (val, row) => (
        <div className="flex items-center justify-between gap-2 w-full">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 icon-bg-orange">
              <FileText size={14} weight="duotone" />
            </div>
            <span className="font-medium truncate">{row.common_name || row.cn || val || t('common.unnamed')}</span>
            <KeyIndicator hasKey={row.has_private_key} size={12} />
          </div>
          <Badge variant="warning" size="sm" dot>{t('common.pending')}</Badge>
        </div>
      )
    },
    {
      key: 'organization',
      header: t('common.organization'),
      priority: 3,
      hideOnMobile: true,
      render: (val) => <span className="text-sm text-text-secondary">{val || '—'}</span>
    },
    {
      key: 'created_at',
      header: t('common.created'),
      priority: 2,
      render: (val) => (
        <span className="text-xs text-text-secondary whitespace-nowrap">
          {formatDate(val, 'short')}
        </span>
      )
    },
    {
      key: 'key_type',
      header: t('common.key'),
      priority: 4,
      hideOnMobile: true,
      render: (val, row) => (
        <span className="text-xs font-mono text-text-secondary">
          {row.key_algorithm || 'RSA'} {row.key_size ? `(${row.key_size})` : ''}
        </span>
      )
    }
  ], [t])

  // History table columns
  const historyColumns = useMemo(() => [
    {
      key: 'cn',
      header: t('common.commonName'),
      priority: 1,
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 icon-bg-emerald">
            <Certificate size={14} weight="duotone" />
          </div>
          <span className="font-medium truncate">{row.common_name || row.cn || val || t('common.unnamed')}</span>
          <KeyIndicator hasKey={row.has_private_key} size={14} />
          {row.source === 'acme' && (
            <Badge variant="info" size="sm">ACME</Badge>
          )}
          {row.source === 'scep' && (
            <Badge variant="purple" size="sm">SCEP</Badge>
          )}
        </div>
      ),
      mobileRender: (val, row) => (
        <div className="flex items-center justify-between gap-2 w-full">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 icon-bg-emerald">
              <Certificate size={14} weight="duotone" />
            </div>
            <span className="font-medium truncate">{row.common_name || row.cn || val || t('common.unnamed')}</span>
            <KeyIndicator hasKey={row.has_private_key} size={12} />
          </div>
          <Badge variant="success" size="sm" dot>{t('csrs.signed')}</Badge>
        </div>
      )
    },
    {
      key: 'signed_by',
      header: t('common.signedBy'),
      priority: 2,
      hideOnMobile: true,
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <Stamp size={14} className="text-accent-primary" />
          <span className="text-sm text-text-primary truncate">{val || row.issuer_name || '—'}</span>
        </div>
      ),
      mobileRender: (val, row) => (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-text-tertiary">CA:</span>
          <span className="text-text-secondary truncate">{val || row.issuer_name || '—'}</span>
        </div>
      )
    },
    {
      key: 'signed_at',
      header: t('csrs.signed'),
      priority: 3,
      render: (val, row) => (
        <span className="text-xs text-text-secondary whitespace-nowrap">
          {formatDate(val || row.valid_from, 'short')}
        </span>
      )
    },
    {
      key: 'valid_to',
      header: t('common.expires'),
      priority: 4,
      hideOnMobile: true,
      render: (val, row) => {
        const days = row.days_remaining
        const variant = days < 0 ? 'danger' : days < 30 ? 'warning' : 'success'
        return (
          <Badge variant={variant} size="sm">
            {days < 0 ? t('common.expired') : t('csrs.daysRemaining', { days })}
          </Badge>
        )
      }
    }
  ], [t])

  // Row actions for pending
  const pendingRowActions = useCallback((row) => [
    { label: t('csrs.downloadCSR'), icon: Download, onClick: () => handleDownload(row.id, `${row.cn || 'csr'}.pem`) },
    ...(canWrite('csrs') ? [
      { label: t('csrs.sign'), icon: SignIn, onClick: () => { setSelectedCSR(row); openModal('sign') }}
    ] : []),
    ...(canDelete('csrs') ? [
      { label: t('common.delete'), icon: Trash, variant: 'danger', onClick: () => handleDelete(row.id) }
    ] : [])
  ], [canWrite, canDelete, t])

  // Row actions for history
  const historyRowActions = useCallback((row) => [
    { label: t('common.downloadCertificate'), icon: Download, onClick: () => handleDownload(row.id, `${row.cn || 'cert'}.pem`) },
    { label: t('common.viewInCertificates'), icon: Certificate, onClick: () => window.location.href = `/certificates?id=${row.id}` }
  ], [t])

  // Help content
  const helpContent = (
    <div className="space-y-4">
      {/* Quick Stats */}
      <div className="visual-section">
        <div className="visual-section-header">
          <FileText size={16} className="status-primary-text" />
          {t('csrs.csrStatistics')}
        </div>
        <div className="visual-section-body">
          <div className="quick-info-grid">
            <div className="help-stat-card">
              <div className="help-stat-value help-stat-value-warning">{pendingCSRs.length}</div>
              <div className="help-stat-label">{t('common.pending')}</div>
            </div>
            <div className="help-stat-card">
              <div className="help-stat-value help-stat-value-success">{historyCSRs.length}</div>
              <div className="help-stat-label">{t('csrs.signed')}</div>
            </div>
            <div className="help-stat-card">
              <div className="help-stat-value help-stat-value-primary">{pendingCSRs.length + historyCSRs.length}</div>
              <div className="help-stat-label">{t('common.total')}</div>
            </div>
          </div>
        </div>
      </div>

      <HelpCard title={t('common.aboutCSRs')} variant="info">
        {t('csrs.aboutCSRsDescription')}
      </HelpCard>
      <HelpCard title={t('common.status')} variant="info">
        <div className="space-y-1.5 mt-2">
          <div className="flex items-center gap-2">
            <Badge variant="warning" size="sm" dot>{t('common.pending')}</Badge>
            <span className="text-xs">{t('csrs.pendingDescription')}</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="success" size="sm" dot>{t('csrs.signed')}</Badge>
            <span className="text-xs">{t('csrs.signedDescription')}</span>
          </div>
        </div>
      </HelpCard>
      <HelpCard title={t('csrs.workflow')} variant="tip">
        {t('csrs.workflowSteps')}
      </HelpCard>
    </div>
  )

  // Tabs with counts
  const tabsWithCounts = TABS.map(tab => ({
    ...tab,
    count: tab.id === 'pending' ? pendingCSRs.length : historyCSRs.length
  }))

  return (
    <>
      <ResponsiveLayout
        title={t('common.csrs')}
        subtitle={t('csrs.pendingSubtitle', { pending: pendingCSRs.length, signed: historyCSRs.length })}
        icon={FileText}
        stats={stats}
        helpPageKey="csrs"
        tabs={tabsWithCounts}
        activeTab={activeTab}
        onTabChange={handleTabChange}
        splitView={true}
        splitEmptyContent={
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
              <FileText size={24} className="text-text-tertiary" />
            </div>
            <p className="text-sm text-text-secondary">{t('csrs.selectCSR')}</p>
          </div>
        }
        slideOverOpen={!!selectedCSR}
        onSlideOverClose={() => setSelectedCSR(null)}
        slideOverTitle={activeTab === 'pending' ? t('common.csrDetails') : t('common.certificateDetails')}
        slideOverContent={selectedCSR && (
          activeTab === 'pending' ? (
            <CSRDetailsPanel 
              csr={selectedCSR}
              canWrite={canWrite}
              canDelete={canDelete}
              onSign={() => openModal('sign')}
              onDownload={() => handleDownload(selectedCSR.id, `${selectedCSR.cn || 'csr'}.pem`)}
              onDelete={() => handleDelete(selectedCSR.id)}
              onUploadKey={() => setShowKeyModal(true)}
              t={t}
            />
          ) : (
            <SignedCSRDetailsPanel 
              cert={selectedCSR}
              onDownload={() => handleDownload(selectedCSR.id, `${selectedCSR.cn || 'cert'}.pem`)}
              t={t}
            />
          )
        )}
      >
        <ResponsiveDataTable
          data={currentData.map(item => ({
            ...item,
            cn: item.common_name || item.cn || item.subject || t('common.unnamed')
          }))}
          columns={activeTab === 'pending' ? pendingColumns : historyColumns}
          loading={loading}
          selectedId={selectedCSR?.id}
          onRowClick={(item) => item ? loadCSRDetails(item) : setSelectedCSR(null)}
          rowActions={activeTab === 'pending' ? pendingRowActions : historyRowActions}
          searchable
          searchPlaceholder={activeTab === 'pending' ? t('csrs.searchPending') : t('csrs.searchSigned')}
          searchKeys={['cn', 'common_name', 'subject', 'organization', 'signed_by']}
          columnStorageKey={`ucm-csrs-${activeTab}-columns`}
          toolbarActions={activeTab === 'pending' && canWrite('csrs') && (
            isMobile ? (
              <Button size="lg" onClick={() => setShowImportModal(true)} className="w-11 h-11 p-0">
                <UploadSimple size={22} weight="bold" />
              </Button>
            ) : (
              <Button size="sm" onClick={() => setShowImportModal(true)}>
                <UploadSimple size={14} weight="bold" />
                {t('common.import')}
              </Button>
            )
          )}
          sortable
          pagination={{
            page,
            total: currentData.length,
            perPage,
            onChange: setPage,
            onPerPageChange: (v) => { setPerPage(v); setPage(1) }
          }}
          emptyIcon={activeTab === 'pending' ? Warning : CheckCircle}
          emptyTitle={activeTab === 'pending' ? t('csrs.noPendingCSRs') : t('csrs.noSignedCertificates')}
          emptyDescription={activeTab === 'pending' 
            ? t('csrs.uploadToStart') 
            : t('csrs.signToSee')}
          emptyAction={activeTab === 'pending' && canWrite('csrs') && (
            <Button onClick={() => setShowImportModal(true)}>
              <UploadSimple size={16} /> {t('csrs.importCSR')}
            </Button>
          )}
        />
      </ResponsiveLayout>

      {/* Upload CSR Modal */}
      <Modal
        open={modals.upload}
        onOpenChange={() => { closeModal('upload'); setPastedPEM(''); setUploadMode('file') }}
        title={t('csrs.uploadCSR')}
      >
        <div className="p-4 space-y-4">
          {/* Mode tabs */}
          <div className="flex gap-1 p-1 bg-bg-tertiary rounded-lg">
            <button
              onClick={() => setUploadMode('file')}
              className={cn(
                "flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                uploadMode === 'file' 
                  ? "bg-bg-primary text-text-primary shadow-sm" 
                  : "text-text-secondary hover:text-text-primary"
              )}
            >
              <UploadSimple size={16} /> {t('common.uploadFile')}
            </button>
            <button
              onClick={() => setUploadMode('paste')}
              className={cn(
                "flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                uploadMode === 'paste' 
                  ? "bg-bg-primary text-text-primary shadow-sm" 
                  : "text-text-secondary hover:text-text-primary"
              )}
            >
              <ClipboardText size={16} /> {t('csrs.pastePEM')}
            </button>
          </div>

          {uploadMode === 'file' ? (
            <>
              <p className="text-sm text-text-secondary">
                {t('csrs.uploadCSRDescription')}
              </p>
              <FileUpload
                accept=".pem,.csr"
                onUpload={handleUpload}
                maxSize={1024 * 1024}
              />
            </>
          ) : (
            <>
              <p className="text-sm text-text-secondary">
                {t('csrs.pasteCSRDescription')}
              </p>
              <Textarea
                value={pastedPEM}
                onChange={(e) => setPastedPEM(e.target.value)}
                placeholder="-----BEGIN CERTIFICATE REQUEST-----
MIICijCCAXICAQAwRTELMAkGA1UEBhMCVVMx...
-----END CERTIFICATE REQUEST-----"
                rows={10}
                className="font-mono text-xs"
              />
              <div className="flex justify-end gap-2 pt-2 border-t border-border">
                <Button variant="secondary" onClick={() => { closeModal('upload'); setPastedPEM('') }}>
                  {t('common.cancel')}
                </Button>
                <Button onClick={handlePasteUpload} disabled={!pastedPEM.trim()}>
                  <UploadSimple size={16} /> {t('common.upload')}
                </Button>
              </div>
            </>
          )}
        </div>
      </Modal>

      {/* Sign CSR Modal */}
      <Modal
        open={modals.sign}
        onOpenChange={() => closeModal('sign')}
        title={t('common.signCSR')}
      >
        <div className="p-4 space-y-4">
          <p className="text-sm text-text-secondary">
            {t('csrs.signCSRDescription')}
          </p>
          
          <Select
            label={t('common.certificateAuthority')}
            options={cas.map(ca => ({ value: String(ca.id), label: ca.descr || ca.name || ca.common_name }))}
            value={signCA}
            onChange={setSignCA}
            placeholder={t('csrs.selectCA')}
          />

          <Input
            label={t('csrs.validityPeriod')}
            type="number"
            value={validityDays}
            onChange={(e) => setValidityDays(parseInt(e.target.value))}
            min="1"
            max="3650"
          />

          <div className="flex justify-end gap-2 pt-4 border-t border-border">
            <Button variant="secondary" onClick={() => closeModal('sign')}>{t('common.cancel')}</Button>
            <Button onClick={handleSign} disabled={!signCA}>
              <SignIn size={16} /> {t('common.signCSR')}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Upload Private Key Modal */}
      <Modal
        open={showKeyModal}
        onOpenChange={() => { setShowKeyModal(false); setKeyPem(''); setKeyPassphrase('') }}
        title={t('csrs.uploadPrivateKey')}
      >
        <div className="p-4 space-y-4">
          <p className="text-sm text-text-secondary">
            {t('csrs.uploadPrivateKey')} <strong>{selectedCSR?.common_name || selectedCSR?.cn}</strong>
          </p>
          <Textarea
            label={t('common.privateKeyPEM')}
            value={keyPem}
            onChange={(e) => setKeyPem(e.target.value)}
            placeholder="-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQE...
-----END PRIVATE KEY-----"
            rows={8}
            className="font-mono text-xs"
          />
          <Input
            label={t('csrs.passphrase')}
            type="password"
            value={keyPassphrase}
            onChange={(e) => setKeyPassphrase(e.target.value)}
            placeholder={t('csrs.passphraseHint')}
          />
          <div className="flex justify-end gap-2 pt-2 border-t border-border">
            <Button variant="secondary" onClick={() => { setShowKeyModal(false); setKeyPem(''); setKeyPassphrase('') }}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleUploadKey} disabled={!keyPem.trim()}>
              <UploadSimple size={16} /> {t('csrs.uploadKey')}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Smart Import Modal */}
      <SmartImportModal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        onImportComplete={() => {
          setShowImportModal(false)
          loadData()
        }}
      />
    </>
  )
}

// =============================================================================
// CSR DETAILS PANEL (for pending CSRs)
// =============================================================================

function CSRDetailsPanel({ csr, canWrite, canDelete, onSign, onDownload, onDelete, onUploadKey, t }) {
  return (
    <div className="p-3 space-y-3">
      {/* Header */}
      <CompactHeader
        icon={FileText}
        iconClass="bg-accent-warning/20"
        title={csr.common_name || csr.cn || t('csrs.unnamedCSR')}
        subtitle={csr.organization}
        badge={
          <div className="flex gap-1">
            <Badge variant="warning" size="sm" icon={Clock}>{t('common.pending')}</Badge>
            {csr.has_private_key && <Badge variant="success" size="sm" icon={Key}>{t('common.hasKey')}</Badge>}
          </div>
        }
      />

      {/* Stats */}
      <CompactStats stats={[
        { icon: Clock, value: csr.created_at ? formatDate(csr.created_at, 'short') : '—' },
        { icon: Key, value: `${csr.key_algorithm || 'RSA'} ${csr.key_size || ''}` },
      ]} />

      {/* Actions */}
      <div className="flex gap-2 flex-wrap">
        <Button size="sm" variant="secondary" onClick={onDownload}>
          <Download size={14} /> {t('common.download')}
        </Button>
        {canWrite('csrs') && !csr.has_private_key && (
          <Button size="sm" variant="secondary" onClick={onUploadKey}>
            <UploadSimple size={14} /> {t('csrs.uploadKey')}
          </Button>
        )}
        {canWrite('csrs') && (
          <Button size="sm" onClick={onSign}>
            <SignIn size={14} /> {t('csrs.sign')}
          </Button>
        )}
        {canDelete('csrs') && (
          <Button size="sm" variant="danger" onClick={onDelete}>
            <Trash size={14} />
          </Button>
        )}
      </div>

      {/* Subject Information */}
      <CompactSection title={t('common.subject')}>
        <CompactGrid>
          <CompactField label={t('common.commonName')} value={csr.common_name || csr.cn} className="col-span-2" />
          <CompactField label={t('common.organization')} value={csr.organization} />
          <CompactField label={t('common.orgUnit')} value={csr.organizational_unit} />
          <CompactField label={t('common.country')} value={csr.country} />
          <CompactField label={t('common.state')} value={csr.state} />
          <CompactField label={t('common.locality')} value={csr.locality} />
          <CompactField label={t('common.email')} value={csr.email} />
        </CompactGrid>
      </CompactSection>

      {/* Key Information */}
      <CompactSection title={t('common.keyInformation')}>
        <CompactGrid>
          <CompactField label={t('common.algorithm')} value={csr.key_algorithm || 'RSA'} />
          <CompactField label={t('common.keySize')} value={csr.key_size} />
          <CompactField label={t('common.signature')} value={csr.signature_algorithm} />
        </CompactGrid>
      </CompactSection>

      {/* SANs */}
      {(csr.sans?.length > 0 || csr.san_dns?.length > 0) && (
        <CompactSection title={t('common.subjectAltNames')}>
          <div className="text-xs text-text-secondary space-y-1">
            {(csr.sans || csr.san_dns || []).map((san, i) => (
              <div key={i} className="font-mono bg-bg-tertiary px-2 py-1 rounded">
                {san}
              </div>
            ))}
          </div>
        </CompactSection>
      )}

      {/* Timeline */}
      <CompactSection title={t('common.timeline')}>
        <CompactGrid>
          <CompactField label={t('common.created')} value={csr.created_at ? formatDate(csr.created_at) : '—'} />
          <CompactField label={t('csrs.requester')} value={csr.requester || csr.created_by} />
        </CompactGrid>
      </CompactSection>
    </div>
  )
}

// =============================================================================
// SIGNED CSR DETAILS PANEL (for history)
// =============================================================================

function SignedCSRDetailsPanel({ cert, onDownload, t }) {
  const daysRemaining = cert.days_remaining || 0
  const expiryVariant = daysRemaining < 0 ? 'danger' : daysRemaining < 30 ? 'warning' : 'success'
  const isAcme = cert.source === 'acme'
  const isScep = cert.source === 'scep'
  
  return (
    <div className="p-3 space-y-3">
      {/* Header */}
      <CompactHeader
        icon={Certificate}
        iconClass="bg-accent-success/20"
        title={cert.common_name || cert.cn || t('csrs.unnamedCertificate')}
        subtitle={cert.organization}
        badge={
          <div className="flex gap-1">
            <Badge variant="success" size="sm" icon={CheckCircle}>{t('csrs.signed')}</Badge>
            {isAcme && <Badge variant="info" size="sm">ACME</Badge>}
            {isScep && <Badge variant="purple" size="sm">SCEP</Badge>}
          </div>
        }
      />

      {/* Stats */}
      <CompactStats stats={[
        { icon: Stamp, value: cert.signed_by || cert.issuer_name || '—' },
        { icon: Clock, value: t('csrs.remaining', { days: daysRemaining }) },
      ]} />

      {/* Actions */}
      <div className="flex gap-2">
        <Button size="sm" variant="secondary" className="flex-1" onClick={onDownload}>
          <Download size={14} /> {t('common.download')}
        </Button>
        <Button 
          size="sm" 
          variant="secondary"
          onClick={() => window.location.href = `/certificates?id=${cert.id}`}
        >
          <Certificate size={14} /> {t('common.viewCertificate')}
        </Button>
      </div>

      {/* Signing Information */}
      <CompactSection title={t('common.signingDetails')}>
        <CompactGrid>
          <CompactField label={t('common.signedBy')} value={cert.signed_by || cert.issuer_name} className="col-span-2" />
          <CompactField label={t('csrs.signed')} value={cert.signed_at ? formatDate(cert.signed_at) : formatDate(cert.valid_from)} />
          <CompactField label={t('common.expires')} value={cert.valid_to ? formatDate(cert.valid_to) : '—'} />
          <CompactField 
            label={t('common.status')} 
            value={
              <Badge variant={expiryVariant} size="sm">
                {daysRemaining < 0 ? t('common.expired') : t('csrs.daysLeft', { days: daysRemaining })}
              </Badge>
            } 
          />
        </CompactGrid>
      </CompactSection>

      {/* Subject Information */}
      <CompactSection title={t('common.subject')}>
        <CompactGrid>
          <CompactField label={t('common.commonName')} value={cert.common_name || cert.cn} className="col-span-2" />
          <CompactField label={t('common.organization')} value={cert.organization} />
          <CompactField label={t('common.orgUnit')} value={cert.organizational_unit} />
          <CompactField label={t('common.country')} value={cert.country} />
          <CompactField label={t('common.state')} value={cert.state} />
        </CompactGrid>
      </CompactSection>

      {/* Key Information */}
      <CompactSection title={t('common.keyInformation')}>
        <CompactGrid>
          <CompactField label={t('common.algorithm')} value={cert.key_algorithm || 'RSA'} />
          <CompactField label={t('common.keySize')} value={cert.key_size} />
          <CompactField label={t('common.serial')} value={cert.serial_number} copyable mono className="col-span-2" />
        </CompactGrid>
      </CompactSection>

      {/* Timeline */}
      <CompactSection title={t('common.timeline')}>
        <CompactGrid>
          <CompactField label={t('csrs.csrCreated')} value={cert.created_at ? formatDate(cert.created_at) : '—'} />
          <CompactField label={t('csrs.certificateIssued')} value={cert.valid_from ? formatDate(cert.valid_from) : '—'} />
        </CompactGrid>
      </CompactSection>
    </div>
  )
}
