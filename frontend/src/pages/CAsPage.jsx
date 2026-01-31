/**
 * CAs (Certificate Authorities) Page - Using ListPageLayout for consistent UI
 */
import { useState, useEffect, useRef, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { 
  ShieldCheck, Crown, Key, Download, Trash, PencilSimple,
  Certificate, UploadSimple, Clock, Plus, Warning
} from '@phosphor-icons/react'
import {
  ListPageLayout, Badge, Button, Modal, Input, Select, HelpCard, LoadingSpinner,
  CompactSection, CompactGrid, CompactField, CompactStats, CompactHeader
} from '../components'
import { casService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useModals } from '../hooks'
import { extractData, formatDate, cn } from '../lib/utils'

export default function CAsPage() {
  const { showSuccess, showError, showConfirm, showPrompt } = useNotification()
  const { canWrite, canDelete } = usePermission()
  const [searchParams, setSearchParams] = useSearchParams()
  
  const [cas, setCAs] = useState([])
  const [selectedCA, setSelectedCA] = useState(null)
  const [loading, setLoading] = useState(true)
  const { modals, open: openModal, close: closeModal } = useModals(['create', 'import'])
  const [createFormType, setCreateFormType] = useState('root')
  const [importFile, setImportFile] = useState(null)
  const [importName, setImportName] = useState('')
  const [importPassword, setImportPassword] = useState('')
  const [importing, setImporting] = useState(false)
  const importFileRef = useRef(null)

  useEffect(() => {
    loadCAs()
    if (searchParams.get('action') === 'create') {
      openModal('create')
      searchParams.delete('action')
      setSearchParams(searchParams)
    }
  }, [])

  // Handle selected param from navigation
  useEffect(() => {
    const selectedId = searchParams.get('selected')
    if (selectedId && cas.length > 0) {
      const ca = cas.find(c => c.id === parseInt(selectedId))
      if (ca) {
        loadCADetails(ca)
        searchParams.delete('selected')
        setSearchParams(searchParams)
      }
    }
  }, [cas, searchParams])

  const loadCAs = async () => {
    setLoading(true)
    try {
      const casData = await casService.getAll()
      const casList = casData.data || []
      setCAs(casList)
    } catch (error) {
      showError(error.message || 'Failed to load CAs')
    } finally {
      setLoading(false)
    }
  }

  const loadCADetails = async (ca) => {
    try {
      const caData = await casService.getById(ca.id)
      setSelectedCA(extractData(caData) || ca)
    } catch {
      setSelectedCA(ca)
    }
  }

  const handleDelete = async (id) => {
    const confirmed = await showConfirm('Are you sure you want to delete this CA? This action cannot be undone.', {
      title: 'Delete Certificate Authority',
      confirmText: 'Delete CA',
      variant: 'danger'
    })
    if (!confirmed) return
    
    try {
      await casService.delete(id)
      showSuccess('CA deleted successfully')
      loadCAs()
      setSelectedCA(null)
    } catch (error) {
      showError(error.message || 'Failed to delete CA')
    }
  }

  const handleImportCA = async () => {
    if (!importFile) {
      showError('Please select a file')
      return
    }
    setImporting(true)
    try {
      const formData = new FormData()
      formData.append('file', importFile)
      if (importName) formData.append('name', importName)
      if (importPassword) formData.append('password', importPassword)
      formData.append('format', 'auto')
      
      const result = await casService.import(formData)
      showSuccess(result.message || 'CA imported successfully')
      closeModal('import')
      setImportFile(null)
      setImportName('')
      setImportPassword('')
      await loadCAs()
      
      if (result.data) {
        setSelectedCA(result.data)
      }
    } catch (error) {
      showError(error.message || 'Failed to import CA')
    } finally {
      setImporting(false)
    }
  }

  const handleExport = async (ca, format = 'pem') => {
    try {
      const blob = await casService.export(ca.id, format, {})
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const ext = format === 'pkcs12' ? 'p12' : format === 'der' ? 'der' : 'pem'
      a.download = `${ca.name || ca.common_name || 'ca'}.${ext}`
      a.click()
      URL.revokeObjectURL(url)
      showSuccess('CA exported successfully')
    } catch (error) {
      showError(error.message || 'Failed to export CA')
    }
  }

  // Check if intermediate CA is orphan (no parent found in our list)
  const isOrphanIntermediate = (ca) => {
    if (ca.type !== 'intermediate') return false
    if (!ca.parent_id) return true // No parent_id means orphan
    // Check if parent exists in our CA list
    return !cas.some(c => c.id === ca.parent_id)
  }

  // Table filters
  const tableFilters = useMemo(() => [
    {
      key: 'type',
      label: 'Type',
      options: [
        { value: 'root', label: 'Root CA' },
        { value: 'intermediate', label: 'Intermediate' }
      ]
    },
    {
      key: 'status',
      label: 'Status',
      options: [
        { value: 'Active', label: 'Active' },
        { value: 'Expired', label: 'Expired' },
        { value: 'Revoked', label: 'Revoked' }
      ]
    }
  ], [])

  // Table columns
  const columns = [
    {
      key: 'name',
      header: 'Name',
      render: (val, row) => (
        <div className="flex items-center gap-2">
          {row.type === 'root' ? (
            <Crown size={16} weight="duotone" className="text-yellow-500 shrink-0" />
          ) : (
            <ShieldCheck size={16} weight="duotone" className="text-blue-500 shrink-0" />
          )}
          <span className="font-medium truncate">{val || row.common_name || 'CA'}</span>
          {isOrphanIntermediate(row) && (
            <Badge variant="warning" size="sm" className="ml-1">
              <Warning size={12} className="mr-0.5" /> orphan
            </Badge>
          )}
        </div>
      )
    },
    {
      key: 'type',
      header: 'Type',
      render: (val) => (
        <Badge variant={val === 'root' ? 'primary' : 'secondary'} size="sm">
          {val || 'unknown'}
        </Badge>
      )
    },
    {
      key: 'status',
      header: 'Status',
      render: (val) => (
        <Badge 
          variant={val === 'Active' ? 'success' : val === 'Expired' ? 'danger' : 'warning'}
          size="sm"
        >
          {val || 'Unknown'}
        </Badge>
      )
    },
    {
      key: 'certs',
      header: 'Certificates',
      render: (val) => val || 0
    },
    {
      key: 'valid_to',
      header: 'Expires',
      sortType: 'date',
      render: (val) => formatDate(val)
    }
  ]

  // Row actions
  const rowActions = (row) => [
    { label: 'Export PEM', icon: Download, onClick: () => handleExport(row, 'pem') },
    ...(canWrite('cas') ? [
      { label: 'Edit', icon: PencilSimple, onClick: () => {} }
    ] : []),
    ...(canDelete('cas') ? [
      { label: 'Delete', icon: Trash, variant: 'danger', onClick: () => handleDelete(row.id) }
    ] : [])
  ]

  // Render details panel
  const renderDetails = (ca) => (
    <div className="p-3 space-y-3">
      {/* Header */}
      <CompactHeader
        icon={ca.type === 'root' ? Crown : ShieldCheck}
        iconClass={ca.type === 'root' ? "bg-amber-500/20" : "bg-accent-primary/20"}
        title={ca.name || ca.common_name}
        subtitle={ca.subject}
        badge={
          <Badge variant={ca.status === 'Active' ? 'success' : 'danger'} size="sm">
            {ca.status}
          </Badge>
        }
      />

      {/* Stats */}
      <CompactStats stats={[
        { icon: Certificate, iconClass: "text-accent-primary", value: `${ca.certs || 0} certs` },
        { icon: Key, value: ca.key_algorithm || 'RSA' },
        { badge: ca.type, badgeVariant: ca.type === 'root' ? 'primary' : 'secondary' }
      ]} />

      {/* Actions */}
      <div className="flex gap-2">
        <Button size="sm" variant="secondary" className="flex-1" onClick={() => handleExport(ca, 'pem')}>
          <Download size={14} /> Export
        </Button>
        {canDelete('cas') && (
          <Button size="sm" variant="danger" onClick={() => handleDelete(ca.id)}>
            <Trash size={14} />
          </Button>
        )}
      </div>

      {/* Subject */}
      <CompactSection title="Subject">
        <CompactGrid>
          <CompactField label="CN" value={ca.common_name} />
          <CompactField label="O" value={ca.organization} />
          <CompactField label="C" value={ca.country} />
          <CompactField label="ST" value={ca.state} />
        </CompactGrid>
      </CompactSection>

      {/* Validity */}
      <CompactSection title="Validity">
        <CompactGrid>
          <CompactField label="From" value={formatDate(ca.valid_from)} />
          <CompactField label="Until" value={formatDate(ca.valid_to)} />
        </CompactGrid>
      </CompactSection>

      {/* Technical */}
      <CompactSection title="Technical">
        <CompactGrid>
          <CompactField label="Key" value={ca.key_algorithm || ca.key_type} />
          <div className="text-xs">
            <span className="text-text-tertiary">Private:</span>
            <span className={cn("ml-1", ca.has_private_key ? "text-status-success" : "text-status-error")}>
              {ca.has_private_key ? 'Yes' : 'No'}
            </span>
          </div>
          <CompactField label="Signature" value={ca.signature_algorithm || ca.hash_algorithm} className="col-span-2" />
        </CompactGrid>
      </CompactSection>

      {/* Serial */}
      <CompactSection title="Serial Number">
        <p className="font-mono text-xs text-text-primary break-all">{ca.serial === 0 ? '0' : (ca.serial || '—')}</p>
      </CompactSection>

      {/* DN */}
      {ca.subject && (
        <CompactSection title="Distinguished Names">
          <div className="space-y-2">
            <div>
              <span className="text-[10px] text-text-tertiary block mb-0.5">Subject DN</span>
              <p className="font-mono text-[11px] text-text-primary break-all">{ca.subject}</p>
            </div>
            <div className="border-t border-border pt-2">
              <span className="text-[10px] text-text-tertiary block mb-0.5">Issuer DN</span>
              <p className="font-mono text-[11px] text-text-primary break-all">{ca.issuer}</p>
            </div>
          </div>
        </CompactSection>
      )}
    </div>
  )

  // Help content
  const helpContent = (
    <div className="space-y-4">
      <HelpCard title="Certificate Authorities" variant="info">
        CAs are trusted entities that issue digital certificates.
        Root CAs are self-signed, Intermediate CAs are signed by a parent.
      </HelpCard>
      <HelpCard title="CA Types" variant="default">
        <ul className="text-sm space-y-1">
          <li><Badge variant="primary" size="sm">Root</Badge> - Self-signed, top of trust chain</li>
          <li><Badge variant="secondary" size="sm">Intermediate</Badge> - Signed by parent CA</li>
        </ul>
      </HelpCard>
      <HelpCard title="Best Practice" variant="tip">
        Keep Root CA private keys offline. Use Intermediate CAs for issuing end-entity certificates.
      </HelpCard>
    </div>
  )

  return (
    <>
      <ListPageLayout
        title="Certificate Authorities"
        data={cas}
        columns={columns}
        loading={loading}
        selectedItem={selectedCA}
        onSelectItem={(ca) => ca ? loadCADetails(ca) : setSelectedCA(null)}
        renderDetails={renderDetails}
        detailsTitle="CA Details"
        searchable
        searchPlaceholder="Search CAs..."
        searchKeys={['name', 'common_name', 'subject']}
        sortable
        defaultSort={{ key: 'type', direction: 'asc' }}
        paginated
        pageSize={25}
        rowActions={rowActions}
        filters={tableFilters}
        hierarchical
        parentKey="parent_id"
        defaultExpanded={true}
        emptyIcon={ShieldCheck}
        emptyTitle="No Certificate Authorities"
        emptyDescription="Create your first CA to get started"
        emptyAction={canWrite('cas') && (
          <Button onClick={() => openModal('create')}>
            <Plus size={16} /> Create CA
          </Button>
        )}
        helpContent={helpContent}
        actions={canWrite('cas') && (
          <>
            <Button size="sm" onClick={() => openModal('create')}>
              <Plus size={16} /> Create
            </Button>
            <Button size="sm" variant="secondary" onClick={() => openModal('import')}>
              <UploadSimple size={16} /> Import
            </Button>
          </>
        )}
      />

      {/* Create CA Modal */}
      <Modal
        open={modals.create}
        onClose={() => closeModal('create')}
        title="Create Certificate Authority"
        size="lg"
      >
        <form onSubmit={async (e) => {
          e.preventDefault()
          const formData = new FormData(e.target)
          const data = {
            commonName: formData.get('commonName'),
            organization: formData.get('organization'),
            country: formData.get('country'),
            state: formData.get('state'),
            locality: formData.get('locality'),
            keyAlgo: formData.get('keyAlgo'),
            keySize: parseInt(formData.get('keySize')),
            validityYears: parseInt(formData.get('validityYears')),
            type: formData.get('type'),
            parentCAId: formData.get('type') === 'intermediate' ? formData.get('parentCAId') : null
          }
          
          try {
            await casService.create(data)
            showSuccess('CA created successfully')
            closeModal('create')
            loadCAs()
          } catch (error) {
            showError(error.message || 'Failed to create CA')
          }
        }} className="space-y-6">
          
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-text-primary">Subject Information</h3>
            <Input name="commonName" label="Common Name (CN)" placeholder="My Certificate Authority" required />
            <div className="grid grid-cols-2 gap-4">
              <Input name="organization" label="Organization (O)" placeholder="My Company" />
              <Input name="country" label="Country (C)" placeholder="US" maxLength={2} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Input name="state" label="State/Province (ST)" placeholder="California" />
              <Input name="locality" label="City/Locality (L)" placeholder="San Francisco" />
            </div>
          </div>

          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-text-primary">Key Configuration</h3>
            <div className="grid grid-cols-2 gap-4">
              <Select
                name="keyAlgo"
                label="Key Algorithm"
                options={[
                  { value: 'RSA', label: 'RSA' },
                  { value: 'ECDSA', label: 'ECDSA' }
                ]}
                defaultValue="RSA"
              />
              <Select
                name="keySize"
                label="Key Size"
                options={[
                  { value: '2048', label: '2048 bits' },
                  { value: '3072', label: '3072 bits' },
                  { value: '4096', label: '4096 bits' }
                ]}
                defaultValue="2048"
              />
            </div>
          </div>

          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-text-primary">Validity</h3>
            <Select
              name="validityYears"
              label="Validity Period"
              options={[
                { value: '5', label: '5 years' },
                { value: '10', label: '10 years' },
                { value: '15', label: '15 years' },
                { value: '20', label: '20 years' }
              ]}
              defaultValue="10"
            />
          </div>

          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-text-primary">CA Type</h3>
            <Select
              name="type"
              label="Type"
              options={[
                { value: 'root', label: 'Root CA (Self-signed)' },
                { value: 'intermediate', label: 'Intermediate CA (Signed by parent)' }
              ]}
              value={createFormType}
              onChange={(value) => setCreateFormType(value)}
            />
            {createFormType === 'intermediate' && (
              <Select
                name="parentCAId"
                label="Parent CA"
                options={cas.map(ca => ({
                  value: ca.id.toString(),
                  label: ca.name || ca.descr
                }))}
                required
              />
            )}
          </div>

          <div className="flex gap-3 justify-end pt-4 border-t border-border">
            <Button type="button" variant="secondary" onClick={() => closeModal('create')}>
              Cancel
            </Button>
            <Button type="submit">Create CA</Button>
          </div>
        </form>
      </Modal>

      {/* Import CA Modal */}
      <Modal
        open={modals.import}
        onClose={() => closeModal('import')}
        title="Import CA"
        size="md"
      >
        <div className="space-y-4">
          <p className="text-sm text-text-secondary">
            Import an existing CA certificate. Supports PEM, DER, and PKCS#12 formats.
          </p>
          
          <div>
            <label className="block text-xs font-medium text-text-primary mb-1">CA Certificate File</label>
            <input
              ref={importFileRef}
              type="file"
              accept=".pem,.crt,.cer,.der,.p12,.pfx"
              onChange={(e) => setImportFile(e.target.files[0])}
              className="w-full text-sm text-text-secondary file:mr-4 file:py-1.5 file:px-3 file:rounded-sm file:border-0 file:text-sm file:bg-accent-primary file:text-white hover:file:bg-accent-primary/80"
            />
            <p className="text-xs text-text-secondary mt-1">Accepted: .pem, .crt, .cer, .der, .p12, .pfx</p>
          </div>
          
          <Input 
            label="Display Name (optional)" 
            value={importName}
            onChange={(e) => setImportName(e.target.value)}
            placeholder="My Root CA"
          />
          
          <Input 
            label="Password (for PKCS#12)" 
            type="password"
            value={importPassword}
            onChange={(e) => setImportPassword(e.target.value)}
            placeholder="Enter password if needed"
          />
          
          <div className="flex gap-3 justify-end pt-4 border-t border-border">
            <Button variant="secondary" onClick={() => closeModal('import')}>Cancel</Button>
            <Button onClick={handleImportCA} disabled={importing || !importFile}>
              {importing ? <LoadingSpinner size="sm" /> : <UploadSimple size={16} />}
              Import CA
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}
