/**
 * Trust Store Management Page
 * Manage trusted CA certificates for chain validation
 */
import { useState, useEffect } from 'react'
import { 
  ShieldCheck, Plus, Trash, Download, Upload, Certificate,
  MagnifyingGlass, ArrowsClockwise, CheckCircle, Warning, Info
} from '@phosphor-icons/react'
import {
  ExplorerPanel, DetailsPanel, Button, Input, Card, Badge, 
  Table, Modal, Textarea, LoadingSpinner, EmptyState, HelpCard
} from '../components'
import { truststoreService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useModals } from '../hooks'
import { formatDate } from '../lib/utils'

export default function TrustStorePage() {
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canWrite, canDelete } = usePermission()
  const { modals, open: openModal, close: closeModal } = useModals(['add'])
  
  const [loading, setLoading] = useState(true)
  const [certificates, setCertificates] = useState([])
  const [selectedCert, setSelectedCert] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [purposeFilter, setPurposeFilter] = useState('all')
  
  // Add modal state
  const [addForm, setAddForm] = useState({
    name: '',
    description: '',
    certificate_pem: '',
    purpose: 'custom',
    notes: ''
  })
  const [adding, setAdding] = useState(false)

  useEffect(() => {
    loadCertificates()
  }, [searchQuery, purposeFilter])

  const loadCertificates = async () => {
    setLoading(true)
    try {
      const response = await truststoreService.getAll({
        search: searchQuery || undefined,
        purpose: purposeFilter !== 'all' ? purposeFilter : undefined
      })
      const certs = response.data || []
      setCertificates(certs)
      if (certs.length > 0 && !selectedCert) {
        setSelectedCert(certs[0])
      }
    } catch (error) {
      showError(error.message || 'Failed to load trust store')
    } finally {
      setLoading(false)
    }
  }

  const handleSelectCert = async (cert) => {
    try {
      const response = await truststoreService.getById(cert.id)
      setSelectedCert(response.data || cert)
    } catch (error) {
      setSelectedCert(cert)
    }
  }

  const handleAdd = async () => {
    if (!addForm.name || !addForm.certificate_pem) {
      showError('Name and certificate are required')
      return
    }
    
    setAdding(true)
    try {
      const response = await truststoreService.add(addForm)
      showSuccess('Certificate added to trust store')
      closeModal('add')
      setAddForm({ name: '', description: '', certificate_pem: '', purpose: 'custom', notes: '' })
      loadCertificates()
      if (response.data) {
        setSelectedCert(response.data)
      }
    } catch (error) {
      showError(error.message || 'Failed to add certificate')
    } finally {
      setAdding(false)
    }
  }

  const handleDelete = async (id) => {
    const confirmed = await showConfirm('Remove this certificate from the trust store?', {
      title: 'Remove Certificate',
      confirmText: 'Remove',
      variant: 'danger'
    })
    if (!confirmed) return
    
    try {
      await truststoreService.delete(id)
      showSuccess('Certificate removed from trust store')
      loadCertificates()
      if (selectedCert?.id === id) {
        setSelectedCert(null)
      }
    } catch (error) {
      showError(error.message || 'Failed to remove certificate')
    }
  }

  const handleExport = async (cert) => {
    if (!cert?.certificate_pem) return
    
    const blob = new Blob([cert.certificate_pem], { type: 'application/x-pem-file' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${cert.name.replace(/\s+/g, '_')}.pem`
    a.click()
    URL.revokeObjectURL(url)
  }

  const purposeOptions = [
    { value: 'all', label: 'All Purposes' },
    { value: 'root_ca', label: 'Root CA' },
    { value: 'intermediate_ca', label: 'Intermediate CA' },
    { value: 'client_auth', label: 'Client Auth' },
    { value: 'code_signing', label: 'Code Signing' },
    { value: 'system', label: 'System' },
    { value: 'custom', label: 'Custom' },
  ]

  const getPurposeBadge = (purpose) => {
    const variants = {
      root_ca: 'emerald',
      intermediate_ca: 'blue',
      client_auth: 'purple',
      code_signing: 'orange',
      system: 'secondary',
      custom: 'default'
    }
    return <Badge variant={variants[purpose] || 'default'}>{purpose?.replace('_', ' ')}</Badge>
  }

  // Sidebar content
  const sidebarContent = (
    <div className="space-y-4">
      {/* Stats */}
      <div className="space-y-2">
        <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wide">Overview</h3>
        <Card className="p-3 space-y-2 bg-gradient-to-br from-accent-primary/5 to-transparent">
          <div className="flex items-center justify-between text-xs">
            <span className="text-text-secondary">Total Certificates</span>
            <span className="text-text-primary font-medium">{certificates.length}</span>
          </div>
          <div className="flex items-center justify-between text-xs">
            <span className="text-text-secondary">Root CAs</span>
            <span className="text-text-primary font-medium">
              {certificates.filter(c => c.purpose === 'root_ca').length}
            </span>
          </div>
          <div className="flex items-center justify-between text-xs">
            <span className="text-text-secondary">Intermediate CAs</span>
            <span className="text-text-primary font-medium">
              {certificates.filter(c => c.purpose === 'intermediate_ca').length}
            </span>
          </div>
        </Card>
      </div>

      {/* Filter */}
      <div className="space-y-2">
        <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wide">Filter</h3>
        <select
          value={purposeFilter}
          onChange={(e) => setPurposeFilter(e.target.value)}
          className="w-full px-2 py-1.5 text-xs bg-bg-secondary border border-border rounded-md text-text-primary"
        >
          {purposeOptions.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>

      {/* Actions */}
      <div className="space-y-2">
        <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wide">Actions</h3>
        <div className="space-y-1">
          {canWrite && (
            <Button 
              variant="ghost" 
              size="sm" 
              className="w-full justify-start text-xs"
              onClick={() => openModal('add')}
            >
              <Plus size={14} />
              Add Certificate
            </Button>
          )}
          <Button 
            variant="ghost" 
            size="sm" 
            className="w-full justify-start text-xs"
            onClick={() => loadCertificates()}
          >
            <ArrowsClockwise size={14} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Help */}
      <HelpCard variant="info" className="text-xs">
        <p className="font-medium mb-1">Trust Store</p>
        <p className="text-text-secondary">
          Certificates here are trusted for chain validation during certificate verification.
        </p>
      </HelpCard>
    </div>
  )

  if (loading && certificates.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner />
      </div>
    )
  }

  return (
    <>
      <div className="flex h-full">
        {/* Explorer Panel */}
        <ExplorerPanel 
          title="Trust Store"
          width="300px"
          sidebarContent={sidebarContent}
          actions={
            canWrite && (
              <Button size="sm" onClick={() => openModal('add')}>
                <Plus size={14} />
                Add
              </Button>
            )
          }
        >
          {/* Search */}
          <div className="p-2 border-b border-border">
            <div className="relative">
              <MagnifyingGlass size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-text-secondary" />
              <input
                type="text"
                placeholder="Search certificates..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-7 pr-2 py-1.5 text-xs bg-bg-secondary border border-border rounded-md text-text-primary placeholder:text-text-secondary"
              />
            </div>
          </div>

          {/* Certificate List */}
          <div className="p-2 space-y-1">
            {certificates.length === 0 ? (
              <EmptyState 
                icon={ShieldCheck}
                title="No certificates"
                description="Add trusted certificates to the store"
              />
            ) : (
              certificates.map((cert) => (
                <div
                  key={cert.id}
                  onClick={() => handleSelectCert(cert)}
                  className={`
                    p-2 rounded-md cursor-pointer transition-colors
                    ${selectedCert?.id === cert.id 
                      ? 'bg-accent-primary/10 border border-accent-primary/30' 
                      : 'hover:bg-bg-tertiary border border-transparent'
                    }
                  `}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-text-primary truncate">
                      {cert.name}
                    </span>
                    {getPurposeBadge(cert.purpose)}
                  </div>
                  <div className="text-xs text-text-secondary mt-0.5 truncate">
                    {cert.subject}
                  </div>
                </div>
              ))
            )}
          </div>
        </ExplorerPanel>

        {/* Details Panel */}
        <DetailsPanel title={selectedCert ? selectedCert.name : 'Certificate Details'}>
          {!selectedCert ? (
            <EmptyState 
              icon={Certificate}
              title="Select a certificate"
              description="Choose a certificate to view details"
            />
          ) : (
            <div className="p-4 space-y-6">
              {/* Certificate Info */}
              <div>
                <h3 className="text-sm font-semibold text-text-primary mb-4">Certificate Information</h3>
                <div className="grid grid-cols-2 gap-4">
                  <div className="col-span-2">
                    <p className="text-xs text-text-secondary uppercase mb-1">Name</p>
                    <p className="text-sm text-text-primary">{selectedCert.name}</p>
                  </div>
                  <div className="col-span-2">
                    <p className="text-xs text-text-secondary uppercase mb-1">Subject</p>
                    <p className="text-xs font-mono text-text-primary break-all">{selectedCert.subject}</p>
                  </div>
                  <div className="col-span-2">
                    <p className="text-xs text-text-secondary uppercase mb-1">Issuer</p>
                    <p className="text-xs font-mono text-text-primary break-all">{selectedCert.issuer}</p>
                  </div>
                  <div>
                    <p className="text-xs text-text-secondary uppercase mb-1">Purpose</p>
                    {getPurposeBadge(selectedCert.purpose)}
                  </div>
                  <div>
                    <p className="text-xs text-text-secondary uppercase mb-1">Serial Number</p>
                    <p className="text-xs font-mono text-text-primary">{selectedCert.serial_number}</p>
                  </div>
                  <div>
                    <p className="text-xs text-text-secondary uppercase mb-1">Valid From</p>
                    <p className="text-sm text-text-primary">
                      {selectedCert.not_before ? formatDate(selectedCert.not_before) : '-'}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-text-secondary uppercase mb-1">Valid Until</p>
                    <p className="text-sm text-text-primary">
                      {selectedCert.not_after ? formatDate(selectedCert.not_after) : '-'}
                    </p>
                  </div>
                </div>
              </div>

              {/* Fingerprints */}
              <div>
                <h3 className="text-sm font-semibold text-text-primary mb-4">Fingerprints</h3>
                <div className="space-y-3">
                  <div>
                    <p className="text-xs text-text-secondary uppercase mb-1">SHA-256</p>
                    <code className="text-xs font-mono text-text-primary bg-bg-tertiary px-2 py-1 rounded block break-all">
                      {selectedCert.fingerprint_sha256}
                    </code>
                  </div>
                  <div>
                    <p className="text-xs text-text-secondary uppercase mb-1">SHA-1</p>
                    <code className="text-xs font-mono text-text-primary bg-bg-tertiary px-2 py-1 rounded block break-all">
                      {selectedCert.fingerprint_sha1}
                    </code>
                  </div>
                </div>
              </div>

              {/* Metadata */}
              <div>
                <h3 className="text-sm font-semibold text-text-primary mb-4">Metadata</h3>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-text-secondary uppercase mb-1">Added By</p>
                    <p className="text-sm text-text-primary">{selectedCert.added_by || '-'}</p>
                  </div>
                  <div>
                    <p className="text-xs text-text-secondary uppercase mb-1">Added At</p>
                    <p className="text-sm text-text-primary">
                      {selectedCert.added_at ? formatDate(selectedCert.added_at) : '-'}
                    </p>
                  </div>
                  {selectedCert.notes && (
                    <div className="col-span-2">
                      <p className="text-xs text-text-secondary uppercase mb-1">Notes</p>
                      <p className="text-sm text-text-primary">{selectedCert.notes}</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-2 pt-4 border-t border-border">
                <Button 
                  variant="secondary"
                  onClick={() => handleExport(selectedCert)}
                >
                  <Download size={16} />
                  Export PEM
                </Button>
                {canDelete && (
                  <Button 
                    variant="danger"
                    onClick={() => handleDelete(selectedCert.id)}
                  >
                    <Trash size={16} />
                    Remove
                  </Button>
                )}
              </div>
            </div>
          )}
        </DetailsPanel>
      </div>

      {/* Add Certificate Modal */}
      <Modal
        open={modals.add}
        onClose={() => closeModal('add')}
        title="Add Trusted Certificate"
      >
        <div className="space-y-4">
          <Input
            label="Name"
            placeholder="e.g., DigiCert Global Root CA"
            value={addForm.name}
            onChange={(e) => setAddForm(prev => ({ ...prev, name: e.target.value }))}
          />
          <Input
            label="Description"
            placeholder="Optional description"
            value={addForm.description}
            onChange={(e) => setAddForm(prev => ({ ...prev, description: e.target.value }))}
          />
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1">Purpose</label>
            <select
              value={addForm.purpose}
              onChange={(e) => setAddForm(prev => ({ ...prev, purpose: e.target.value }))}
              className="w-full px-3 py-2 text-sm bg-bg-secondary border border-border rounded-md text-text-primary"
            >
              <option value="root_ca">Root CA</option>
              <option value="intermediate_ca">Intermediate CA</option>
              <option value="client_auth">Client Authentication</option>
              <option value="code_signing">Code Signing</option>
              <option value="custom">Custom</option>
            </select>
          </div>
          <Textarea
            label="Certificate (PEM)"
            placeholder="-----BEGIN CERTIFICATE-----&#10;...&#10;-----END CERTIFICATE-----"
            value={addForm.certificate_pem}
            onChange={(e) => setAddForm(prev => ({ ...prev, certificate_pem: e.target.value }))}
            rows={8}
            className="font-mono text-xs"
          />
          <Input
            label="Notes"
            placeholder="Optional notes"
            value={addForm.notes}
            onChange={(e) => setAddForm(prev => ({ ...prev, notes: e.target.value }))}
          />
          <div className="flex gap-2 justify-end pt-4 border-t border-border">
            <Button variant="ghost" onClick={() => closeModal('add')}>
              Cancel
            </Button>
            <Button onClick={handleAdd} disabled={adding}>
              {adding ? 'Adding...' : 'Add Certificate'}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}
