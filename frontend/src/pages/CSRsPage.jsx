/**
 * CSRs (Certificate Signing Requests) Page
 */
import { useState, useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { FileText, Upload, SignIn, Trash, Download, FileArrowUp } from '@phosphor-icons/react'
import {
  ExplorerPanel, DetailsPanel, Table, Button, Badge,
  Modal, Input, Select, Textarea,
  FileUpload, LoadingSpinner, EmptyState
} from '../components'
import { csrsService, casService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks/usePermission'
import { extractData } from '../lib/utils'

export default function CSRsPage() {
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canWrite, canDelete } = usePermission()
  const [searchParams, setSearchParams] = useSearchParams()
  const fileRef = useRef(null)
  
  const [csrs, setCSRs] = useState([])
  const [selectedCSR, setSelectedCSR] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)
  const [showSignModal, setShowSignModal] = useState(false)
  const [cas, setCAs] = useState([])
  const [signCA, setSignCA] = useState('')
  const [validityDays, setValidityDays] = useState(365)
  
  // Import form state
  const [importFile, setImportFile] = useState(null)
  const [importPem, setImportPem] = useState('')
  const [importName, setImportName] = useState('')
  const [importing, setImporting] = useState(false)

  useEffect(() => {
    loadCSRs()
    loadCAs()
    // Check if we should auto-open upload modal
    if (searchParams.get('action') === 'upload') {
      setShowUploadModal(true)
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
      setShowUploadModal(false)
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
      setShowSignModal(false)
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
      setShowImportModal(false)
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

  const csrColumns = [
    { 
      key: 'common_name', 
      label: 'Common Name',
      render: (val) => <span className="font-medium">{val}</span>
    },
    { key: 'key_algorithm', label: 'Algorithm' },
    { key: 'key_size', label: 'Key Size', render: (val) => `${val} bits` },
    { 
      key: 'created_at', 
      label: 'Created',
      render: (val) => new Date(val).toLocaleDateString()
    },
    {
      key: 'status',
      label: 'Status',
      render: (val) => (
        <Badge variant={val === 'pending' ? 'warning' : 'success'}>
          {val}
        </Badge>
      )
    },
  ]

  return (
    <>
      <ExplorerPanel
        title="CSRs"
        footer={
          <div className="text-xs text-text-secondary">
            {csrs.length} total CSRs
          </div>
        }
      >
        <div className="p-4 space-y-3">
          {canWrite('csrs') && (
            <>
              <Button onClick={() => setShowUploadModal(true)} className="w-full">
                <Upload size={18} />
                Create CSR
              </Button>
              <Button variant="secondary" onClick={() => setShowImportModal(true)} className="w-full">
                <FileArrowUp size={18} />
                Import CSR
              </Button>
            </>
          )}
        </div>

        <div className="flex-1 overflow-auto">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <LoadingSpinner />
            </div>
          ) : csrs.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="No CSRs"
              description="Create or import a Certificate Signing Request"
              action={{
                label: 'Import CSR',
                onClick: () => setShowImportModal(true)
              }}
            />
          ) : (
            <Table
              columns={csrColumns}
              data={csrs}
              onRowClick={(csr) => loadCSRDetails(csr.id)}
            />
          )}
        </div>
      </ExplorerPanel>

      <DetailsPanel
        breadcrumb={[
          { label: 'CSRs' },
          { label: selectedCSR?.common_name || '...' }
        ]}
        title={selectedCSR?.common_name || 'Select a CSR'}
        actions={selectedCSR && (
          <>
            {canWrite('csrs') && (
              <Button 
                variant="primary" 
                size="sm" 
                onClick={() => setShowSignModal(true)}
                disabled={selectedCSR.status !== 'pending'}
              >
                <SignIn size={16} />
                Sign
              </Button>
            )}
            <Button variant="secondary" size="sm" onClick={() => handleDownload(selectedCSR.id)}>
              <Download size={16} />
              Download
            </Button>
            {canDelete('csrs') && (
              <Button variant="danger" size="sm" onClick={() => handleDelete(selectedCSR.id)}>
                <Trash size={16} />
                Delete
              </Button>
            )}
          </>
        )}
      >
        {!selectedCSR ? (
          <EmptyState
            title="No CSR selected"
            description="Select a CSR from the list to view details"
          />
        ) : (
          <div className="space-y-6">
            {/* Request Info */}
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-4">Request Information</h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-xs text-text-secondary uppercase mb-1">Common Name</p>
                  <p className="text-sm text-text-primary">{selectedCSR.common_name}</p>
                </div>
                <div>
                  <p className="text-xs text-text-secondary uppercase mb-1">Status</p>
                  <Badge variant={selectedCSR.status === 'pending' ? 'warning' : 'success'}>
                    {selectedCSR.status}
                  </Badge>
                </div>
                <div>
                  <p className="text-xs text-text-secondary uppercase mb-1">Key Algorithm</p>
                  <p className="text-sm text-text-primary">{selectedCSR.key_algorithm}</p>
                </div>
                <div>
                  <p className="text-xs text-text-secondary uppercase mb-1">Key Size</p>
                  <p className="text-sm text-text-primary">{selectedCSR.key_size} bits</p>
                </div>
                <div className="col-span-2">
                  <p className="text-xs text-text-secondary uppercase mb-1">Subject DN</p>
                  <p className="text-sm text-text-primary">{selectedCSR.subject}</p>
                </div>
                <div>
                  <p className="text-xs text-text-secondary uppercase mb-1">Signature Algorithm</p>
                  <p className="text-sm text-text-primary">{selectedCSR.signature_algorithm}</p>
                </div>
                <div>
                  <p className="text-xs text-text-secondary uppercase mb-1">Created</p>
                  <p className="text-sm text-text-primary">
                    {new Date(selectedCSR.created_at).toLocaleString()}
                  </p>
                </div>
              </div>
            </div>

            {/* Subject Alternative Names */}
            {selectedCSR.san && selectedCSR.san.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-text-primary mb-4">Subject Alternative Names</h3>
                <div className="flex flex-wrap gap-2">
                  {selectedCSR.san.map((name, i) => (
                    <Badge key={i} variant="secondary">{name}</Badge>
                  ))}
                </div>
              </div>
            )}

            {/* Raw CSR */}
            <div>
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-text-primary">Raw CSR (PEM)</h3>
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
              <pre className="bg-bg-tertiary border border-border rounded-lg p-4 text-xs overflow-x-auto max-h-64">
                {selectedCSR.csr_pem || selectedCSR.pem || 'PEM data not available'}
              </pre>
            </div>
          </div>
        )}
      </DetailsPanel>

      {/* Import CSR Modal */}
      <Modal
        open={showImportModal}
        onClose={() => setShowImportModal(false)}
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
            <Button variant="secondary" onClick={() => setShowImportModal(false)}>Cancel</Button>
            <Button onClick={handleImportCSR} disabled={importing || (!importFile && !importPem.trim())}>
              {importing ? <LoadingSpinner size="sm" /> : <FileArrowUp size={16} />}
              Import CSR
            </Button>
          </div>
        </div>
      </Modal>

      {/* Create CSR Modal */}
      <Modal
        open={showUploadModal}
        onClose={() => setShowUploadModal(false)}
        title="Create CSR"
      >
        <div className="space-y-4">
          <p className="text-sm text-text-secondary">
            Create a new Certificate Signing Request
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
        open={showSignModal}
        onClose={() => setShowSignModal(false)}
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
            <Button variant="ghost" onClick={() => setShowSignModal(false)}>
              Cancel
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}
