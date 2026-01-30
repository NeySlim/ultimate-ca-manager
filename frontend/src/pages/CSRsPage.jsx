/**
 * CSRs (Certificate Signing Requests) Page - Using ListPageLayout
 */
import { useState, useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { 
  FileText, Upload, SignIn, Trash, Download, FileArrowUp, 
  Clock, Key, UploadSimple
} from '@phosphor-icons/react'
import {
  ListPageLayout, Badge, Button, Modal, Input, Select,
  DetailHeader, DetailSection, DetailGrid, DetailField, HelpCard,
  FileUpload, LoadingSpinner
} from '../components'
import { csrsService, casService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useModals } from '../hooks'
import { extractData, formatDate } from '../lib/utils'
import { VALIDITY } from '../constants/config'

export default function CSRsPage() {
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canWrite, canDelete } = usePermission()
  const [searchParams, setSearchParams] = useSearchParams()
  const fileRef = useRef(null)
  const { modals, open: openModal, close: closeModal } = useModals(['upload', 'sign'])
  
  const [csrs, setCSRs] = useState([])
  const [selectedCSR, setSelectedCSR] = useState(null)
  const [loading, setLoading] = useState(true)
  const [cas, setCAs] = useState([])
  const [signCA, setSignCA] = useState('')
  const [validityDays, setValidityDays] = useState(VALIDITY.DEFAULT_DAYS)

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
      setCAs(casRes.cas || [])
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

  // Table columns
  const columns = [
    {
      key: 'common_name',
      header: 'Common Name',
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <FileText size={16} className="text-accent-primary shrink-0" />
          <span className="font-medium truncate">{val || row.subject || 'Unnamed CSR'}</span>
        </div>
      )
    },
    {
      key: 'status',
      header: 'Status',
      render: (val) => (
        <Badge 
          variant={val === 'pending' ? 'warning' : 'success'}
          size="sm"
        >
          {val || 'pending'}
        </Badge>
      )
    },
    {
      key: 'created_at',
      header: 'Created',
      sortType: 'date',
      render: (val) => formatDate(val)
    },
    {
      key: 'key_algorithm',
      header: 'Key Type',
      render: (val, row) => `${val || 'RSA'} ${row.key_size ? `(${row.key_size})` : ''}`
    }
  ]

  // Row actions
  const rowActions = (row) => [
    ...(canWrite('csrs') && row.status === 'pending' ? [
      { label: 'Sign', icon: SignIn, onClick: () => { setSelectedCSR(row); openModal('sign') }}
    ] : []),
    { label: 'Download CSR', icon: Download, onClick: () => handleDownload(row.id) },
    ...(canDelete('csrs') ? [
      { label: 'Delete', icon: Trash, variant: 'danger', onClick: () => handleDelete(row.id) }
    ] : [])
  ]

  // Render details panel
  const renderDetails = (csr) => (
    <div className="p-4 space-y-4">
      <DetailHeader
        icon={FileText}
        title={csr.common_name || 'Unnamed CSR'}
        subtitle={csr.subject}
        badge={
          <Badge variant={csr.status === 'pending' ? 'warning' : 'success'}>
            {csr.status || 'pending'}
          </Badge>
        }
        stats={[
          { icon: Clock, label: 'Created', value: formatDate(csr.created_at) },
          { icon: Key, label: 'Key', value: `${csr.key_algorithm || 'RSA'} ${csr.key_size ? `(${csr.key_size})` : ''}` },
        ]}
        actions={[
          ...(canWrite('csrs') && csr.status === 'pending' ? [
            { label: 'Sign', icon: SignIn, onClick: () => openModal('sign') }
          ] : []),
          { label: 'Download', icon: Download, variant: 'secondary', onClick: () => handleDownload(csr.id) },
          ...(canDelete('csrs') ? [
            { label: 'Delete', icon: Trash, variant: 'danger', onClick: () => handleDelete(csr.id) }
          ] : [])
        ]}
      />

      <DetailSection title="Subject Information">
        <DetailGrid>
          <DetailField label="Common Name" value={csr.common_name} />
          <DetailField label="Organization" value={csr.organization} />
          <DetailField label="Country" value={csr.country} />
          <DetailField label="State" value={csr.state} />
          <DetailField label="Locality" value={csr.locality} />
          <DetailField label="Email" value={csr.email} />
        </DetailGrid>
      </DetailSection>

      <DetailSection title="Key Information">
        <DetailGrid>
          <DetailField label="Key Algorithm" value={csr.key_algorithm} />
          <DetailField label="Key Size" value={csr.key_size ? `${csr.key_size} bits` : null} />
          <DetailField label="Signature Algorithm" value={csr.signature_algorithm} />
        </DetailGrid>
      </DetailSection>

      {csr.san && csr.san.length > 0 && (
        <DetailSection title="Subject Alternative Names">
          <div className="flex flex-wrap gap-1">
            {csr.san.map((name, i) => (
              <Badge key={i} variant="secondary" size="sm">{name}</Badge>
            ))}
          </div>
        </DetailSection>
      )}
    </div>
  )

  // Help content
  const helpContent = (
    <div className="space-y-4">
      <HelpCard title="Certificate Signing Requests" variant="info">
        A CSR contains the public key and identity information needed to issue a certificate.
      </HelpCard>
      <HelpCard title="Status" variant="default">
        <ul className="text-sm space-y-1">
          <li><Badge variant="warning" size="sm">Pending</Badge> - Awaiting signature</li>
          <li><Badge variant="success" size="sm">Signed</Badge> - Certificate issued</li>
        </ul>
      </HelpCard>
      <HelpCard title="Workflow" variant="tip">
        1. Upload CSR → 2. Review details → 3. Sign with CA → 4. Download certificate
      </HelpCard>
    </div>
  )

  return (
    <>
      <ListPageLayout
        title="Certificate Signing Requests"
        data={csrs}
        columns={columns}
        loading={loading}
        selectedItem={selectedCSR}
        onSelectItem={(csr) => csr ? loadCSRDetails(csr) : setSelectedCSR(null)}
        renderDetails={renderDetails}
        detailsTitle="CSR Details"
        searchable
        searchPlaceholder="Search CSRs..."
        searchKeys={['common_name', 'subject', 'organization']}
        sortable
        defaultSort={{ key: 'created_at', direction: 'desc' }}
        paginated
        pageSize={25}
        rowActions={rowActions}
        emptyIcon={FileText}
        emptyTitle="No CSRs"
        emptyDescription="Upload a CSR to get started"
        emptyAction={canWrite('csrs') && (
          <Button onClick={() => openModal('upload')}>
            <UploadSimple size={16} /> Upload CSR
          </Button>
        )}
        helpContent={helpContent}
        actions={canWrite('csrs') && (
          <Button size="sm" onClick={() => openModal('upload')}>
            <UploadSimple size={16} /> Upload CSR
          </Button>
        )}
      />

      {/* Upload CSR Modal */}
      <Modal
        open={modals.upload}
        onClose={() => closeModal('upload')}
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
        onClose={() => closeModal('sign')}
        title="Sign CSR"
      >
        <div className="p-4 space-y-4">
          <p className="text-sm text-text-secondary">
            Sign this CSR with a Certificate Authority to issue a certificate
          </p>
          
          <Select
            label="Certificate Authority"
            options={cas.map(ca => ({ value: ca.id, label: ca.name || ca.common_name }))}
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

          <div className="flex justify-end gap-2 pt-4">
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
