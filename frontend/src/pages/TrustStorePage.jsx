/**
 * Trust Store Management Page
 * Manage trusted CA certificates for chain validation
 * Uses ResponsiveLayout for unified UI
 */
import { useState, useEffect, useMemo, useRef } from 'react'
import { 
  ShieldCheck, Plus, Trash, Download, Certificate, Clock,
  CheckCircle, Warning, UploadSimple, ArrowsClockwise
} from '@phosphor-icons/react'
import {
  Button, Input, Badge, Modal, Textarea, HelpCard,
  CompactSection, CompactHeader, CompactField, CompactStats
} from '../components'
import { ResponsiveLayout, ResponsiveDataTable } from '../components/ui/responsive'
import { truststoreService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useModals } from '../hooks'
import { formatDate, cn } from '../lib/utils'
import { ERRORS, SUCCESS, CONFIRM } from '../lib/messages'

export default function TrustStorePage() {
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canWrite, canDelete } = usePermission()
  const { modals, open: openModal, close: closeModal } = useModals(['add', 'import'])
  
  const [loading, setLoading] = useState(true)
  const [certificates, setCertificates] = useState([])
  const [certStats, setCertStats] = useState({ total: 0, root_ca: 0, intermediate_ca: 0, expired: 0, valid: 0 })
  const [selectedCert, setSelectedCert] = useState(null)
  const [syncing, setSyncing] = useState(false)
  
  // Pagination state
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  
  // Add modal state
  const [addForm, setAddForm] = useState({
    name: '',
    description: '',
    certificate_pem: '',
    purpose: 'custom',
    notes: ''
  })
  const [adding, setAdding] = useState(false)
  
  // Import modal state
  const [importFile, setImportFile] = useState(null)
  const [importForm, setImportForm] = useState({ name: '', purpose: 'root_ca', description: '' })
  const [importing, setImporting] = useState(false)

  useEffect(() => {
    loadCertificates()
  }, [])

  const loadCertificates = async () => {
    setLoading(true)
    try {
      const [certsRes, statsRes] = await Promise.all([
        truststoreService.getAll(),
        truststoreService.getStats()
      ])
      setCertificates(certsRes.data || [])
      setCertStats(statsRes.data || { total: 0, root_ca: 0, intermediate_ca: 0, expired: 0, valid: 0 })
    } catch (error) {
      showError(error.message || ERRORS.LOAD_FAILED.TRUSTSTORE)
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
      showError(ERRORS.VALIDATION.TRUSTSTORE_REQUIRED)
      return
    }
    
    setAdding(true)
    try {
      const response = await truststoreService.add(addForm)
      showSuccess(SUCCESS.IMPORT.TRUSTSTORE)
      closeModal('add')
      setAddForm({ name: '', description: '', certificate_pem: '', purpose: 'custom', notes: '' })
      loadCertificates()
      if (response.data) {
        setSelectedCert(response.data)
      }
    } catch (error) {
      showError(error.message || ERRORS.IMPORT_FAILED.TRUSTSTORE)
    } finally {
      setAdding(false)
    }
  }

  const handleImport = async () => {
    if (!importFile) {
      showError('Please select a file to import')
      return
    }
    
    setImporting(true)
    try {
      const response = await truststoreService.importFile(importFile, importForm)
      showSuccess(response.message || 'Certificate imported successfully')
      closeModal('import')
      setImportFile(null)
      setImportForm({ name: '', purpose: 'root_ca', description: '' })
      loadCertificates()
      if (response.data) {
        setSelectedCert(response.data)
      }
    } catch (error) {
      showError(error.message || 'Failed to import certificate')
    } finally {
      setImporting(false)
    }
  }

  const handleSyncFromSystem = async () => {
    const confirmed = await showConfirm(
      'This will import up to 50 certificates from the system CA bundle (/etc/ssl/certs). Continue?',
      { title: 'Sync from System', confirmText: 'Sync', variant: 'primary' }
    )
    if (!confirmed) return
    
    setSyncing(true)
    try {
      const response = await truststoreService.syncFromSystem(50)
      showSuccess(response.message || `Synced ${response.data?.new_count || 0} certificates`)
      loadCertificates()
    } catch (error) {
      showError(error.message || 'Failed to sync from system')
    } finally {
      setSyncing(false)
    }
  }

  const handleDelete = async (cert) => {
    const confirmed = await showConfirm(CONFIRM.DELETE.TRUSTSTORE, {
      title: 'Remove Certificate',
      confirmText: 'Remove',
      variant: 'danger'
    })
    if (!confirmed) return
    
    try {
      await truststoreService.delete(cert.id)
      showSuccess(SUCCESS.DELETE.TRUSTSTORE)
      loadCertificates()
      if (selectedCert?.id === cert.id) {
        setSelectedCert(null)
      }
    } catch (error) {
      showError(error.message || ERRORS.DELETE_FAILED.TRUSTSTORE)
    }
  }

  const handleExport = (cert) => {
    if (!cert?.certificate_pem) return
    
    const blob = new Blob([cert.certificate_pem], { type: 'application/x-pem-file' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${cert.name.replace(/\s+/g, '_')}.pem`
    a.click()
    URL.revokeObjectURL(url)
  }

  // Stats - from backend API
  const stats = useMemo(() => [
    { icon: ShieldCheck, label: 'Root CAs', value: certStats.root_ca, variant: 'success' },
    { icon: Certificate, label: 'Intermediate', value: certStats.intermediate_ca, variant: 'primary' },
    { icon: Warning, label: 'Expired', value: certStats.expired, variant: 'danger' },
    { icon: CheckCircle, label: 'Total', value: certStats.total, variant: 'default' }
  ], [certStats])

  // Columns
  const columns = [
    {
      key: 'name',
      header: 'Certificate',
      sortable: true,
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <Certificate size={16} className="text-accent-primary shrink-0" />
          <div className="min-w-0">
            <div className="font-medium truncate">{val}</div>
            {row.subject_cn && row.subject_cn !== val && (
              <div className="text-xs text-text-secondary truncate">{row.subject_cn}</div>
            )}
          </div>
        </div>
      )
    },
    {
      key: 'purpose',
      header: 'Purpose',
      render: (val) => {
        const variants = {
          root_ca: 'success',
          intermediate_ca: 'primary',
          client_auth: 'purple',
          code_signing: 'warning',
          system: 'secondary',
          custom: 'default'
        }
        return <Badge variant={variants[val] || 'default'} size="sm">{val?.replace('_', ' ')}</Badge>
      }
    },
    {
      key: 'not_after',
      header: 'Expires',
      render: (val) => {
        if (!val) return <span className="text-text-tertiary">—</span>
        const date = new Date(val)
        const isExpired = date < new Date()
        return (
          <span className={isExpired ? 'text-status-danger' : ''}>
            {formatDate(val)}
          </span>
        )
      }
    }
  ]

  // Row actions
  const rowActions = (row) => [
    { label: 'Export', icon: Download, onClick: () => handleExport(row) },
    ...(canDelete('truststore') ? [
      { label: 'Delete', icon: Trash, variant: 'danger', onClick: () => handleDelete(row) }
    ] : [])
  ]

  // Detail panel content
  const detailContent = selectedCert && (
    <div className="p-3 space-y-3">
      <CompactHeader
        icon={Certificate}
        iconClass="status-primary-bg"
        title={selectedCert.name}
        subtitle={selectedCert.subject_cn || selectedCert.description}
        badge={
          <Badge 
            variant={selectedCert.purpose === 'root_ca' ? 'success' : 'primary'} 
            size="sm"
          >
            {selectedCert.purpose?.replace('_', ' ')}
          </Badge>
        }
      />

      <CompactStats stats={[
        { icon: Clock, value: selectedCert.not_after ? formatDate(selectedCert.not_after) : 'No expiry' },
        { icon: CheckCircle, value: selectedCert.issuer_cn || 'Self-signed' }
      ]} />

      {/* Actions */}
      <div className="flex gap-2">
        <Button 
          size="sm" 
          variant="secondary"
          className="flex-1"
          onClick={() => handleExport(selectedCert)}
        >
          <Download size={14} />
          Export
        </Button>
        {canDelete('truststore') && (
          <Button 
            size="sm" 
            variant="danger"
            onClick={() => handleDelete(selectedCert)}
          >
            <Trash size={14} />
          </Button>
        )}
      </div>

      {/* Certificate Details */}
      <CompactSection title="Certificate Info" icon={Certificate}>
        <CompactField label="Subject" value={selectedCert.subject || selectedCert.subject_cn} />
        <CompactField label="Issuer" value={selectedCert.issuer || selectedCert.issuer_cn} />
        <CompactField label="Valid From" value={selectedCert.not_before ? formatDate(selectedCert.not_before) : '—'} />
        <CompactField label="Valid To" value={selectedCert.not_after ? formatDate(selectedCert.not_after) : '—'} />
        {selectedCert.fingerprint_sha256 && (
          <CompactField 
            label="SHA-256" 
            value={selectedCert.fingerprint_sha256} 
            mono 
            copyable 
          />
        )}
      </CompactSection>

      {selectedCert.notes && (
        <CompactSection title="Notes" icon={Warning}>
          <p className="text-sm text-text-secondary">{selectedCert.notes}</p>
        </CompactSection>
      )}
    </div>
  )

  // Help content
  const helpContent = (
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
  )

  return (
    <>
      <ResponsiveLayout
        title="Trust Store"
        subtitle={`${certificates.length} certificate${certificates.length !== 1 ? 's' : ''}`}
        icon={ShieldCheck}
        stats={stats}
        helpContent={helpContent}
        helpTitle="Trust Store Help"
        splitView={true}
        splitEmptyContent={
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
              <Certificate size={24} className="text-text-tertiary" />
            </div>
            <p className="text-sm text-text-secondary">Select a certificate to view details</p>
          </div>
        }
        slideOverOpen={!!selectedCert}
        slideOverTitle={selectedCert?.name || 'Certificate Details'}
        slideOverContent={detailContent}
        onSlideOverClose={() => setSelectedCert(null)}
      >
        <ResponsiveDataTable
          data={certificates}
          columns={columns}
          loading={loading}
          onRowClick={handleSelectCert}
          selectedId={selectedCert?.id}
          rowActions={rowActions}
          searchable
          searchPlaceholder="Search certificates..."
          searchKeys={['name', 'subject_cn', 'issuer_cn', 'purpose']}
          toolbarFilters={[
            {
              key: 'purpose',
              placeholder: 'All Purposes',
              options: [
                { value: 'root_ca', label: 'Root CA' },
                { value: 'intermediate_ca', label: 'Intermediate' },
                { value: 'client_auth', label: 'Client Auth' },
                { value: 'code_signing', label: 'Code Signing' },
                { value: 'system', label: 'System' },
                { value: 'custom', label: 'Custom' }
              ]
            }
          ]}
          toolbarActions={canWrite('truststore') && (
            <div className="flex gap-2">
              <Button variant="secondary" onClick={handleSyncFromSystem} disabled={syncing}>
                <ArrowsClockwise size={16} className={syncing ? 'animate-spin' : ''} />
                <span className="hidden sm:inline">{syncing ? 'Syncing...' : 'Sync'}</span>
              </Button>
              <Button variant="secondary" onClick={() => openModal('import')}>
                <UploadSimple size={16} />
                <span className="hidden sm:inline">Import</span>
              </Button>
              <Button onClick={() => openModal('add')}>
                <Plus size={16} />
                <span className="hidden sm:inline">Add</span>
              </Button>
            </div>
          )}
          sortable
          defaultSort={{ key: 'name', direction: 'asc' }}
          pagination={{
            page,
            total: certificates.length,
            perPage,
            onChange: setPage,
            onPerPageChange: (v) => { setPerPage(v); setPage(1) }
          }}
          emptyIcon={ShieldCheck}
          emptyTitle="No trusted certificates"
          emptyDescription="Add certificates to validate certificate chains"
          emptyAction={canWrite('truststore') && (
            <Button onClick={() => openModal('add')}>
              <Plus size={16} /> Add Certificate
            </Button>
          )}
        />
      </ResponsiveLayout>

      {/* Add Certificate Modal */}
      <Modal
        open={modals.add}
        onClose={() => closeModal('add')}
        title="Add Trusted Certificate"
      >
        <form className="p-4 space-y-4" onSubmit={(e) => { e.preventDefault(); handleAdd() }}>
          <Input
            label="Name"
            placeholder="e.g., DigiCert Global Root CA"
            value={addForm.name}
            onChange={(e) => setAddForm(prev => ({ ...prev, name: e.target.value }))}
            required
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
            required
          />
          <Input
            label="Notes"
            placeholder="Optional notes"
            value={addForm.notes}
            onChange={(e) => setAddForm(prev => ({ ...prev, notes: e.target.value }))}
          />
          <div className="flex justify-end gap-2 pt-4 border-t border-border">
            <Button type="button" variant="secondary" onClick={() => closeModal('add')}>
              Cancel
            </Button>
            <Button type="submit" disabled={adding}>
              {adding ? 'Adding...' : 'Add Certificate'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Import Certificate Modal */}
      <Modal
        open={modals.import}
        onClose={() => closeModal('import')}
        title="Import Certificate File"
      >
        <form className="p-4 space-y-4" onSubmit={(e) => { e.preventDefault(); handleImport() }}>
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1">
              Certificate File (PEM or DER)
            </label>
            <input
              type="file"
              accept=".pem,.crt,.cer,.der"
              onChange={(e) => {
                const file = e.target.files?.[0]
                setImportFile(file)
                if (file && !importForm.name) {
                  setImportForm(prev => ({ ...prev, name: file.name.replace(/\.(pem|crt|cer|der)$/i, '') }))
                }
              }}
              className="w-full px-3 py-2 text-sm bg-bg-secondary border border-border rounded-md text-text-primary file:mr-3 file:py-1 file:px-3 file:border-0 file:rounded file:bg-accent-primary file:text-white file:cursor-pointer"
            />
          </div>
          <Input
            label="Name"
            placeholder="Certificate name (auto-filled from filename)"
            value={importForm.name}
            onChange={(e) => setImportForm(prev => ({ ...prev, name: e.target.value }))}
          />
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1">Purpose</label>
            <select
              value={importForm.purpose}
              onChange={(e) => setImportForm(prev => ({ ...prev, purpose: e.target.value }))}
              className="w-full px-3 py-2 text-sm bg-bg-secondary border border-border rounded-md text-text-primary"
            >
              <option value="root_ca">Root CA</option>
              <option value="intermediate_ca">Intermediate CA</option>
              <option value="client_auth">Client Authentication</option>
              <option value="code_signing">Code Signing</option>
              <option value="custom">Custom</option>
            </select>
          </div>
          <Input
            label="Description"
            placeholder="Optional description"
            value={importForm.description}
            onChange={(e) => setImportForm(prev => ({ ...prev, description: e.target.value }))}
          />
          <div className="flex justify-end gap-2 pt-4 border-t border-border">
            <Button type="button" variant="secondary" onClick={() => closeModal('import')}>
              Cancel
            </Button>
            <Button type="submit" disabled={importing || !importFile}>
              {importing ? 'Importing...' : 'Import Certificate'}
            </Button>
          </div>
        </form>
      </Modal>
    </>
  )
}
