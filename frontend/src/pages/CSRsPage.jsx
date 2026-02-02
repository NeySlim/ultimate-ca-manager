/**
 * CSRs (Certificate Signing Requests) Page - With Pending/History Tabs
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { 
  FileText, Upload, SignIn, Trash, Download, 
  Clock, Key, UploadSimple, CheckCircle, Warning, X,
  ClockCounterClockwise, Certificate, Stamp, ClipboardText
} from '@phosphor-icons/react'
import {
  Badge, Button, Modal, Input, Select, HelpCard, FileUpload, Textarea,
  CompactSection, CompactGrid, CompactField, CompactHeader, CompactStats,
  KeyIndicator
} from '../components'
import { ResponsiveLayout, ResponsiveDataTable } from '../components/ui/responsive'
import { csrsService, casService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useModals } from '../hooks'
import { useMobile } from '../contexts/MobileContext'
import { extractData, formatDate, cn } from '../lib/utils'
import { VALIDITY } from '../constants/config'
import { ERRORS, SUCCESS, LABELS, CONFIRM } from '../lib/messages'

// Tab definitions
const TABS = [
  { id: 'pending', label: 'Pending', icon: Warning },
  { id: 'history', label: 'History', icon: ClockCounterClockwise }
]

export default function CSRsPage() {
  const { isMobile } = useMobile()
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canWrite, canDelete } = usePermission()
  const [searchParams, setSearchParams] = useSearchParams()
  const { modals, open: openModal, close: closeModal } = useModals(['upload', 'sign'])
  
  // Tab state
  const [activeTab, setActiveTab] = useState(searchParams.get('tab') || 'pending')
  
  // Data state
  const [pendingCSRs, setPendingCSRs] = useState([])
  const [historyCSRs, setHistoryCSRs] = useState([])
  const [loading, setLoading] = useState(true)
  const [cas, setCAs] = useState([])
  
  // Selection & modals
  const [selectedCSR, setSelectedCSR] = useState(null)
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
      showError(error.message || 'Failed to upload CSR')
    }
  }

  const handlePasteUpload = async () => {
    if (!pastedPEM.trim()) {
      showError('Please paste a CSR in PEM format')
      return
    }
    if (!pastedPEM.includes('-----BEGIN') || !pastedPEM.includes('REQUEST')) {
      showError('Invalid CSR format. Must be in PEM format (-----BEGIN CERTIFICATE REQUEST-----)')
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
      showError(error.message || 'Failed to upload CSR')
    }
  }

  const handleSign = async () => {
    if (!signCA) {
      showError('Please select a CA')
      return
    }
    try {
      await csrsService.sign(selectedCSR.id, signCA, validityDays)
      showSuccess(SUCCESS.OTHER.SIGNED)
      closeModal('sign')
      loadData()
      setSelectedCSR(null)
    } catch (error) {
      showError(error.message || 'Failed to sign CSR')
    }
  }

  const handleDelete = async (id) => {
    const confirmed = await showConfirm(CONFIRM.DELETE.CSR, {
      title: CONFIRM.DELETE.TITLE,
      confirmText: 'Delete',
      variant: 'danger'
    })
    if (!confirmed) return
    try {
      await csrsService.delete(id)
      showSuccess(SUCCESS.DELETE.CSR)
      loadData()
      setSelectedCSR(null)
    } catch (error) {
      showError(error.message || 'Failed to delete CSR')
    }
  }

  const handleUploadKey = async () => {
    if (!keyPem.trim()) {
      showError('Please provide a private key')
      return
    }
    if (!keyPem.includes('PRIVATE KEY')) {
      showError('Invalid private key format - must be PEM format')
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
      showError(error.message || 'Failed to upload private key')
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
      showSuccess('Downloaded successfully')
    } catch (error) {
      showError(error.message || 'Failed to download')
    }
  }

  // Current data based on tab
  const currentData = activeTab === 'pending' ? pendingCSRs : historyCSRs

  // Stats
  const stats = useMemo(() => [
    { icon: Warning, label: 'Pending', value: pendingCSRs.length, variant: 'warning' },
    { icon: CheckCircle, label: 'Signed', value: historyCSRs.length, variant: 'success' },
    { icon: FileText, label: 'Total', value: pendingCSRs.length + historyCSRs.length, variant: 'primary' }
  ], [pendingCSRs, historyCSRs])

  // Pending table columns
  const pendingColumns = useMemo(() => [
    {
      key: 'cn',
      header: 'Common Name',
      priority: 1,
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <FileText size={16} className="text-accent-warning shrink-0" />
          <span className="font-medium truncate">{row.common_name || row.cn || val || 'Unnamed'}</span>
          <KeyIndicator hasKey={row.has_private_key} size={14} />
        </div>
      )
    },
    {
      key: 'organization',
      header: 'Organization',
      priority: 3,
      hideOnMobile: true,
      render: (val) => <span className="text-sm text-text-secondary">{val || '—'}</span>
    },
    {
      key: 'created_at',
      header: 'Created',
      priority: 2,
      render: (val) => (
        <span className="text-xs text-text-secondary whitespace-nowrap">
          {formatDate(val, 'short')}
        </span>
      )
    },
    {
      key: 'key_type',
      header: 'Key',
      priority: 4,
      hideOnMobile: true,
      render: (val, row) => (
        <span className="text-xs font-mono text-text-secondary">
          {row.key_algorithm || 'RSA'} {row.key_size ? `(${row.key_size})` : ''}
        </span>
      )
    }
  ], [])

  // History table columns
  const historyColumns = useMemo(() => [
    {
      key: 'cn',
      header: 'Common Name',
      priority: 1,
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <Certificate size={16} className="text-accent-success shrink-0" />
          <span className="font-medium truncate">{row.common_name || row.cn || val || 'Unnamed'}</span>
          <KeyIndicator hasKey={row.has_private_key} size={14} />
          {row.source === 'acme' && (
            <Badge variant="info" size="sm">ACME</Badge>
          )}
          {row.source === 'scep' && (
            <Badge variant="purple" size="sm">SCEP</Badge>
          )}
        </div>
      )
    },
    {
      key: 'signed_by',
      header: 'Signed By',
      priority: 2,
      render: (val, row) => (
        <div className="flex items-center gap-1.5">
          <Stamp size={14} className="text-accent-primary" />
          <span className="text-sm text-text-primary truncate">{val || row.issuer_name || '—'}</span>
        </div>
      )
    },
    {
      key: 'signed_at',
      header: 'Signed',
      priority: 3,
      render: (val, row) => (
        <span className="text-xs text-text-secondary whitespace-nowrap">
          {formatDate(val || row.valid_from, 'short')}
        </span>
      )
    },
    {
      key: 'valid_to',
      header: 'Expires',
      priority: 4,
      hideOnMobile: true,
      render: (val, row) => {
        const days = row.days_remaining
        const variant = days < 0 ? 'danger' : days < 30 ? 'warning' : 'success'
        return (
          <Badge variant={variant} size="sm">
            {days < 0 ? 'Expired' : `${days}d`}
          </Badge>
        )
      }
    }
  ], [])

  // Row actions for pending
  const pendingRowActions = useCallback((row) => [
    { label: 'Download CSR', icon: Download, onClick: () => handleDownload(row.id, `${row.cn || 'csr'}.pem`) },
    ...(canWrite('csrs') ? [
      { label: 'Sign', icon: SignIn, onClick: () => { setSelectedCSR(row); openModal('sign') }}
    ] : []),
    ...(canDelete('csrs') ? [
      { label: 'Delete', icon: Trash, variant: 'danger', onClick: () => handleDelete(row.id) }
    ] : [])
  ], [canWrite, canDelete])

  // Row actions for history
  const historyRowActions = useCallback((row) => [
    { label: 'Download Certificate', icon: Download, onClick: () => handleDownload(row.id, `${row.cn || 'cert'}.pem`) },
    { label: 'View in Certificates', icon: Certificate, onClick: () => window.location.href = `/certificates?id=${row.id}` }
  ], [])

  // Help content
  const helpContent = (
    <div className="space-y-3">
      <HelpCard title="About CSRs" variant="info">
        A Certificate Signing Request contains the public key and identity information needed to issue a certificate.
      </HelpCard>
      <HelpCard title="Tabs" variant="info">
        <div className="space-y-1 mt-2">
          <div className="flex items-center gap-2">
            <Badge variant="warning" size="sm">Pending</Badge>
            <span className="text-xs">CSRs awaiting signature</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="success" size="sm">History</Badge>
            <span className="text-xs">Previously signed CSRs</span>
          </div>
        </div>
      </HelpCard>
      <HelpCard title="Workflow" variant="tip">
        1. Upload CSR → 2. Review details → 3. Sign with CA → 4. Certificate appears in History
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
        title="Certificate Signing Requests"
        subtitle={`${pendingCSRs.length} pending, ${historyCSRs.length} signed`}
        icon={FileText}
        stats={stats}
        helpContent={helpContent}
        tabs={tabsWithCounts}
        activeTab={activeTab}
        onTabChange={handleTabChange}
        splitView={true}
        splitEmptyContent={
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
              <FileText size={24} className="text-text-tertiary" />
            </div>
            <p className="text-sm text-text-secondary">Select a CSR to view details</p>
          </div>
        }
        slideOverOpen={!!selectedCSR}
        onSlideOverClose={() => setSelectedCSR(null)}
        slideOverTitle={activeTab === 'pending' ? 'CSR Details' : 'Certificate Details'}
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
            />
          ) : (
            <SignedCSRDetailsPanel 
              cert={selectedCSR}
              onDownload={() => handleDownload(selectedCSR.id, `${selectedCSR.cn || 'cert'}.pem`)}
            />
          )
        )}
      >
        <ResponsiveDataTable
          data={currentData.map(item => ({
            ...item,
            cn: item.common_name || item.cn || item.subject || 'Unnamed'
          }))}
          columns={activeTab === 'pending' ? pendingColumns : historyColumns}
          loading={loading}
          selectedId={selectedCSR?.id}
          onRowClick={(item) => item ? loadCSRDetails(item) : setSelectedCSR(null)}
          rowActions={activeTab === 'pending' ? pendingRowActions : historyRowActions}
          searchable
          searchPlaceholder={activeTab === 'pending' ? 'Search pending CSRs...' : 'Search signed certificates...'}
          searchKeys={['cn', 'common_name', 'subject', 'organization', 'signed_by']}
          toolbarActions={activeTab === 'pending' && canWrite('csrs') && (
            isMobile ? (
              <Button size="lg" onClick={() => openModal('upload')} className="w-11 h-11 p-0">
                <UploadSimple size={22} weight="bold" />
              </Button>
            ) : (
              <Button size="sm" onClick={() => openModal('upload')}>
                <UploadSimple size={14} weight="bold" />
                Upload
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
          emptyTitle={activeTab === 'pending' ? 'No Pending CSRs' : 'No Signed Certificates'}
          emptyDescription={activeTab === 'pending' 
            ? 'Upload a CSR to get started' 
            : 'Sign a CSR to see it here'}
          emptyAction={activeTab === 'pending' && canWrite('csrs') && (
            <Button onClick={() => openModal('upload')}>
              <UploadSimple size={16} /> Upload CSR
            </Button>
          )}
        />
      </ResponsiveLayout>

      {/* Upload CSR Modal */}
      <Modal
        open={modals.upload}
        onOpenChange={() => { closeModal('upload'); setPastedPEM(''); setUploadMode('file') }}
        title="Upload CSR"
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
              <UploadSimple size={16} /> Upload File
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
              <ClipboardText size={16} /> Paste PEM
            </button>
          </div>

          {uploadMode === 'file' ? (
            <>
              <p className="text-sm text-text-secondary">
                Upload a Certificate Signing Request file (.pem, .csr)
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
                Paste your CSR in PEM format below
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
                  Cancel
                </Button>
                <Button onClick={handlePasteUpload} disabled={!pastedPEM.trim()}>
                  <UploadSimple size={16} /> Upload
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
        title="Sign CSR"
      >
        <div className="p-4 space-y-4">
          <p className="text-sm text-text-secondary">
            Sign this CSR with a Certificate Authority to issue a certificate
          </p>
          
          <Select
            label="Certificate Authority"
            options={cas.map(ca => ({ value: ca.id, label: ca.descr || ca.name || ca.common_name }))}
            value={signCA}
            onChange={setSignCA}
            placeholder="Select CA..."
          />

          <Input
            label="Validity Period (days)"
            type="number"
            value={validityDays}
            onChange={(e) => setValidityDays(parseInt(e.target.value))}
            min="1"
            max="3650"
          />

          <div className="flex justify-end gap-2 pt-4 border-t border-border">
            <Button variant="secondary" onClick={() => closeModal('sign')}>Cancel</Button>
            <Button onClick={handleSign} disabled={!signCA}>
              <SignIn size={16} /> Sign CSR
            </Button>
          </div>
        </div>
      </Modal>

      {/* Upload Private Key Modal */}
      <Modal
        open={showKeyModal}
        onOpenChange={() => { setShowKeyModal(false); setKeyPem(''); setKeyPassphrase('') }}
        title="Upload Private Key"
      >
        <div className="p-4 space-y-4">
          <p className="text-sm text-text-secondary">
            Upload a private key for <strong>{selectedCSR?.common_name || selectedCSR?.cn}</strong>
          </p>
          <Textarea
            label="Private Key (PEM)"
            value={keyPem}
            onChange={(e) => setKeyPem(e.target.value)}
            placeholder="-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQE...
-----END PRIVATE KEY-----"
            rows={8}
            className="font-mono text-xs"
          />
          <Input
            label="Passphrase (if encrypted)"
            type="password"
            value={keyPassphrase}
            onChange={(e) => setKeyPassphrase(e.target.value)}
            placeholder="Leave empty if key is not encrypted"
          />
          <div className="flex justify-end gap-2 pt-2 border-t border-border">
            <Button variant="secondary" onClick={() => { setShowKeyModal(false); setKeyPem(''); setKeyPassphrase('') }}>
              Cancel
            </Button>
            <Button onClick={handleUploadKey} disabled={!keyPem.trim()}>
              <UploadSimple size={16} /> Upload Key
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}

// =============================================================================
// CSR DETAILS PANEL (for pending CSRs)
// =============================================================================

function CSRDetailsPanel({ csr, canWrite, canDelete, onSign, onDownload, onDelete, onUploadKey }) {
  return (
    <div className="p-3 space-y-3">
      {/* Header */}
      <CompactHeader
        icon={FileText}
        iconClass="bg-accent-warning/20"
        title={csr.common_name || csr.cn || 'Unnamed CSR'}
        subtitle={csr.organization}
        badge={
          <div className="flex gap-1">
            <Badge variant="warning" size="sm">Pending</Badge>
            {csr.has_private_key && <Badge variant="success" size="sm">Has Key</Badge>}
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
          <Download size={14} /> Download
        </Button>
        {canWrite('csrs') && !csr.has_private_key && (
          <Button size="sm" variant="secondary" onClick={onUploadKey}>
            <UploadSimple size={14} /> Upload Key
          </Button>
        )}
        {canWrite('csrs') && (
          <Button size="sm" onClick={onSign}>
            <SignIn size={14} /> Sign
          </Button>
        )}
        {canDelete('csrs') && (
          <Button size="sm" variant="danger" onClick={onDelete}>
            <Trash size={14} />
          </Button>
        )}
      </div>

      {/* Subject Information */}
      <CompactSection title="Subject">
        <CompactGrid>
          <CompactField label="Common Name" value={csr.common_name || csr.cn} className="col-span-2" />
          <CompactField label="Organization" value={csr.organization} />
          <CompactField label="Org Unit" value={csr.organizational_unit} />
          <CompactField label="Country" value={csr.country} />
          <CompactField label="State" value={csr.state} />
          <CompactField label="Locality" value={csr.locality} />
          <CompactField label="Email" value={csr.email} />
        </CompactGrid>
      </CompactSection>

      {/* Key Information */}
      <CompactSection title="Key Information">
        <CompactGrid>
          <CompactField label="Algorithm" value={csr.key_algorithm || 'RSA'} />
          <CompactField label="Key Size" value={csr.key_size} />
          <CompactField label="Signature" value={csr.signature_algorithm} />
        </CompactGrid>
      </CompactSection>

      {/* SANs */}
      {(csr.sans?.length > 0 || csr.san_dns?.length > 0) && (
        <CompactSection title="Subject Alternative Names">
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
      <CompactSection title="Timeline">
        <CompactGrid>
          <CompactField label="Created" value={csr.created_at ? formatDate(csr.created_at) : '—'} />
          <CompactField label="Requester" value={csr.requester || csr.created_by} />
        </CompactGrid>
      </CompactSection>
    </div>
  )
}

// =============================================================================
// SIGNED CSR DETAILS PANEL (for history)
// =============================================================================

function SignedCSRDetailsPanel({ cert, onDownload }) {
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
        title={cert.common_name || cert.cn || 'Unnamed Certificate'}
        subtitle={cert.organization}
        badge={
          <div className="flex gap-1">
            <Badge variant="success" size="sm">Signed</Badge>
            {isAcme && <Badge variant="info" size="sm">ACME</Badge>}
            {isScep && <Badge variant="purple" size="sm">SCEP</Badge>}
          </div>
        }
      />

      {/* Stats */}
      <CompactStats stats={[
        { icon: Stamp, value: cert.signed_by || cert.issuer_name || '—' },
        { icon: Clock, value: `${daysRemaining}d remaining` },
      ]} />

      {/* Actions */}
      <div className="flex gap-2">
        <Button size="sm" variant="secondary" className="flex-1" onClick={onDownload}>
          <Download size={14} /> Download
        </Button>
        <Button 
          size="sm" 
          variant="secondary"
          onClick={() => window.location.href = `/certificates?id=${cert.id}`}
        >
          <Certificate size={14} /> View Certificate
        </Button>
      </div>

      {/* Signing Information */}
      <CompactSection title="Signing Details">
        <CompactGrid>
          <CompactField label="Signed By" value={cert.signed_by || cert.issuer_name} className="col-span-2" />
          <CompactField label="Signed" value={cert.signed_at ? formatDate(cert.signed_at) : formatDate(cert.valid_from)} />
          <CompactField label="Expires" value={cert.valid_to ? formatDate(cert.valid_to) : '—'} />
          <CompactField 
            label="Status" 
            value={
              <Badge variant={expiryVariant} size="sm">
                {daysRemaining < 0 ? 'Expired' : `${daysRemaining} days left`}
              </Badge>
            } 
          />
        </CompactGrid>
      </CompactSection>

      {/* Subject Information */}
      <CompactSection title="Subject">
        <CompactGrid>
          <CompactField label="Common Name" value={cert.common_name || cert.cn} className="col-span-2" />
          <CompactField label="Organization" value={cert.organization} />
          <CompactField label="Org Unit" value={cert.organizational_unit} />
          <CompactField label="Country" value={cert.country} />
          <CompactField label="State" value={cert.state} />
        </CompactGrid>
      </CompactSection>

      {/* Key Information */}
      <CompactSection title="Key Information">
        <CompactGrid>
          <CompactField label="Algorithm" value={cert.key_algorithm || 'RSA'} />
          <CompactField label="Key Size" value={cert.key_size} />
          <CompactField label="Serial" value={cert.serial_number} className="col-span-2" />
        </CompactGrid>
      </CompactSection>

      {/* Timeline */}
      <CompactSection title="Timeline">
        <CompactGrid>
          <CompactField label="CSR Created" value={cert.created_at ? formatDate(cert.created_at) : '—'} />
          <CompactField label="Certificate Issued" value={cert.valid_from ? formatDate(cert.valid_from) : '—'} />
        </CompactGrid>
      </CompactSection>
    </div>
  )
}
