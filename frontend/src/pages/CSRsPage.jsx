/**
 * CSRs (Certificate Signing Requests) Page - Using ResponsiveLayout
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { 
  FileText, Upload, SignIn, Trash, Download, 
  Clock, Key, UploadSimple, CheckCircle, Warning, X
} from '@phosphor-icons/react'
import {
  Badge, Button, Modal, Input, Select, HelpCard, FileUpload,
  CompactSection, CompactGrid, CompactField, CompactHeader, CompactStats
} from '../components'
import { ResponsiveLayout, ResponsiveDataTable } from '../components/ui/responsive'
import { csrsService, casService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useModals } from '../hooks'
import { useMobile } from '../contexts/MobileContext'
import { extractData, formatDate, cn } from '../lib/utils'
import { VALIDITY } from '../constants/config'

export default function CSRsPage() {
  const { isMobile } = useMobile()
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canWrite, canDelete } = usePermission()
  const [searchParams, setSearchParams] = useSearchParams()
  const { modals, open: openModal, close: closeModal } = useModals(['upload', 'sign'])
  
  // Data state
  const [csrs, setCSRs] = useState([])
  const [loading, setLoading] = useState(true)
  const [cas, setCAs] = useState([])
  
  // Selection & modals
  const [selectedCSR, setSelectedCSR] = useState(null)
  const [signCA, setSignCA] = useState('')
  const [validityDays, setValidityDays] = useState(VALIDITY.DEFAULT_DAYS)
  
  // Filters
  const [filterStatus, setFilterStatus] = useState('')
  
  // Pagination
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
      const [csrsRes, casRes] = await Promise.all([
        csrsService.getAll(),
        casService.getAll()
      ])
      setCSRs(csrsRes.data || [])
      setCAs(casRes.data || casRes.cas || [])
    } catch (error) {
      showError('Failed to load CSRs')
    } finally {
      setLoading(false)
    }
  }

  const loadCSRDetails = async (csr) => {
    try {
      const response = await csrsService.getById(csr.id)
      const data = extractData(response)
      setSelectedCSR({ ...data })
    } catch {
      setSelectedCSR(csr)
    }
  }

  const handleUpload = async (files) => {
    try {
      const file = files[0]
      const text = await file.text()
      await csrsService.upload(text)
      showSuccess('CSR uploaded successfully')
      closeModal('upload')
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
      showSuccess('CSR signed successfully')
      closeModal('sign')
      loadData()
      setSelectedCSR(null)
    } catch (error) {
      showError(error.message || 'Failed to sign CSR')
    }
  }

  const handleDelete = async (id) => {
    const confirmed = await showConfirm('Are you sure you want to delete this CSR?', {
      title: 'Delete CSR',
      confirmText: 'Delete',
      variant: 'danger'
    })
    if (!confirmed) return
    try {
      await csrsService.delete(id)
      showSuccess('CSR deleted successfully')
      loadData()
      setSelectedCSR(null)
    } catch (error) {
      showError(error.message || 'Failed to delete CSR')
    }
  }

  const handleDownload = async (id) => {
    try {
      const blob = await csrsService.download(id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `csr.pem`
      a.click()
      showSuccess('CSR downloaded')
    } catch (error) {
      showError(error.message || 'Failed to download CSR')
    }
  }

  // Filter data
  const filteredCSRs = useMemo(() => {
    let result = csrs.map(csr => ({
      ...csr,
      cn: csr.common_name || csr.subject || 'Unnamed CSR'
    }))
    
    if (filterStatus) {
      result = result.filter(c => c.status === filterStatus)
    }
    
    return result
  }, [csrs, filterStatus])

  // Stats
  const stats = useMemo(() => {
    const pending = csrs.filter(c => c.status === 'pending' || !c.status).length
    const signed = csrs.filter(c => c.status === 'signed').length
    const rejected = csrs.filter(c => c.status === 'rejected').length
    return [
      { icon: Warning, label: 'Pending', value: pending, variant: 'warning' },
      { icon: CheckCircle, label: 'Signed', value: signed, variant: 'success' },
      { icon: X, label: 'Rejected', value: rejected, variant: 'danger' },
      { icon: FileText, label: 'Total', value: csrs.length, variant: 'primary' }
    ]
  }, [csrs])

  // Table columns
  const columns = useMemo(() => [
    {
      key: 'cn',
      header: 'Common Name',
      priority: 1,
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <FileText size={16} className="text-accent-primary shrink-0" />
          <span className="font-medium truncate">{val}</span>
        </div>
      )
    },
    {
      key: 'status',
      header: 'Status',
      priority: 2,
      render: (val) => (
        <Badge 
          variant={val === 'signed' ? 'success' : val === 'rejected' ? 'danger' : 'warning'}
          size="sm"
        >
          {val || 'pending'}
        </Badge>
      )
    },
    {
      key: 'created_at',
      header: 'Created',
      priority: 3,
      hideOnMobile: true,
      render: (val) => (
        <span className="text-xs text-text-secondary whitespace-nowrap">
          {formatDate(val)}
        </span>
      )
    },
    {
      key: 'key_algorithm',
      header: 'Key',
      priority: 4,
      hideOnMobile: true,
      render: (val, row) => (
        <span className="text-xs font-mono text-text-secondary">
          {val || 'RSA'} {row.key_size ? `(${row.key_size})` : ''}
        </span>
      )
    }
  ], [])

  // Filters config
  const filters = useMemo(() => [
    {
      key: 'status',
      label: 'Status',
      type: 'select',
      value: filterStatus,
      onChange: setFilterStatus,
      placeholder: 'All Status',
      options: [
        { value: 'pending', label: 'Pending' },
        { value: 'signed', label: 'Signed' },
        { value: 'rejected', label: 'Rejected' }
      ]
    }
  ], [filterStatus])

  const activeFiltersCount = filterStatus ? 1 : 0

  // Row actions
  const rowActions = useCallback((row) => [
    { label: 'Download', icon: Download, onClick: () => handleDownload(row.id) },
    ...(canWrite('csrs') && (!row.status || row.status === 'pending') ? [
      { label: 'Sign', icon: SignIn, onClick: () => { setSelectedCSR(row); openModal('sign') }}
    ] : []),
    ...(canDelete('csrs') ? [
      { label: 'Delete', icon: Trash, variant: 'danger', onClick: () => handleDelete(row.id) }
    ] : [])
  ], [canWrite, canDelete])

  // Help content
  const helpContent = (
    <div className="space-y-3">
      <HelpCard title="About CSRs" variant="info">
        A Certificate Signing Request contains the public key and identity information needed to issue a certificate.
      </HelpCard>
      <HelpCard title="Status Legend" variant="info">
        <div className="space-y-1 mt-2">
          <div className="flex items-center gap-2">
            <Badge variant="warning" size="sm">Pending</Badge>
            <span className="text-xs">Awaiting signature</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="success" size="sm">Signed</Badge>
            <span className="text-xs">Certificate issued</span>
          </div>
        </div>
      </HelpCard>
      <HelpCard title="Workflow" variant="tip">
        1. Upload CSR → 2. Review details → 3. Sign with CA → 4. Download certificate
      </HelpCard>
    </div>
  )

  return (
    <>
      <ResponsiveLayout
        title="Certificate Signing Requests"
        subtitle={`${csrs.length} request${csrs.length !== 1 ? 's' : ''}`}
        icon={FileText}
        stats={stats}
        helpContent={helpContent}
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
        slideOverTitle="CSR Details"
        slideOverContent={selectedCSR && (
          <CSRDetailsPanel 
            csr={selectedCSR}
            canWrite={canWrite}
            canDelete={canDelete}
            onSign={() => openModal('sign')}
            onDownload={() => handleDownload(selectedCSR.id)}
            onDelete={() => handleDelete(selectedCSR.id)}
          />
        )}
      >
        <ResponsiveDataTable
          data={filteredCSRs}
          columns={columns}
          loading={loading}
          selectedId={selectedCSR?.id}
          onRowClick={(csr) => csr ? loadCSRDetails(csr) : setSelectedCSR(null)}
          rowActions={rowActions}
          searchable
          searchPlaceholder="Search CSRs..."
          searchKeys={['cn', 'common_name', 'subject', 'organization']}
          toolbarFilters={[
            {
              key: 'status',
              value: filterStatus,
              onChange: setFilterStatus,
              placeholder: 'All Status',
              options: [
                { value: 'pending', label: 'Pending' },
                { value: 'signed', label: 'Signed' },
                { value: 'rejected', label: 'Rejected' }
              ]
            }
          ]}
          toolbarActions={canWrite('csrs') && (
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
          emptyIcon={FileText}
          emptyTitle="No CSRs"
          emptyDescription="Upload a CSR to get started"
          emptyAction={canWrite('csrs') && (
            <Button onClick={() => openModal('upload')}>
              <UploadSimple size={16} /> Upload CSR
            </Button>
          )}
        />
      </ResponsiveLayout>

      {/* Upload CSR Modal */}
      <Modal
        open={modals.upload}
        onOpenChange={() => closeModal('upload')}
        title="Upload CSR"
      >
        <div className="p-4 space-y-4">
          <p className="text-sm text-text-secondary">
            Upload a Certificate Signing Request file (.pem, .csr)
          </p>
          <FileUpload
            accept=".pem,.csr"
            onUpload={handleUpload}
            maxSize={1024 * 1024}
          />
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
    </>
  )
}

// =============================================================================
// CSR DETAILS PANEL (for slide-over)
// =============================================================================

function CSRDetailsPanel({ csr, canWrite, canDelete, onSign, onDownload, onDelete }) {
  const statusVariant = csr.status === 'signed' ? 'success' : csr.status === 'rejected' ? 'danger' : 'warning'
  
  return (
    <div className="p-3 space-y-3">
      {/* Header */}
      <CompactHeader
        icon={FileText}
        iconClass="bg-accent-primary/20"
        title={csr.common_name || csr.cn || 'Unnamed CSR'}
        subtitle={csr.organization}
        badge={
          <Badge variant={statusVariant} size="sm">
            {csr.status || 'pending'}
          </Badge>
        }
      />

      {/* Stats */}
      <CompactStats stats={[
        { icon: Clock, value: csr.created_at ? formatDate(csr.created_at, 'short') : '—' },
        { icon: Key, value: `${csr.key_algorithm || 'RSA'} ${csr.key_size || ''}` },
      ]} />

      {/* Actions */}
      <div className="flex gap-2">
        <Button size="sm" variant="secondary" className="flex-1" onClick={onDownload}>
          <Download size={14} /> Download
        </Button>
        {canWrite('csrs') && (!csr.status || csr.status === 'pending') && (
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

      {/* Extensions */}
      {(csr.san || csr.subject_alternative_names) && (
        <CompactSection title="Subject Alternative Names">
          <div className="text-xs text-text-secondary space-y-1">
            {(csr.san || csr.subject_alternative_names || []).map((san, i) => (
              <div key={i} className="font-mono bg-bg-tertiary px-2 py-1 rounded">
                {san}
              </div>
            ))}
          </div>
        </CompactSection>
      )}

      {/* Timestamps */}
      <CompactSection title="Timeline">
        <CompactGrid>
          <CompactField label="Created" value={csr.created_at ? formatDate(csr.created_at) : '—'} />
          {csr.signed_at && <CompactField label="Signed" value={formatDate(csr.signed_at)} />}
        </CompactGrid>
      </CompactSection>
    </div>
  )
}
