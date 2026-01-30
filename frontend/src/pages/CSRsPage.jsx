/**
 * CSRs (Certificate Signing Requests) Page
 * Uses PageLayout with Responsive Components for consistent UI structure
 */
import { useState, useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { 
  FileText, Upload, SignIn, Trash, Download, FileArrowUp, 
  CheckCircle, HourglassHigh, MagnifyingGlass, Database
} from '@phosphor-icons/react'
import {
  PageLayout, FocusItem, Button, Badge, Card,
  Modal, Input, Select,
  FileUpload, LoadingSpinner, EmptyState, HelpCard,
  DetailHeader, DetailSection, DetailGrid, DetailField, DetailContent
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
  const { modals, open: openModal, close: closeModal } = useModals(['upload', 'import', 'sign'])
  
  const [csrs, setCSRs] = useState([])
  const [selectedCSR, setSelectedCSR] = useState(null)
  const [loading, setLoading] = useState(true)
  const [cas, setCAs] = useState([])
  const [signCA, setSignCA] = useState('')
  const [validityDays, setValidityDays] = useState(VALIDITY.DEFAULT_DAYS)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  
  // Import form state
  const [importFile, setImportFile] = useState(null)
  const [importPem, setImportPem] = useState('')
  const [importName, setImportName] = useState('')
  const [importing, setImporting] = useState(false)

  useEffect(() => {
    loadCSRs()
    loadCAs()
    if (searchParams.get('action') === 'upload') {
      openModal('upload')
      searchParams.delete('action')
      setSearchParams(searchParams)
    }
  }, [])

  const loadCSRs = async () => {
    setLoading(true)
    try {
      const data = await csrsService.getAll()
      const csrsList = data.data || []
      setCSRs(csrsList)
      if (csrsList.length > 0 && !selectedCSR) {
        loadCSRDetails(csrsList[0].id)
      }
    } catch (error) {
      showError(error.message || 'Failed to load CSRs')
    } finally {
      setLoading(false)
    }
  }

  const loadCAs = async () => {
    try {
      const data = await casService.getAll()
      setCAs(data.cas || [])
    } catch (error) {
      console.error('Failed to load CAs:', error)
    }
  }

  const loadCSRDetails = async (id) => {
    try {
      const response = await csrsService.getById(id)
      const data = extractData(response)
      setSelectedCSR({ ...data })
    } catch (error) {
      console.error('Failed to load CSR:', error)
      showError(error.message || 'Failed to load CSR details')
    }
  }

  const handleUpload = async (files) => {
    try {
      const file = files[0]
      const text = await file.text()
      await csrsService.upload(text)
      showSuccess('CSR uploaded successfully')
      closeModal('upload')
      loadCSRs()
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
      loadCSRs()
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
      loadCSRs()
      setSelectedCSR(null)
    } catch (error) {
      showError(error.message || 'Failed to delete CSR')
    }
  }

  const handleImportCSR = async () => {
    if (!importFile && !importPem.trim()) {
      showError('Please select a file or paste PEM content')
      return
    }
    setImporting(true)
    try {
      const formData = new FormData()
      if (importFile) {
        formData.append('file', importFile)
      } else {
        formData.append('pem_content', importPem)
      }
      if (importName) formData.append('name', importName)
      
      const result = await csrsService.import(formData)
      showSuccess(result.message || 'CSR imported successfully')
      closeModal('import')
      setImportFile(null)
      setImportPem('')
      setImportName('')
      if (fileRef.current) fileRef.current.value = ''
      loadCSRs()
      
      // Auto-select imported CSR
      if (result.data?.id) {
        loadCSRDetails(result.data.id)
      }
    } catch (error) {
      showError(error.message || 'Failed to import CSR')
    } finally {
      setImporting(false)
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

  // Stats computed from CSRs
  const stats = {
    total: csrs.length,
    pending: csrs.filter(c => c.status === 'pending').length,
    signed: csrs.filter(c => c.status === 'signed').length
  }

  // Filter CSRs based on search and status
  const filteredCSRs = csrs.filter(csr => {
    const matchesSearch = !searchQuery || 
      csr.common_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      csr.subject?.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesStatus = statusFilter === 'all' || csr.status === statusFilter
    return matchesSearch && matchesStatus
  })

  // Help content for modal
  const helpContent = (
    <div className="space-y-4">
      {/* CSR Statistics */}
      <Card className="p-4 space-y-3 bg-gradient-to-br from-accent-primary/5 to-transparent">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Database size={16} className="text-accent-primary" />
          CSR Statistics
        </h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-yellow-500">{stats.pending}</p>
            <p className="text-xs text-text-secondary">Pending</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-emerald-500">{stats.signed}</p>
            <p className="text-xs text-text-secondary">Signed</p>
          </div>
        </div>
      </Card>

      {/* Help Cards */}
      <div className="space-y-3">
        <HelpCard variant="info" title="What is a CSR?">
          A Certificate Signing Request (CSR) contains the public key and identity 
          information needed to issue a certificate. The private key remains with the requester.
        </HelpCard>
        
        <HelpCard variant="tip" title="CSR Workflow">
          1. Upload or import a CSR from an external source
          2. Review the request details and subject information
          3. Sign with a CA to issue a certificate
          4. Download and deploy the issued certificate
        </HelpCard>

        <HelpCard variant="warning" title="Best Practices">
          Always verify the CSR subject and key details before signing. 
          Ensure the common name matches the intended use (domain, server, etc.).
        </HelpCard>
      </div>
    </div>
  )

  // Focus panel content (search, filter, CSR list)
  const focusContent = (
    <div className="flex flex-col h-full">
      {/* Search */}
      <div className="p-3 border-b border-border">
        <div className="relative">
          <MagnifyingGlass size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-tertiary" />
          <input
            type="text"
            placeholder="Search CSRs..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-sm bg-bg-tertiary border border-border rounded-md text-text-primary placeholder-text-tertiary focus:outline-none focus:ring-1 focus:ring-accent-primary"
          />
        </div>
      </div>

      {/* Status Filter */}
      <div className="px-3 py-2 border-b border-border flex gap-1.5">
        {['all', 'pending', 'signed'].map((status) => (
          <button
            key={status}
            onClick={() => setStatusFilter(status)}
            className={`px-2 py-1 text-xs rounded-md transition-colors ${
              statusFilter === status
                ? 'bg-accent-primary/20 text-accent-primary border border-accent-primary/40'
                : 'bg-bg-tertiary text-text-secondary hover:bg-bg-tertiary/80 border border-transparent'
            }`}
          >
            {status === 'all' ? 'All' : status.charAt(0).toUpperCase() + status.slice(1)}
          </button>
        ))}
      </div>

      {/* CSR List */}
      <div className="flex-1 overflow-auto p-2 space-y-1.5">
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <LoadingSpinner />
          </div>
        ) : filteredCSRs.length === 0 ? (
          <EmptyState 
            icon={FileText}
            title="No CSRs"
            description={searchQuery ? "No CSRs match your search" : "Upload or import a CSR to get started"}
          />
        ) : (
          filteredCSRs.map((csr) => (
            <FocusItem
              key={csr.id}
              icon={FileText}
              title={csr.common_name || 'Unnamed CSR'}
              subtitle={csr.created_at ? `Created ${formatDate(csr.created_at)}` : 'No date'}
              badge={
                <Badge 
                  variant={csr.status === 'pending' ? 'warning' : 'success'} 
                  size="sm"
                >
                  {csr.status}
                </Badge>
              }
              selected={selectedCSR?.id === csr.id}
              onClick={() => loadCSRDetails(csr.id)}
            />
          ))
        )}
      </div>
    </div>
  )

  // Focus panel actions (upload button)
  const focusActions = canWrite('csrs') ? (
    <>
      <Button size="sm" onClick={() => openModal('upload')} className="flex-1">
        <Upload size={14} />
        Upload
      </Button>
      <Button size="sm" variant="secondary" onClick={() => openModal('import')} className="flex-1">
        <FileArrowUp size={14} />
        Import
      </Button>
    </>
  ) : null

  if (loading && csrs.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner />
      </div>
    )
  }

  return (
    <>
      <PageLayout
        title="Certificate Signing Requests"
        focusTitle="CSRs"
        focusContent={focusContent}
        focusActions={focusActions}
        focusFooter={`${filteredCSRs.length} of ${csrs.length} CSR(s)`}
        helpContent={helpContent}
        helpTitle="CSRs - Aide"
      >
        {/* Main Content - CSR Details */}
        {!selectedCSR ? (
          <div className="flex items-center justify-center h-full">
            <EmptyState
              icon={FileText}
              title="Select a CSR"
              description="Choose a CSR from the list to view details"
            />
          </div>
        ) : (
          <>
            {/* Header with gradient card style */}
            <div className="p-4 md:p-6">
              <DetailHeader
                icon={FileText}
                title={selectedCSR.common_name || 'Unnamed CSR'}
                subtitle={selectedCSR.subject || 'No subject information'}
                badge={
                  <Badge 
                    variant={selectedCSR.status === 'pending' ? 'amber' : 'emerald'} 
                    size="lg"
                  >
                    {selectedCSR.status === 'pending' && <HourglassHigh size={14} weight="fill" />}
                    {selectedCSR.status === 'signed' && <CheckCircle size={14} weight="fill" />}
                    {selectedCSR.status}
                  </Badge>
                }
                stats={[
                  { icon: Database, label: 'Key:', value: selectedCSR.key_algorithm || 'RSA' },
                  ...(selectedCSR.key_size ? [{ icon: Database, label: 'Size:', value: `${selectedCSR.key_size} bits` }] : []),
                ]}
                actions={[
                  ...(canWrite('csrs') && selectedCSR.status === 'pending' ? [{
                    label: 'Sign',
                    icon: SignIn,
                    onClick: () => openModal('sign'),
                  }] : []),
                  {
                    label: 'Download',
                    icon: Download,
                    onClick: () => handleDownload(selectedCSR.id),
                  },
                  ...(canDelete('csrs') ? [{
                    label: 'Delete',
                    icon: Trash,
                    variant: 'danger',
                    onClick: () => handleDelete(selectedCSR.id),
                  }] : []),
                ]}
              />
            </div>

            {/* Content */}
            <DetailContent>
              {/* Request Information */}
              <DetailSection title="Request Information">
                <DetailGrid columns={2}>
                  <DetailField label="Common Name" value={selectedCSR.common_name} />
                  <DetailField 
                    label="Status" 
                    value={
                      <Badge variant={selectedCSR.status === 'pending' ? 'warning' : 'success'}>
                        {selectedCSR.status}
                      </Badge>
                    }
                  />
                  <DetailField label="Key Algorithm" value={selectedCSR.key_algorithm} />
                  <DetailField label="Key Size" value={selectedCSR.key_size ? `${selectedCSR.key_size} bits` : null} />
                  <DetailField label="Signature Algorithm" value={selectedCSR.signature_algorithm} />
                  <DetailField label="Created" value={selectedCSR.created_at ? new Date(selectedCSR.created_at).toLocaleString() : null} />
                  <DetailField label="Subject DN" value={selectedCSR.subject} mono copyable fullWidth />
                </DetailGrid>
              </DetailSection>

              {/* Subject Alternative Names */}
              {selectedCSR.san && selectedCSR.san.length > 0 && (
                <DetailSection title="Subject Alternative Names">
                  <div className="flex flex-wrap gap-2">
                    {selectedCSR.san.map((name, i) => (
                      <Badge key={i} variant="secondary">{name}</Badge>
                    ))}
                  </div>
                </DetailSection>
              )}

              {/* Raw CSR (PEM) */}
              <DetailSection title="Raw CSR (PEM)">
                <div className="flex items-center justify-end mb-2">
                  <Button 
                    variant="secondary" 
                    size="sm"
                    onClick={() => {
                      navigator.clipboard.writeText(selectedCSR.csr_pem || selectedCSR.pem || '')
                      showSuccess('CSR PEM copied to clipboard')
                    }}
                    disabled={!selectedCSR.csr_pem && !selectedCSR.pem}
                  >
                    Copy PEM
                  </Button>
                </div>
                <pre className="bg-bg-tertiary border border-border rounded-lg p-4 text-xs overflow-x-auto max-h-64 font-mono">
                  {selectedCSR.csr_pem || selectedCSR.pem || 'PEM data not available'}
                </pre>
              </DetailSection>
            </DetailContent>
          </>
        )}
      </PageLayout>

      {/* Import CSR Modal */}
      <Modal
        open={modals.import}
        onClose={() => closeModal('import')}
        title="Import CSR"
      >
        <div className="space-y-4">
          <p className="text-sm text-text-secondary">
            Import a Certificate Signing Request from a file or paste PEM content
          </p>
          
          <div>
            <label className="block text-xs font-medium text-text-primary mb-1">CSR File</label>
            <input
              ref={fileRef}
              type="file"
              accept=".pem,.csr,.req"
              onChange={(e) => { setImportFile(e.target.files[0]); setImportPem('') }}
              className="w-full text-sm text-text-secondary file:mr-4 file:py-1.5 file:px-3 file:rounded-sm file:border-0 file:text-sm file:bg-accent-primary file:text-white hover:file:bg-accent-primary/80"
            />
          </div>
          
          <div className="flex items-center gap-3">
            <div className="flex-1 border-t border-border"></div>
            <span className="text-xs text-text-secondary">OR paste PEM content</span>
            <div className="flex-1 border-t border-border"></div>
          </div>
          
          <div>
            <label className="block text-xs font-medium text-text-primary mb-1">Paste PEM Content</label>
            <textarea
              value={importPem}
              onChange={(e) => { setImportPem(e.target.value); setImportFile(null); if (fileRef.current) fileRef.current.value = '' }}
              placeholder="-----BEGIN CERTIFICATE REQUEST-----&#10;...&#10;-----END CERTIFICATE REQUEST-----"
              rows={6}
              className="w-full px-2 py-1.5 bg-bg-secondary border border-border rounded-sm text-sm text-text-primary font-mono placeholder-text-secondary focus:outline-none focus:ring-1 focus:ring-accent-primary resize-y"
            />
          </div>
          
          <Input 
            label="Display Name (optional)" 
            value={importName}
            onChange={(e) => setImportName(e.target.value)}
            placeholder="My CSR"
          />
          
          <div className="flex justify-end gap-3 pt-2">
            <Button variant="secondary" onClick={() => closeModal('import')}>Cancel</Button>
            <Button onClick={handleImportCSR} disabled={importing || (!importFile && !importPem.trim())}>
              {importing ? <LoadingSpinner size="sm" /> : <FileArrowUp size={16} />}
              Import CSR
            </Button>
          </div>
        </div>
      </Modal>

      {/* Create CSR Modal */}
      <Modal
        open={modals.upload}
        onClose={() => closeModal('upload')}
        title="Upload CSR"
      >
        <div className="space-y-4">
          <p className="text-sm text-text-secondary">
            Upload a Certificate Signing Request file
          </p>
          <FileUpload
            accept=".pem,.csr"
            onUpload={handleUpload}
            maxSize={1024 * 1024} // 1MB
          />
        </div>
      </Modal>

      {/* Sign CSR Modal */}
      <Modal
        open={modals.sign}
        onClose={() => closeModal('sign')}
        title="Sign CSR"
      >
        <div className="space-y-4">
          <p className="text-sm text-text-secondary">
            Sign this Certificate Signing Request with a Certificate Authority
          </p>
          
          <Select
            label="Certificate Authority"
            options={cas.map(ca => ({ value: ca.id, label: ca.name }))}
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

          <div className="flex gap-3 pt-4">
            <Button onClick={handleSign} disabled={!signCA}>
              <SignIn size={16} />
              Sign CSR
            </Button>
            <Button variant="ghost" onClick={() => closeModal('sign')}>
              Cancel
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}
