/**
 * CSRs (Certificate Signing Requests) Page - Using TablePageLayout (Audit pattern)
 */
import { useState, useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { 
  FileText, Upload, SignIn, Trash, Download, 
  Clock, Key, UploadSimple, CheckCircle, Warning, X
} from '@phosphor-icons/react'
import {
  TablePageLayout, Badge, Button, Modal, Input, Select, HelpCard, FileUpload,
  CSRDetails
} from '../components'
import { csrsService, casService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useModals } from '../hooks'
import { extractData, formatDate, cn } from '../lib/utils'
import { VALIDITY } from '../constants/config'

export default function CSRsPage() {
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
  const [search, setSearch] = useState('')
  
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

  useEffect(() => {
    setPage(1)
  }, [filterStatus, search])

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
      { icon: Warning, label: 'Pending', value: pending, color: 'text-amber-500' },
      { icon: CheckCircle, label: 'Signed', value: signed, color: 'text-emerald-500' },
      { icon: X, label: 'Rejected', value: rejected, color: 'text-red-500' },
      { icon: FileText, label: 'Total', value: csrs.length, color: 'text-accent-primary' }
    ]
  }, [csrs])

  // Table columns
  const columns = [
    {
      key: 'cn',
      label: 'Common Name',
      sortable: true,
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <FileText size={16} className="text-accent-primary shrink-0" />
          <span className="font-medium truncate">{val}</span>
        </div>
      )
    },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
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
      label: 'Created',
      sortable: true,
      render: (val) => (
        <span className="text-xs text-text-secondary whitespace-nowrap">
          {formatDate(val)}
        </span>
      )
    },
    {
      key: 'key_algorithm',
      label: 'Key',
      render: (val, row) => (
        <span className="text-xs font-mono text-text-secondary">
          {val || 'RSA'} {row.key_size ? `(${row.key_size})` : ''}
        </span>
      )
    }
  ]

  // Filters config
  const filters = [
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
  ]

  // Quick filters
  const quickFilters = [
    {
      icon: Warning,
      title: 'Pending',
      subtitle: 'Awaiting signature',
      selected: filterStatus === 'pending',
      onClick: () => setFilterStatus(filterStatus === 'pending' ? '' : 'pending')
    },
    {
      icon: CheckCircle,
      title: 'Signed',
      subtitle: 'Certificates issued',
      selected: filterStatus === 'signed',
      onClick: () => setFilterStatus(filterStatus === 'signed' ? '' : 'signed')
    }
  ]

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

  const handleClearFilters = () => {
    setFilterStatus('')
    setSearch('')
  }

  return (
    <>
      <TablePageLayout
        title="Certificate Signing Requests"
        loading={loading}
        data={filteredCSRs}
        columns={columns}
        searchable
        searchPlaceholder="Search CSRs..."
        searchKeys={['cn', 'common_name', 'subject', 'organization']}
        externalSearch={search}
        onSearch={setSearch}
        onRowClick={loadCSRDetails}
        filters={filters}
        quickFilters={quickFilters}
        onClearFilters={handleClearFilters}
        stats={stats}
        helpContent={helpContent}
        onRefresh={loadData}
        emptyIcon={FileText}
        emptyTitle="No CSRs"
        emptyDescription="Upload a CSR to get started"
        emptyAction={canWrite('csrs') && (
          <Button onClick={() => openModal('upload')}>
            <UploadSimple size={16} /> Upload CSR
          </Button>
        )}
        actions={canWrite('csrs') && (
          <Button size="sm" onClick={() => openModal('upload')} className="flex-1">
            <UploadSimple size={14} /> Upload
          </Button>
        )}
        pagination={{
          page,
          total: filteredCSRs.length,
          perPage,
          onChange: setPage,
          onPerPageChange: (v) => { setPerPage(v); setPage(1) }
        }}
      />

      {/* CSR Details Modal */}
      <Modal
        open={!!selectedCSR}
        onOpenChange={() => setSelectedCSR(null)}
        title="CSR Details"
        size="lg"
      >
        {selectedCSR && (
          <CSRDetails
            csr={selectedCSR}
            onSign={() => openModal('sign')}
            onDownload={() => handleDownload(selectedCSR.id)}
            onDelete={() => handleDelete(selectedCSR.id)}
            canWrite={canWrite('csrs')}
            canDelete={canDelete('csrs')}
          />
        )}
      </Modal>

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
