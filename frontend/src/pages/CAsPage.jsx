/**
 * CAs (Certificate Authorities) Page - Using ResponsiveLayout
 */
import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { 
  ShieldCheck, Crown, Key, Download, Trash, PencilSimple,
  Certificate, UploadSimple, Clock, Plus, Warning, CaretRight, CaretDown
} from '@phosphor-icons/react'
import {
  Badge, Button, Modal, Input, Select, HelpCard, LoadingSpinner,
  CompactSection, CompactGrid, CompactField, CompactHeader, CompactStats
} from '../components'
import { ResponsiveLayout } from '../components/ui/responsive'
import { casService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useModals } from '../hooks'
import { useMobile } from '../contexts/MobileContext'
import { extractData, formatDate, cn } from '../lib/utils'

export default function CAsPage() {
  const { isMobile } = useMobile()
  const { showSuccess, showError, showConfirm } = useNotification()
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
  
  // Filter state
  const [filterType, setFilterType] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  
  // Tree expanded state
  const [expandedNodes, setExpandedNodes] = useState(new Set())

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

  // Expand all root nodes by default
  useEffect(() => {
    if (cas.length > 0 && expandedNodes.size === 0) {
      const rootIds = cas.filter(c => !c.parent_id || c.type === 'root').map(c => c.id)
      setExpandedNodes(new Set(rootIds))
    }
  }, [cas])

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

  const handleCreateCA = async (e) => {
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
  }

  // Check if intermediate CA is orphan
  const isOrphanIntermediate = useCallback((ca) => {
    if (ca.type !== 'intermediate') return false
    if (!ca.parent_id) return true
    return !cas.some(c => c.id === ca.parent_id)
  }, [cas])

  // Build tree structure
  const treeData = useMemo(() => {
    const rootCAs = cas.filter(ca => !ca.parent_id || ca.type === 'root' || isOrphanIntermediate(ca))
    
    const buildTree = (parentId) => {
      return cas
        .filter(ca => ca.parent_id === parentId && ca.type !== 'root')
        .map(ca => ({
          ...ca,
          children: buildTree(ca.id)
        }))
    }
    
    return rootCAs.map(ca => ({
      ...ca,
      children: buildTree(ca.id)
    }))
  }, [cas, isOrphanIntermediate])

  // Filter tree
  const filteredTree = useMemo(() => {
    let result = treeData
    
    // Apply search
    if (searchQuery) {
      const query = searchQuery.toLowerCase()
      const matches = (ca) => 
        (ca.name || '').toLowerCase().includes(query) ||
        (ca.common_name || '').toLowerCase().includes(query) ||
        (ca.subject || '').toLowerCase().includes(query)
      
      const filterTree = (nodes) => nodes.filter(node => {
        if (matches(node)) return true
        if (node.children?.length) {
          node.children = filterTree(node.children)
          return node.children.length > 0
        }
        return false
      })
      result = filterTree([...result])
    }
    
    // Apply type filter
    if (filterType) {
      const filterByType = (nodes) => nodes.filter(node => {
        if (node.type === filterType) return true
        if (node.children?.length) {
          node.children = filterByType(node.children)
          return node.children.length > 0
        }
        return false
      })
      result = filterByType([...result])
    }
    
    return result
  }, [treeData, searchQuery, filterType])

  // Stats
  const stats = useMemo(() => {
    const rootCount = cas.filter(c => c.type === 'root').length
    const intermediateCount = cas.filter(c => c.type === 'intermediate').length
    const activeCount = cas.filter(c => c.status === 'Active').length
    const expiredCount = cas.filter(c => c.status === 'Expired').length
    
    return [
      { icon: Crown, label: 'Root', value: rootCount, variant: 'warning' },
      { icon: ShieldCheck, label: 'Intermediate', value: intermediateCount, variant: 'primary' },
      { icon: Certificate, label: 'Active', value: activeCount, variant: 'success' },
      { icon: Clock, label: 'Expired', value: expiredCount, variant: 'danger' }
    ]
  }, [cas])

  // Filters config
  const filters = useMemo(() => [
    {
      key: 'type',
      label: 'Type',
      type: 'select',
      value: filterType,
      onChange: setFilterType,
      placeholder: 'All Types',
      options: [
        { value: 'root', label: 'Root CA' },
        { value: 'intermediate', label: 'Intermediate' }
      ]
    }
  ], [filterType])

  const activeFiltersCount = (filterType ? 1 : 0)

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

  // Toggle tree node
  const toggleNode = (id) => {
    setExpandedNodes(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  return (
    <>
      <ResponsiveLayout
        title="Certificate Authorities"
        icon={ShieldCheck}
        stats={stats}
        filters={filters}
        activeFilters={activeFiltersCount}
        helpContent={helpContent}
        slideOverOpen={!!selectedCA}
        onSlideOverClose={() => setSelectedCA(null)}
        slideOverTitle="CA Details"
        slideOverWidth="wide"
        slideOverContent={selectedCA && (
          <CADetailsPanel 
            ca={selectedCA}
            canWrite={canWrite}
            canDelete={canDelete}
            onExport={(format) => handleExport(selectedCA, format)}
            onDelete={() => handleDelete(selectedCA.id)}
          />
        )}
        actions={
          canWrite('cas') && (
            isMobile ? (
              <div className="flex gap-2">
                <Button size="lg" onClick={() => openModal('create')} className="w-11 h-11 p-0">
                  <Plus size={22} weight="bold" />
                </Button>
              </div>
            ) : (
              <div className="flex gap-2">
                <Button size="sm" onClick={() => openModal('create')}>
                  <Plus size={14} weight="bold" />
                  Create
                </Button>
                <Button size="sm" variant="secondary" onClick={() => openModal('import')}>
                  <UploadSimple size={14} />
                  Import
                </Button>
              </div>
            )
          )
        }
      >
        {/* Tree View Content */}
        <div className="flex flex-col h-full">
          {/* Search Bar */}
          <div className="shrink-0 p-3 border-b border-border/50 bg-bg-secondary/30">
            <div className="relative">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search CAs..."
                className={cn(
                  'w-full rounded-lg border border-border bg-bg-primary',
                  'text-text-primary placeholder:text-text-tertiary',
                  'focus:outline-none focus:ring-2 focus:ring-accent-primary/30 focus:border-accent-primary',
                  isMobile ? 'h-11 px-4 text-base' : 'h-8 px-3 text-sm'
                )}
              />
            </div>
          </div>

          {/* Tree List */}
          <div className="flex-1 overflow-auto">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <LoadingSpinner />
              </div>
            ) : filteredTree.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 px-4">
                <div className="w-16 h-16 rounded-2xl bg-bg-tertiary flex items-center justify-center mb-4">
                  <ShieldCheck size={32} className="text-text-secondary" />
                </div>
                <h3 className="text-lg font-medium text-text-primary mb-1">No Certificate Authorities</h3>
                <p className="text-sm text-text-secondary text-center mb-4">Create your first CA to get started</p>
                {canWrite('cas') && (
                  <Button onClick={() => openModal('create')}>
                    <Plus size={16} /> Create CA
                  </Button>
                )}
              </div>
            ) : (
              <div className="py-1">
                {filteredTree.map((ca, idx) => (
                  <TreeNode
                    key={ca.id}
                    ca={ca}
                    level={0}
                    selectedId={selectedCA?.id}
                    expandedNodes={expandedNodes}
                    onToggle={toggleNode}
                    onSelect={loadCADetails}
                    isOrphan={isOrphanIntermediate(ca)}
                    isMobile={isMobile}
                    isLast={idx === filteredTree.length - 1}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </ResponsiveLayout>

      {/* Create CA Modal */}
      <Modal
        open={modals.create}
        onOpenChange={() => closeModal('create')}
        title="Create Certificate Authority"
        size="lg"
      >
        <form onSubmit={handleCreateCA} className="space-y-6 p-4">
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
                  label: ca.name || ca.descr || ca.common_name
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
        onOpenChange={() => closeModal('import')}
        title="Import CA"
        size="md"
      >
        <div className="space-y-4 p-4">
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

// =============================================================================
// TREE NODE COMPONENT
// =============================================================================

function TreeNode({ ca, level, selectedId, expandedNodes, onToggle, onSelect, isOrphan, isMobile, isLast = false }) {
  const hasChildren = ca.children && ca.children.length > 0
  const isExpanded = expandedNodes.has(ca.id)
  const isSelected = selectedId === ca.id
  const indent = isMobile ? 24 : 20
  
  return (
    <div>
      <div
        onClick={() => onSelect(ca)}
        className={cn(
          'relative flex items-center cursor-pointer transition-colors',
          'hover:bg-bg-tertiary/60',
          isSelected && 'bg-accent-primary/10',
          isMobile ? 'h-12 px-3 gap-2' : 'h-7 px-2 gap-1.5'
        )}
        style={{ paddingLeft: `${12 + (level * indent)}px` }}
      >
        {/* Simple L connector - part du centre de l'icône parent */}
        {level > 0 && (
          <div 
            className="absolute border-border/50"
            style={{ 
              left: `${12 + ((level - 1) * indent) + (isMobile ? 20 : 14)}px`,
              top: 0,
              width: `${indent - 4}px`,
              height: isMobile ? '24px' : '14px',
              borderLeft: '1px solid',
              borderBottom: '1px solid',
              borderColor: 'inherit',
              borderBottomLeftRadius: '3px'
            }}
          />
        )}
        
        {/* Expand/Collapse */}
        {hasChildren ? (
          <button
            onClick={(e) => { e.stopPropagation(); onToggle(ca.id) }}
            className={cn(
              'shrink-0 flex items-center justify-center text-text-tertiary hover:text-text-primary',
              isMobile ? 'w-6 h-6' : 'w-4 h-4'
            )}
          >
            {isExpanded ? <CaretDown size={isMobile ? 14 : 10} weight="bold" /> : <CaretRight size={isMobile ? 14 : 10} weight="bold" />}
          </button>
        ) : (
          <div className={cn(isMobile ? 'w-6' : 'w-4')} />
        )}
        
        {/* Icon */}
        {ca.type === 'root' ? (
          <Crown size={isMobile ? 16 : 14} weight="duotone" className="text-amber-500 shrink-0" />
        ) : (
          <ShieldCheck size={isMobile ? 16 : 14} weight="duotone" className="text-blue-500 shrink-0" />
        )}
        
        {/* Name */}
        <span className={cn(
          'flex-1 truncate',
          isMobile ? 'text-sm' : 'text-xs',
          isSelected ? 'text-accent-primary font-medium' : 'text-text-primary'
        )}>
          {ca.name || ca.common_name || 'CA'}
        </span>
        
        {/* Cert count */}
        {ca.certs > 0 && (
          <span className={cn(
            'text-text-tertiary',
            isMobile ? 'text-xs' : 'text-[10px]'
          )}>
            {ca.certs}
          </span>
        )}
        
        {/* Status dot */}
        <span className={cn(
          'shrink-0 rounded-full',
          isMobile ? 'w-2 h-2' : 'w-1.5 h-1.5',
          ca.status === 'Active' ? 'bg-emerald-500' : ca.status === 'Expired' ? 'bg-red-500' : 'bg-amber-500'
        )} />
        
        {isSelected && (
          <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-accent-primary" />
        )}
      </div>
      
      {/* Children */}
      {hasChildren && isExpanded && ca.children.map((child, idx) => (
        <TreeNode
          key={child.id}
          ca={child}
          level={level + 1}
          selectedId={selectedId}
          expandedNodes={expandedNodes}
          onToggle={onToggle}
          onSelect={onSelect}
          isOrphan={false}
          isMobile={isMobile}
          isLast={idx === ca.children.length - 1}
        />
      ))}
    </div>
  )
}

// =============================================================================
// CA DETAILS PANEL
// =============================================================================

function CADetailsPanel({ ca, canWrite, canDelete, onExport, onDelete }) {
  return (
    <div className="p-3 space-y-3">
      {/* Header */}
      <CompactHeader
        icon={ca.type === 'root' ? Crown : ShieldCheck}
        iconClass={ca.type === 'root' ? "status-warning-bg" : "status-primary-bg"}
        title={ca.name || ca.common_name || 'CA'}
        subtitle={ca.subject}
        badge={
          <Badge variant={ca.type === 'root' ? 'warning' : 'primary'} size="sm">
            {ca.type || 'unknown'}
          </Badge>
        }
      />

      {/* Stats */}
      <CompactStats stats={[
        { icon: Certificate, value: `${ca.certs || 0} certificates` },
        { icon: Clock, value: ca.valid_to ? formatDate(ca.valid_to, 'short') : '—' },
        { badge: ca.status, badgeVariant: ca.status === 'Active' ? 'success' : 'danger' }
      ]} />

      {/* Actions */}
      <div className="flex gap-2">
        <Button size="sm" variant="secondary" className="flex-1" onClick={() => onExport('pem')}>
          <Download size={14} /> Export
        </Button>
        {canDelete('cas') && (
          <Button size="sm" variant="danger" onClick={onDelete}>
            <Trash size={14} />
          </Button>
        )}
      </div>

      {/* Subject Info */}
      <CompactSection title="Subject">
        <CompactGrid>
          <CompactField label="Common Name" value={ca.common_name} className="col-span-2" />
          <CompactField label="Organization" value={ca.organization} />
          <CompactField label="Country" value={ca.country} />
          <CompactField label="State" value={ca.state} />
          <CompactField label="Locality" value={ca.locality} />
        </CompactGrid>
      </CompactSection>

      {/* Key Info */}
      <CompactSection title="Key Information">
        <CompactGrid>
          <CompactField label="Algorithm" value={ca.key_algorithm || 'RSA'} />
          <CompactField label="Key Size" value={ca.key_size} />
          <CompactField label="Signature" value={ca.signature_algorithm} />
        </CompactGrid>
      </CompactSection>

      {/* Validity */}
      <CompactSection title="Validity">
        <CompactGrid>
          <CompactField label="Not Before" value={ca.valid_from ? formatDate(ca.valid_from) : '—'} />
          <CompactField label="Not After" value={ca.valid_to ? formatDate(ca.valid_to) : '—'} />
          <CompactField label="Serial" value={ca.serial_number} className="col-span-2 font-mono text-xs" />
        </CompactGrid>
      </CompactSection>

      {/* Fingerprints */}
      {(ca.thumbprint_sha1 || ca.thumbprint_sha256) && (
        <CompactSection title="Fingerprints">
          <CompactGrid>
            {ca.thumbprint_sha1 && (
              <CompactField label="SHA-1" value={ca.thumbprint_sha1} className="col-span-2 font-mono text-xs break-all" />
            )}
            {ca.thumbprint_sha256 && (
              <CompactField label="SHA-256" value={ca.thumbprint_sha256} className="col-span-2 font-mono text-xs break-all" />
            )}
          </CompactGrid>
        </CompactSection>
      )}
    </div>
  )
}
