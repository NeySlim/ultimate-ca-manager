/**
 * Trust Store Management Page
 * Manage trusted CA certificates for chain validation
 */
import { useState, useEffect } from 'react'
import { 
  ShieldCheck, Plus, Trash, Download, Certificate, Clock,
  MagnifyingGlass, Info
} from '@phosphor-icons/react'
import {
  PageLayout, FocusItem, Button, Input, Card, Badge, 
  Modal, Textarea, LoadingSpinner, EmptyState, HelpCard,
  DetailHeader, DetailSection, DetailGrid, DetailField, DetailContent
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
    return <Badge variant={variants[purpose] || 'default'} size="sm">{purpose?.replace('_', ' ')}</Badge>
  }

  const purposeColors = {
    root_ca: 'bg-emerald-500/15 text-emerald-500',
    intermediate_ca: 'bg-blue-500/15 text-blue-500',
    client_auth: 'bg-purple-500/15 text-purple-500',
    code_signing: 'bg-orange-500/15 text-orange-500',
    system: 'bg-gray-500/15 text-gray-400',
    custom: 'bg-gray-500/15 text-gray-400'
  }

  // Calculate stats by purpose
  const rootCAs = certificates.filter(c => c.purpose === 'root_ca').length
  const intermediateCAs = certificates.filter(c => c.purpose === 'intermediate_ca').length

  // Help content for modal
  const helpContent = (
    <div className="space-y-4">
      {/* Trust Store Overview */}
      <Card className="p-4 space-y-3 bg-gradient-to-br from-emerald-500/5 to-transparent">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <ShieldCheck size={16} className="text-emerald-500" />
          Trust Store Overview
        </h3>
        <div className="text-center p-4 bg-bg-tertiary rounded-lg">
          <p className="text-3xl font-bold text-text-primary">{certificates.length}</p>
          <p className="text-sm text-text-secondary">Trusted Certificates</p>
        </div>
      </Card>

      {/* Certificate Breakdown */}
      <Card className="p-4 space-y-3">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Info size={16} className="text-accent-primary" />
          By Purpose
        </h3>
        <div className="space-y-2">
          <div className="flex items-center justify-between py-2 px-3 rounded-md bg-bg-tertiary/50">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-emerald-500" />
              <span className="text-sm text-text-primary">Root CAs</span>
            </div>
            <Badge variant="emerald">{rootCAs}</Badge>
          </div>
          <div className="flex items-center justify-between py-2 px-3 rounded-md bg-bg-tertiary/50">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-blue-500" />
              <span className="text-sm text-text-primary">Intermediate CAs</span>
            </div>
            <Badge variant="blue">{intermediateCAs}</Badge>
          </div>
        </div>
      </Card>

      {/* Help Cards */}
      <div className="space-y-3">
        <HelpCard variant="info" title="About Trust Store">
          The Trust Store contains certificates that are explicitly trusted for validating 
          certificate chains. Add Root and Intermediate CAs here for chain verification.
        </HelpCard>
        
        <HelpCard variant="tip" title="Best Practices">
          Only add certificates from trusted sources. Regularly review and remove 
          expired or unnecessary certificates to maintain security.
        </HelpCard>

        <HelpCard variant="warning" title="Security Note">
          Certificates in the Trust Store can validate any certificate chain. 
          Be careful when adding third-party certificates.
        </HelpCard>
      </div>
    </div>
  )

  // Focus panel content with search and filter
  const focusContent = (
    <div className="flex flex-col h-full">
      {/* Search */}
      <div className="p-2 border-b border-border shrink-0">
        <div className="relative">
          <MagnifyingGlass size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-text-secondary" />
          <input
            type="text"
            placeholder="Search..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-7 pr-2 py-1.5 text-xs bg-bg-tertiary border border-border rounded-md text-text-primary placeholder:text-text-secondary"
          />
        </div>
      </div>

      {/* Filter */}
      <div className="p-2 border-b border-border shrink-0">
        <select
          value={purposeFilter}
          onChange={(e) => setPurposeFilter(e.target.value)}
          className="w-full px-2 py-1.5 text-xs bg-bg-tertiary border border-border rounded-md text-text-primary"
        >
          {purposeOptions.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>

      {/* Certificate List */}
      <div className="flex-1 overflow-auto p-2 space-y-1">
        {certificates.length === 0 ? (
          <EmptyState 
            icon={ShieldCheck}
            title="No certificates"
            description="Add trusted certificates"
          />
        ) : (
          certificates.map((cert) => (
            <FocusItem
              key={cert.id}
              icon={Certificate}
              title={cert.name}
              subtitle={cert.not_after ? formatDate(cert.not_after) : 'No expiry'}
              badge={getPurposeBadge(cert.purpose)}
              selected={selectedCert?.id === cert.id}
              onClick={() => handleSelectCert(cert)}
            />
          ))
        )}
      </div>
    </div>
  )

  // Focus panel actions
  const focusActions = canWrite && (
    <Button size="sm" onClick={() => openModal('add')} className="w-full">
      <Plus size={14} />
      Add Certificate
    </Button>
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
      <PageLayout
        title="Trust Store"
        focusTitle="Certificates"
        focusContent={focusContent}
        focusActions={focusActions}
        focusFooter={`${certificates.length} certificate(s)`}
        helpContent={helpContent}
        helpTitle="Trust Store - Aide"
      >
        {/* Main Content */}
        {!selectedCert ? (
          <div className="flex items-center justify-center h-full">
            <EmptyState 
              icon={Certificate}
              title="Select a certificate"
              description="Choose a certificate to view details"
            />
          </div>
        ) : (
          <>
            {/* Header with gradient card style */}
            <div className="p-4 md:p-6">
              <DetailHeader
                icon={ShieldCheck}
                title={selectedCert.name}
                subtitle={selectedCert.subject}
                badge={getPurposeBadge(selectedCert.purpose)}
                actions={[
                  {
                    label: 'Export PEM',
                    icon: Download,
                    onClick: () => handleExport(selectedCert)
                  },
                  ...(canDelete ? [{
                    label: 'Remove',
                    icon: Trash,
                    variant: 'danger',
                    onClick: () => handleDelete(selectedCert.id)
                  }] : [])
                ]}
              />
            </div>

            {/* Content */}
            <DetailContent>
              {/* Certificate Information */}
              <DetailSection title="Certificate Information">
                <DetailGrid columns={2}>
                  <DetailField label="Name" value={selectedCert.name} />
                  <DetailField label="Purpose" value={selectedCert.purpose?.replace('_', ' ')} />
                  <DetailField label="Subject" value={selectedCert.subject} mono copyable fullWidth />
                  <DetailField label="Issuer" value={selectedCert.issuer} mono copyable fullWidth />
                  <DetailField label="Serial Number" value={selectedCert.serial_number} mono copyable />
                  <DetailField label="Valid From" value={selectedCert.not_before ? formatDate(selectedCert.not_before) : null} />
                  <DetailField label="Valid Until" value={selectedCert.not_after ? formatDate(selectedCert.not_after) : null} />
                </DetailGrid>
              </DetailSection>

              {/* Fingerprints */}
              <DetailSection title="Fingerprints">
                <DetailGrid columns={1}>
                  <DetailField label="SHA-256" value={selectedCert.fingerprint_sha256} mono copyable fullWidth />
                  <DetailField label="SHA-1" value={selectedCert.fingerprint_sha1} mono copyable fullWidth />
                </DetailGrid>
              </DetailSection>
            </DetailContent>
          </>
        )}
      </PageLayout>

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
            <Button size="sm" variant="ghost" onClick={() => closeModal('add')}>
              Cancel
            </Button>
            <Button size="sm" onClick={handleAdd} disabled={adding}>
              {adding ? 'Adding...' : 'Add Certificate'}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}
