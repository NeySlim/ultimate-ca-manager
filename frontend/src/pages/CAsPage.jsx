/**
 * CAs (Certificate Authorities) Page - Using ResponsiveLayout
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { 
  Key, Download, Trash,
  Certificate, UploadSimple, Clock, Plus, CaretRight, CaretDown,
  TreeStructure, List, Check, Crown, ShieldCheck
} from '@phosphor-icons/react'
import {
  Badge, Button, Modal, Input, Select, LoadingSpinner,
  CompactSection, CompactGrid, CompactField, CompactStats,
  FilterSelect, CATypeIcon
} from '../components'
import { SmartImportModal } from '../components/SmartImport'
import { ResponsiveLayout } from '../components/ui/responsive'
import { casService } from '../services'
import { useNotification } from '../contexts'
import { ERRORS, SUCCESS, LABELS, CONFIRM } from '../lib/messages'
import { usePermission, useModals, useRecentHistory } from '../hooks'
import { useMobile } from '../contexts/MobileContext'
import { extractData, formatDate, cn } from '../lib/utils'

export default function CAsPage() {
  const { t } = useTranslation()
  const { isMobile } = useMobile()
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canWrite, canDelete } = usePermission()
  const [searchParams, setSearchParams] = useSearchParams()
  const { addToHistory } = useRecentHistory('cas')
  
  const [cas, setCAs] = useState([])
  const [selectedCA, setSelectedCA] = useState(null)
  const [loading, setLoading] = useState(true)
  const { modals, open: openModal, close: closeModal } = useModals(['create'])
  const [showImportModal, setShowImportModal] = useState(false)
  const [createFormType, setCreateFormType] = useState('root')
  
  // P12/PFX export modal
  const [showP12Modal, setShowP12Modal] = useState(false)
  const [p12Password, setP12Password] = useState('')
  const [p12CA, setP12CA] = useState(null)
  const [p12Format, setP12Format] = useState('pkcs12')
  
  // Filter state
  const [filterType, setFilterType] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  
  // Pagination state
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  
  // Tree expanded state
  const [expandedNodes, setExpandedNodes] = useState(new Set())
  
  // View mode: 'tree' or 'list'
  const [viewMode, setViewMode] = useState(() => {
    return localStorage.getItem('ucm-ca-view-mode') || 'tree'
  })
  
  // Save view mode preference
  useEffect(() => {
    localStorage.setItem('ucm-ca-view-mode', viewMode)
  }, [viewMode])

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
      showError(error.message || ERRORS.LOAD_FAILED.CAS)
    } finally {
      setLoading(false)
    }
  }

  const loadCADetails = async (ca) => {
    try {
      const caData = await casService.getById(ca.id)
      const fullCA = extractData(caData) || ca
      setSelectedCA(fullCA)
      // Add to recent history
      addToHistory({
        id: fullCA.id,
        name: fullCA.common_name || fullCA.descr || `CA ${fullCA.id}`,
        subtitle: fullCA.is_root ? 'Root CA' : (fullCA.parent_name || 'Intermediate')
      })
    } catch {
      setSelectedCA(ca)
    }
  }

  const handleDelete = async (id) => {
    const confirmed = await showConfirm(CONFIRM.DELETE.CA, {
      title: 'Delete Certificate Authority',
      confirmText: 'Delete CA',
      variant: 'danger'
    })
    if (!confirmed) return
    
    try {
      await casService.delete(id)
      showSuccess(SUCCESS.DELETE.CA)
      loadCAs()
      setSelectedCA(null)
    } catch (error) {
      showError(error.message || 'Failed to delete CA')
    }
  }

  const handleExport = async (ca, format = 'pem') => {
    // PKCS12/PFX need password - show password modal
    if (format === 'pkcs12' || format === 'pfx') {
      setP12CA(ca)
      setP12Format(format)
      setShowP12Modal(true)
      return
    }
    
    try {
      const blob = await casService.export(ca.id, format, {})
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const ext = { pem: 'pem', der: 'der', pkcs7: 'p7b', pkcs12: 'p12', pfx: 'pfx' }[format] || format
      a.download = `${ca.name || ca.common_name || 'ca'}.${ext}`
      a.click()
      URL.revokeObjectURL(url)
      showSuccess(SUCCESS.EXPORT.CA)
    } catch (error) {
      showError(error.message || 'Failed to export CA')
    }
  }
  
  // Export P12/PFX with password
  const handleExportP12 = async () => {
    if (!p12Password || p12Password.length < 4) {
      showError('Password must be at least 4 characters')
      return
    }
    try {
      const blob = await casService.export(p12CA.id, p12Format, { password: p12Password })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const ext = p12Format === 'pfx' ? 'pfx' : 'p12'
      a.download = `${p12CA.name || p12CA.common_name || 'ca'}.${ext}`
      a.click()
      URL.revokeObjectURL(url)
      showSuccess(`CA exported as ${p12Format.toUpperCase()}`)
      setShowP12Modal(false)
      setP12Password('')
      setP12CA(null)
      setP12Format('pkcs12')
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
      showSuccess(SUCCESS.CREATE.CA)
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
      { icon: Crown, label: t('cas.rootCA'), value: rootCount, variant: 'warning' },
      { icon: ShieldCheck, label: t('cas.intermediateCA'), value: intermediateCount, variant: 'primary' },
      { icon: Certificate, label: t('common.active'), value: activeCount, variant: 'success' },
      { icon: Clock, label: t('common.expired'), value: expiredCount, variant: 'danger' }
    ]
  }, [cas, t])

  // Filters config
  const filters = useMemo(() => [
    {
      key: 'type',
      label: t('common.type'),
      type: 'select',
      value: filterType,
      onChange: setFilterType,
      placeholder: LABELS.FILTERS.ALL_TYPES,
      options: [
        { value: 'root', label: t('cas.rootCA') },
        { value: 'intermediate', label: t('cas.intermediateCA') }
      ]
    }
  ], [filterType, t])

  const activeFiltersCount = (filterType ? 1 : 0)

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
        title={t('cas.title')}
        subtitle={`${cas.length} CA${cas.length !== 1 ? 's' : ''}`}
        icon={ShieldCheck}
        stats={stats}
        helpPageKey="cas"
        // Split view on xl+ screens - panel always visible
        splitView={true}
        splitEmptyContent={
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
              <ShieldCheck size={24} className="text-text-tertiary" />
            </div>
            <p className="text-sm text-text-secondary">{t('cas.selectToView')}</p>
          </div>
        }
        slideOverOpen={!!selectedCA}
        onSlideOverClose={() => setSelectedCA(null)}
        slideOverTitle={t('cas.caDetails')}
        slideOverWidth="wide"
        slideOverContent={selectedCA && (
          <CADetailsPanel 
            ca={selectedCA}
            canWrite={canWrite}
            canDelete={canDelete}
            onExport={(format) => handleExport(selectedCA, format)}
            onDelete={() => handleDelete(selectedCA.id)}
            t={t}
          />
        )}
      >
        {/* Tree View Content */}
        <div className="flex flex-col h-full">
          {/* Search Bar + Filters + Actions */}
          <div className="shrink-0 p-3 border-b border-border/50 bg-bg-secondary/30">
            <div className="flex items-center gap-2">
              <div className="relative flex-1 min-w-0">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder={t('cas.searchPlaceholder')}
                  className={cn(
                    'w-full rounded-lg border border-border bg-bg-primary',
                    'text-text-primary placeholder:text-text-tertiary',
                    'focus:outline-none focus:ring-2 focus:ring-accent-primary/30 focus:border-accent-primary',
                    isMobile ? 'h-11 px-4 text-base' : 'h-8 px-3 text-sm'
                  )}
                />
              </div>
              {!isMobile && (
                <>
                  {/* View Mode Toggle */}
                  <div className="flex items-center rounded-lg border border-border bg-bg-secondary/50 p-0.5">
                    <button
                      onClick={() => setViewMode('tree')}
                      className={cn(
                        'flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium transition-colors',
                        viewMode === 'tree' 
                          ? 'bg-accent-primary text-white' 
                          : 'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary'
                      )}
                      title="Hierarchical view"
                    >
                      <TreeStructure size={14} weight={viewMode === 'tree' ? 'fill' : 'regular'} />
                    </button>
                    <button
                      onClick={() => setViewMode('list')}
                      className={cn(
                        'flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium transition-colors',
                        viewMode === 'list' 
                          ? 'bg-accent-primary text-white' 
                          : 'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary'
                      )}
                      title="List view"
                    >
                      <List size={14} weight={viewMode === 'list' ? 'fill' : 'regular'} />
                    </button>
                  </div>
                  
                  <div className="w-px h-5 bg-border/50" />
                  
                  <FilterSelect
                    value={filterType}
                    onChange={setFilterType}
                    placeholder={LABELS.FILTERS.ALL_TYPES}
                    options={[
                      { value: 'root', label: t('cas.rootCA') },
                      { value: 'intermediate', label: t('cas.intermediateCA') },
                    ]}
                    size="sm"
                  />
                  <FilterSelect
                    value={filterStatus}
                    onChange={setFilterStatus}
                    placeholder={LABELS.FILTERS.ALL_STATUS}
                    options={[
                      { value: 'valid', label: t('common.valid') },
                      { value: 'expiring', label: t('common.expiring') },
                      { value: 'expired', label: t('common.expired') },
                    ]}
                    size="sm"
                  />
                </>
              )}
              {canWrite('cas') && (
                isMobile ? (
                  <Button size="lg" onClick={() => openModal('create')} className="w-11 h-11 p-0 shrink-0">
                    <Plus size={22} weight="bold" />
                  </Button>
                ) : (
                  <>
                    <Button size="sm" onClick={() => openModal('create')} className="shrink-0">
                      <Plus size={14} weight="bold" />
                      {t('common.create')}
                    </Button>
                    <Button size="sm" variant="secondary" onClick={() => setShowImportModal(true)} className="shrink-0">
                      <UploadSimple size={14} />
                      {t('common.import')}
                    </Button>
                  </>
                )
              )}
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
                <h3 className="text-lg font-medium text-text-primary mb-1">{t('cas.noCA')}</h3>
                <p className="text-sm text-text-secondary text-center mb-4">{t('cas.createFirst')}</p>
                {canWrite('cas') && (
                  <Button onClick={() => openModal('create')}>
                    <Plus size={16} /> {t('cas.createCA')}
                  </Button>
                )}
              </div>
            ) : (
              <div className="p-3">
                {/* Table Header - Desktop */}
                {!isMobile && (
                  <div className="flex items-center gap-3 px-3 py-2 mb-2 text-2xs font-semibold text-text-tertiary uppercase tracking-wider border-b border-border/50">
                    <div className="flex-1 min-w-0">{t('cas.ca')}</div>
                    {viewMode === 'list' && <div className="w-24 text-center">{t('cas.parentCA')}</div>}
                    <div className="w-20 text-center">{t('common.type')}</div>
                    <div className="w-16 text-center">{t('cas.issuedCertificates')}</div>
                    <div className="w-20 text-center">{t('common.expires')}</div>
                    <div className="w-16 text-center">{t('common.status')}</div>
                  </div>
                )}
                
                {/* Single card with all CAs */}
                <div className="rounded-xl border border-border/60 bg-bg-secondary/30 overflow-hidden divide-y divide-border/40">
                  {viewMode === 'tree' ? (
                    // Hierarchical tree view
                    filteredTree.map((ca, idx) => (
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
                        isFirst={idx === 0}
                        t={t}
                      />
                    ))
                  ) : (
                    // Flat list view
                    cas
                      .filter(ca => {
                        // Apply search filter
                        if (searchQuery) {
                          const query = searchQuery.toLowerCase()
                          if (!(ca.name || '').toLowerCase().includes(query) &&
                              !(ca.common_name || '').toLowerCase().includes(query) &&
                              !(ca.subject || '').toLowerCase().includes(query)) {
                            return false
                          }
                        }
                        // Apply type filter
                        if (filterType && ca.type !== filterType) return false
                        return true
                      })
                      .map((ca, idx, arr) => (
                        <ListRow
                          key={ca.id}
                          ca={ca}
                          allCAs={cas}
                          selectedId={selectedCA?.id}
                          onSelect={loadCADetails}
                          isMobile={isMobile}
                          t={t}
                        />
                      ))
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </ResponsiveLayout>

      {/* Create CA Modal */}
      <Modal
        open={modals.create}
        onOpenChange={() => closeModal('create')}
        title={t('cas.createCA')}
        size="lg"
      >
        <form onSubmit={handleCreateCA} className="space-y-6 p-4">
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-text-primary">{t('cas.subjectInfo')}</h3>
            <Input name="commonName" label={t('certificates.commonName') + ' (CN)'} placeholder="My Certificate Authority" required />
            <div className="grid grid-cols-2 gap-4">
              <Input name="organization" label={t('cas.organization') + ' (O)'} placeholder="My Company" />
              <Input name="country" label={t('cas.country') + ' (C)'} placeholder="US" maxLength={2} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Input name="state" label={t('cas.stateProvince') + ' (ST)'} placeholder="California" />
              <Input name="locality" label={t('cas.locality') + ' (L)'} placeholder="San Francisco" />
            </div>
          </div>

          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-text-primary">{t('cas.keyConfiguration')}</h3>
            <div className="grid grid-cols-2 gap-4">
              <Select
                name="keyAlgo"
                label={t('certificates.keyAlgorithm')}
                options={[
                  { value: 'RSA', label: 'RSA' },
                  { value: 'ECDSA', label: 'ECDSA' }
                ]}
                defaultValue="RSA"
              />
              <Select
                name="keySize"
                label={t('certificates.keySize')}
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
            <h3 className="text-sm font-semibold text-text-primary">{t('certificates.validityPeriod')}</h3>
            <Select
              name="validityYears"
              label={t('certificates.validityPeriod')}
              options={[
                { value: '5', label: t('cas.yearsValidity', { count: 5 }) },
                { value: '10', label: t('cas.yearsValidity', { count: 10 }) },
                { value: '15', label: t('cas.yearsValidity', { count: 15 }) },
                { value: '20', label: t('cas.yearsValidity', { count: 20 }) }
              ]}
              defaultValue="10"
            />
          </div>

          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-text-primary">{t('cas.caType')}</h3>
            <Select
              name="type"
              label={t('common.type')}
              options={[
                { value: 'root', label: t('cas.rootCASelfSigned') },
                { value: 'intermediate', label: t('cas.intermediateCASigned') }
              ]}
              value={createFormType}
              onChange={(value) => setCreateFormType(value)}
            />
            {createFormType === 'intermediate' && (
              <Select
                name="parentCAId"
                label={t('cas.parentCA')}
                options={cas.map(ca => ({
                  value: ca.id.toString(),
                  label: ca.name || ca.descr || ca.common_name
                }))}
                required
              />
            )}
          </div>

          <div className="flex justify-end gap-2 pt-4 border-t border-border">
            <Button type="button" variant="secondary" onClick={() => closeModal('create')}>
              {t('common.cancel')}
            </Button>
            <Button type="submit">{t('cas.createCA')}</Button>
          </div>
        </form>
      </Modal>

      {/* Smart Import Modal */}
      <SmartImportModal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        onImportComplete={() => {
          setShowImportModal(false)
          loadData()
        }}
      />
      
      {/* P12/PFX Export Password Modal */}
      <Modal
        open={showP12Modal}
        onOpenChange={() => { setShowP12Modal(false); setP12Password(''); setP12CA(null) }}
        title={t('cas.exportAs', { format: p12Format.toUpperCase() })}
      >
        <div className="p-4 space-y-4">
          <p className="text-sm text-text-secondary">
            {t('cas.p12PasswordDescription')}
          </p>
          <Input
            label={t('cas.exportPassword')}
            type="password"
            placeholder={t('cas.enterPasswordPlaceholder')}
            value={p12Password}
            onChange={(e) => setP12Password(e.target.value)}
            autoFocus
            showStrength
          />
          <div className="flex justify-end gap-2 pt-4 border-t border-border">
            <Button variant="secondary" onClick={() => { setShowP12Modal(false); setP12Password(''); setP12CA(null) }}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleExportP12} disabled={!p12Password || p12Password.length < 4}>
              <Download size={14} /> {t('common.export')}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}

// =============================================================================
// TREE NODE COMPONENT - Styled with visual hierarchy
// =============================================================================

function TreeNode({ ca, level, selectedId, expandedNodes, onToggle, onSelect, isOrphan, isMobile, isLast = false, isFirst = false, t }) {
  const hasChildren = ca.children && ca.children.length > 0
  const isExpanded = expandedNodes.has(ca.id)
  const isSelected = selectedId === ca.id
  const isRoot = level === 0
  const indent = 24 // indent per level for children
  
  // Format expiration
  const formatExpiry = (date) => {
    if (!date) return null
    const d = new Date(date)
    const now = new Date()
    const diffDays = Math.ceil((d - now) / (1000 * 60 * 60 * 24))
    if (diffDays < 0) return { text: t('common.expired'), variant: 'danger', urgent: true }
    if (diffDays < 30) return { text: t('cas.daysLeft', { count: diffDays }), variant: 'warning', urgent: true }
    if (diffDays < 365) return { text: `${Math.floor(diffDays / 30)}mo`, variant: 'default', urgent: false }
    const formatted = d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
    return { text: formatted, variant: 'default', urgent: false }
  }
  
  const expiry = formatExpiry(ca.valid_to || ca.not_after)
  const rowPadding = isRoot ? 12 : 12 + (level * indent)
  
  return (
    <div className="relative">
      {/* Row */}
      <div
        onClick={() => onSelect(ca)}
        className={cn(
          'relative flex items-center gap-3 cursor-pointer transition-all duration-150',
          'hover:bg-bg-tertiary/50',
          isSelected && 'bg-accent-primary/8 hover:bg-accent-primary/12',
          isMobile ? 'py-3 px-3' : 'py-2 px-3'
        )}
        style={{ paddingLeft: rowPadding }}
      >
        {/* L connector: simple vertical + horizontal lines */}
        {!isRoot && (
          <>
            <div 
              className="absolute bg-border"
              style={{
                left: rowPadding - indent + 46,
                top: 0,
                width: 2,
                height: '50%'
              }}
            />
            <div 
              className="absolute bg-border"
              style={{
                left: rowPadding - indent + 46,
                top: '50%',
                width: indent - 20,
                height: 2,
                marginTop: -1
              }}
            />
          </>
        )}
        
        {/* Left accent for selected */}
        {isSelected && (
          <div className="absolute left-0 top-2 bottom-2 w-1 rounded-r-full bg-accent-primary" />
        )}
        
        {/* Expand button + Icon */}
        <div className="flex items-center gap-2 shrink-0">
          {/* Expand/Collapse */}
          {hasChildren ? (
            <button
              onClick={(e) => { e.stopPropagation(); onToggle(ca.id) }}
              className={cn(
                'w-6 h-6 rounded-md flex items-center justify-center transition-colors',
                'text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary',
                isExpanded && 'bg-bg-tertiary/50'
              )}
            >
              {isExpanded ? <CaretDown size={12} weight="bold" /> : <CaretRight size={12} weight="bold" />}
            </button>
          ) : (
            <div className="w-6" />
          )}
          
          {/* Icon with background */}
          <CATypeIcon isRoot={ca.type === 'root'} size="lg" />
        </div>
        
        {/* Name & Subject */}
        <div className="flex-1 min-w-0">
          <div className={cn(
            'font-medium truncate',
            isMobile ? 'text-sm' : 'text-xs',
            isSelected ? 'text-accent-primary' : 'text-text-primary'
          )}>
            {ca.name || ca.common_name || 'Unnamed CA'}
          </div>
          {!isMobile && ca.subject && (
            <div className="text-2xs text-text-tertiary truncate mt-0.5">
              {ca.subject.split(',')[0]}
            </div>
          )}
        </div>
        
        {/* Desktop: Metadata columns */}
        {!isMobile && (
          <>
            {/* Type badge */}
            <div className="w-20 flex justify-center">
              <span className={cn(
                'px-2 py-0.5 rounded-md text-2xs font-semibold',
                ca.type === 'root' ? 'badge-bg-amber' : 'badge-bg-blue'
              )}>
                {ca.type === 'root' ? t('cas.rootCA') : t('cas.intermediateCA')}
              </span>
            </div>
            
            {/* Certs count */}
            <div className="w-16 flex justify-center">
              {ca.certs > 0 ? (
                <span className="flex items-center gap-1 text-2xs text-text-secondary">
                  <Certificate size={12} weight="duotone" className="text-text-tertiary" />
                  <span className="font-medium">{ca.certs}</span>
                </span>
              ) : (
                <span className="text-2xs text-text-tertiary">—</span>
              )}
            </div>
            
            {/* Expiry */}
            <div className="w-20 flex justify-center">
              {expiry ? (
                <span className={cn(
                  'text-2xs font-medium',
                  expiry.variant === 'danger' ? 'text-status-danger' : 
                  expiry.variant === 'warning' ? 'text-status-warning' : 'text-text-secondary'
                )}>
                  {expiry.text}
                </span>
              ) : (
                <span className="text-2xs text-text-tertiary">—</span>
              )}
            </div>
            
            {/* Status */}
            <div className="w-16 flex justify-center">
              <span className={cn(
                'px-2 py-0.5 rounded-full text-2xs font-medium flex items-center gap-1',
                ca.status === 'Active' 
                  ? 'bg-status-success/10 text-status-success'
                  : ca.status === 'Expired'
                    ? 'bg-status-danger/10 text-status-danger'
                    : 'bg-status-warning/10 text-status-warning'
              )}>
                <span className={cn(
                  'w-1.5 h-1.5 rounded-full',
                  ca.status === 'Active' ? 'bg-status-success' : ca.status === 'Expired' ? 'bg-status-danger' : 'bg-status-warning'
                )} />
                {ca.status || '?'}
              </span>
            </div>
          </>
        )}
        
        {/* Mobile: Compact badges */}
        {isMobile && (
          <div className="flex items-center gap-2">
            {ca.certs > 0 && (
              <span className="text-xs text-text-tertiary">{ca.certs}</span>
            )}
            <span className={cn(
              'w-2.5 h-2.5 rounded-full shrink-0',
              ca.status === 'Active' ? 'bg-status-success' : ca.status === 'Expired' ? 'bg-status-danger' : 'bg-status-warning'
            )} />
          </div>
        )}
      </div>
      
      {/* Children */}
      {hasChildren && isExpanded && (
        <div className={cn(isRoot && 'pb-1')}>
          {ca.children.map((child, idx) => (
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
              t={t}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// =============================================================================
// LIST ROW COMPONENT - Flat list view
// =============================================================================

function ListRow({ ca, allCAs, selectedId, onSelect, isMobile, t }) {
  const isSelected = selectedId === ca.id
  
  // Find parent CA name
  const parentCA = ca.parent_id ? allCAs.find(c => c.id === ca.parent_id) : null
  
  // Format expiration
  const formatExpiry = (date) => {
    if (!date) return null
    const d = new Date(date)
    const now = new Date()
    const diffDays = Math.ceil((d - now) / (1000 * 60 * 60 * 24))
    if (diffDays < 0) return { text: t('common.expired'), variant: 'danger' }
    if (diffDays < 30) return { text: t('cas.daysLeft', { count: diffDays }), variant: 'warning' }
    if (diffDays < 365) return { text: `${Math.floor(diffDays / 30)}mo`, variant: 'default' }
    const formatted = d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
    return { text: formatted, variant: 'default' }
  }
  
  const expiry = formatExpiry(ca.valid_to || ca.not_after)
  
  return (
    <div
      onClick={() => onSelect(ca)}
      className={cn(
        'relative flex items-center gap-3 cursor-pointer transition-all duration-150',
        'hover:bg-bg-tertiary/50',
        isSelected && 'bg-accent-primary/8 hover:bg-accent-primary/12',
        isMobile ? 'py-3 px-3' : 'py-2 px-3'
      )}
    >
      {/* Left accent for selected */}
      {isSelected && (
        <div className="absolute left-0 top-2 bottom-2 w-1 rounded-r-full bg-accent-primary" />
      )}
      
      {/* Icon with background */}
      <CATypeIcon isRoot={ca.type === 'root'} size="lg" />
      
      {/* Name & Subject */}
      <div className="flex-1 min-w-0">
        <div className={cn(
          'font-medium truncate',
          isMobile ? 'text-sm' : 'text-xs',
          isSelected ? 'text-accent-primary' : 'text-text-primary'
        )}>
          {ca.name || ca.common_name || 'Unnamed CA'}
        </div>
        {!isMobile && ca.subject && (
          <div className="text-2xs text-text-tertiary truncate mt-0.5">
            {ca.subject.split(',')[0]}
          </div>
        )}
      </div>
      
      {/* Desktop columns */}
      {!isMobile && (
        <>
          {/* Parent */}
          <div className="w-24 flex justify-center">
            {parentCA ? (
              <span className="text-2xs text-text-secondary truncate max-w-[90px]" title={parentCA.name || parentCA.common_name}>
                {parentCA.name || parentCA.common_name || '—'}
              </span>
            ) : (
              <span className="text-2xs text-text-tertiary">—</span>
            )}
          </div>
          
          {/* Type badge */}
          <div className="w-20 flex justify-center">
            <span className={cn(
              'px-2 py-0.5 rounded-md text-2xs font-semibold',
              ca.type === 'root' ? 'badge-bg-amber' : 'badge-bg-blue'
            )}>
              {ca.type === 'root' ? t('cas.rootCA') : t('cas.intermediateCA')}
            </span>
          </div>
          
          {/* Certs count */}
          <div className="w-16 flex justify-center">
            {ca.certs > 0 ? (
              <span className="flex items-center gap-1 text-2xs text-text-secondary">
                <Certificate size={12} weight="duotone" className="text-text-tertiary" />
                <span className="font-medium">{ca.certs}</span>
              </span>
            ) : (
              <span className="text-2xs text-text-tertiary">—</span>
            )}
          </div>
          
          {/* Expiry */}
          <div className="w-20 flex justify-center">
            {expiry ? (
              <span className={cn(
                'text-2xs font-medium',
                expiry.variant === 'danger' ? 'text-status-danger' : 
                expiry.variant === 'warning' ? 'text-status-warning' : 'text-text-secondary'
              )}>
                {expiry.text}
              </span>
            ) : (
              <span className="text-2xs text-text-tertiary">—</span>
            )}
          </div>
          
          {/* Status */}
          <div className="w-16 flex justify-center">
            <span className={cn(
              'px-2 py-0.5 rounded-full text-2xs font-medium flex items-center gap-1',
              ca.status === 'Active' 
                ? 'bg-status-success/10 text-status-success'
                : ca.status === 'Expired'
                  ? 'bg-status-danger/10 text-status-danger'
                  : 'bg-status-warning/10 text-status-warning'
            )}>
              <span className={cn(
                'w-1.5 h-1.5 rounded-full',
                ca.status === 'Active' ? 'bg-status-success' : ca.status === 'Expired' ? 'bg-status-danger' : 'bg-status-warning'
              )} />
              {ca.status || '?'}
            </span>
          </div>
        </>
      )}
      
      {/* Mobile: Compact badges */}
      {isMobile && (
        <div className="flex items-center gap-2">
          {ca.certs > 0 && (
            <span className="text-xs text-text-tertiary">{ca.certs}</span>
          )}
          <span className={cn(
            'w-2.5 h-2.5 rounded-full shrink-0',
            ca.status === 'Active' ? 'bg-status-success' : ca.status === 'Expired' ? 'bg-status-danger' : 'bg-status-warning'
          )} />
        </div>
      )}
    </div>
  )
}

// =============================================================================
// CA DETAILS PANEL
// =============================================================================

function CADetailsPanel({ ca, canWrite, canDelete, onExport, onDelete, t }) {
  return (
    <div className="p-3 space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2">
        <CATypeIcon isRoot={ca.type === 'root' || ca.is_root} size="lg" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-text-primary truncate">
              {ca.name || ca.common_name || t('cas.ca')}
            </h3>
            <Badge variant={ca.type === 'root' || ca.is_root ? 'warning' : 'primary'} size="sm">
              {ca.type === 'root' || ca.is_root ? t('cas.rootCA') : t('cas.intermediateCA')}
            </Badge>
          </div>
          {ca.subject && (
            <p className="text-xs text-text-secondary truncate">{ca.subject}</p>
          )}
        </div>
      </div>

      {/* Stats */}
      <CompactStats stats={[
        { icon: Certificate, value: t('cas.certificateCount', { count: ca.certs || 0 }) },
        { icon: Clock, value: ca.valid_to ? formatDate(ca.valid_to, 'short') : '—' },
        { badge: ca.status, badgeVariant: ca.status === 'Active' ? 'success' : 'danger' }
      ]} />

      {/* Export Actions */}
      <div className="flex flex-wrap gap-1.5 sm:gap-2">
        <Button size="xs" variant="secondary" onClick={() => onExport('pem')} className="sm:!h-8 sm:!px-3 sm:!text-xs">
          <Download size={12} className="sm:w-3.5 sm:h-3.5" /> PEM
        </Button>
        <Button size="xs" variant="secondary" onClick={() => onExport('der')} className="sm:!h-8 sm:!px-3 sm:!text-xs">
          <Download size={12} className="sm:w-3.5 sm:h-3.5" /> DER
        </Button>
        <Button size="xs" variant="secondary" onClick={() => onExport('pkcs7')} className="sm:!h-8 sm:!px-3 sm:!text-xs">
          <Download size={12} className="sm:w-3.5 sm:h-3.5" /> P7B
        </Button>
        <Button size="xs" variant="secondary" onClick={() => onExport('pkcs12')} className="sm:!h-8 sm:!px-3 sm:!text-xs">
          <Download size={12} className="sm:w-3.5 sm:h-3.5" /> P12
        </Button>
        <Button size="xs" variant="secondary" onClick={() => onExport('pfx')} className="sm:!h-8 sm:!px-3 sm:!text-xs">
          <Download size={12} className="sm:w-3.5 sm:h-3.5" /> PFX
        </Button>
        {canDelete('cas') && (
          <Button size="xs" variant="danger" onClick={onDelete} className="sm:!h-8 sm:!px-3">
            <Trash size={12} className="sm:w-3.5 sm:h-3.5" />
          </Button>
        )}
      </div>

      {/* Subject Info */}
      <CompactSection title={t('cas.subject')}>
        <CompactGrid>
          <CompactField label={t('certificates.commonName')} value={ca.common_name} copyable className="col-span-2" />
          <CompactField label={t('cas.organization')} value={ca.organization} />
          <CompactField label={t('cas.country')} value={ca.country} />
          <CompactField label={t('cas.stateProvince')} value={ca.state} />
          <CompactField label={t('cas.locality')} value={ca.locality} />
        </CompactGrid>
      </CompactSection>

      {/* Key Info */}
      <CompactSection title={t('cas.keyInformation')}>
        <CompactGrid>
          <CompactField label={t('cas.algorithm')} value={ca.key_algorithm || 'RSA'} />
          <CompactField label={t('certificates.keySize')} value={ca.key_size} />
          <CompactField label={t('cas.signature')} value={ca.signature_algorithm} />
        </CompactGrid>
      </CompactSection>

      {/* Validity */}
      <CompactSection title={t('cas.validity')}>
        <CompactGrid>
          <CompactField label={t('certificates.validFrom')} value={ca.valid_from ? formatDate(ca.valid_from) : '—'} />
          <CompactField label={t('certificates.validTo')} value={ca.valid_to ? formatDate(ca.valid_to) : '—'} />
          <CompactField label={t('certificates.serialNumber')} value={ca.serial_number} copyable mono className="col-span-2" />
        </CompactGrid>
      </CompactSection>

      {/* Fingerprints */}
      {(ca.thumbprint_sha1 || ca.thumbprint_sha256) && (
        <CompactSection title={t('certificates.fingerprints')}>
          <CompactGrid>
            {ca.thumbprint_sha1 && (
              <CompactField label="SHA-1" value={ca.thumbprint_sha1} copyable mono className="col-span-2" />
            )}
            {ca.thumbprint_sha256 && (
              <CompactField label="SHA-256" value={ca.thumbprint_sha256} copyable mono className="col-span-2" />
            )}
          </CompactGrid>
        </CompactSection>
      )}
    </div>
  )
}
