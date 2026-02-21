/**
 * CAs (Certificate Authorities) Page - Using ResponsiveLayout
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams, useParams, useNavigate } from 'react-router-dom'
import { 
  Key, Download, Trash,
  Certificate, UploadSimple, Clock, Plus, CaretRight, CaretDown,
  TreeStructure, List, Check, Crown, ShieldCheck, Columns, SquaresFour,
  LinkSimple, ArrowClockwise, CircleNotch, Timer
} from '@phosphor-icons/react'
import {
  Badge, Button, Modal, Input, Select, LoadingSpinner,
  CompactSection, CompactGrid, CompactField, CompactStats,
  FilterSelect, CATypeIcon
} from '../components'
import { ExportModal } from '../components/ExportModal'
import { SmartImportModal } from '../components/SmartImport'
import { ResponsiveLayout } from '../components/ui/responsive'
import { casService } from '../services'
import { apiClient } from '../services'
import { useNotification } from '../contexts'
import { useWindowManager } from '../contexts/WindowManagerContext'
import { usePermission, useModals, useRecentHistory } from '../hooks'
import { useMobile } from '../contexts/MobileContext'
import { extractData, formatDate, cn } from '../lib/utils'

export default function CAsPage() {
  const { t } = useTranslation()
  const { id: urlCAId } = useParams()
  const navigate = useNavigate()
  const { isMobile } = useMobile()
  const { openWindow } = useWindowManager()
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
  const [createFormParentCAId, setCreateFormParentCAId] = useState(null)
  const [createFormKeyAlgo, setCreateFormKeyAlgo] = useState('RSA')
  const [createFormKeySize, setCreateFormKeySize] = useState('2048')
  const [createFormValidity, setCreateFormValidity] = useState('10')
  
  // Filter state
  const [filterType, setFilterType] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

  // Chain repair state
  const [chainRepair, setChainRepair] = useState(null)
  const [chainRepairRunning, setChainRepairRunning] = useState(false)
  
  // Pagination state
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  
  // Tree expanded state
  const [expandedNodes, setExpandedNodes] = useState(new Set())
  
  // View mode: 'tree' or 'list'
  const [viewMode, setViewMode] = useState(() => {
    return localStorage.getItem('ucm-ca-view-mode') || 'org'
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

  // Reload when floating window actions change data
  useEffect(() => {
    const handler = (e) => {
      if (e.detail?.type === 'ca') loadCAs()
    }
    window.addEventListener('ucm:data-changed', handler)
    return () => window.removeEventListener('ucm:data-changed', handler)
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

  // Deep-link: auto-select CA from URL param /cas/:id
  useEffect(() => {
    if (urlCAId && !loading && cas.length > 0) {
      const id = parseInt(urlCAId, 10)
      if (!isNaN(id)) {
        if (!isMobile) {
          openWindow('ca', id)
        } else {
          loadCADetails({ id })
        }
        navigate('/cas', { replace: true })
      }
    }
  }, [urlCAId, loading, cas.length])

  // Expand all nodes that have children by default
  useEffect(() => {
    if (cas.length > 0 && expandedNodes.size === 0) {
      const parentIds = cas.filter(c => cas.some(child => child.parent_id === c.id)).map(c => c.id)
      const rootIds = cas.filter(c => !c.parent_id || c.type === 'root').map(c => c.id)
      setExpandedNodes(new Set([...rootIds, ...parentIds]))
    }
  }, [cas])

  const loadCAs = async () => {
    setLoading(true)
    try {
      const casData = await casService.getAll()
      const casList = casData.data || []
      setCAs(casList)
    } catch (error) {
      showError(error.message || t('messages.errors.loadFailed.cas'))
    } finally {
      setLoading(false)
    }

    // Load chain repair status (non-blocking, admin/operator only)
    if (canWrite('cas')) {
      apiClient.get('/system/chain-repair')
        .then(res => setChainRepair(res.data || null))
        .catch(() => {})
    }
  }

  const loadCADetails = async (ca) => {
    // Desktop: open floating window
    if (!isMobile) {
      openWindow('ca', ca.id)
      addToHistory({
        id: ca.id,
        name: ca.common_name || ca.descr || `CA ${ca.id}`,
        subtitle: ca.is_root ? t('common.rootCA') : (ca.parent_name || t('common.intermediate'))
      })
      return
    }

    // Mobile: slide-over
    try {
      const caData = await casService.getById(ca.id)
      const fullCA = extractData(caData) || ca
      setSelectedCA(fullCA)
      addToHistory({
        id: fullCA.id,
        name: fullCA.common_name || fullCA.descr || `CA ${fullCA.id}`,
        subtitle: fullCA.is_root ? t('common.rootCA') : (fullCA.parent_name || t('common.intermediate'))
      })
    } catch {
      setSelectedCA(ca)
    }
  }

  const runChainRepair = useCallback(async () => {
    setChainRepairRunning(true)
    try {
      const res = await apiClient.post('/system/chain-repair/run')
      setChainRepair(res.data || null)
      loadCAs() // Refresh CAs after repair
    } catch { /* ignore */ }
    finally { setChainRepairRunning(false) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleDelete = async (id) => {
    const confirmed = await showConfirm(t('messages.confirm.delete.ca'), {
      title: t('cas.deleteCA'),
      confirmText: t('cas.deleteCAButton'),
      variant: 'danger'
    })
    if (!confirmed) return
    
    try {
      await casService.delete(id)
      showSuccess(t('messages.success.delete.ca'))
      loadCAs()
      setSelectedCA(null)
    } catch (error) {
      showError(error.message || t('cas.deleteFailed'))
    }
  }

  const handleExport = async (ca, format = 'pem', options = {}) => {
    try {
      const blob = await casService.export(ca.id, format, options)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const ext = { pem: 'pem', der: 'der', pkcs7: 'p7b', pkcs12: 'p12' }[format] || format
      a.download = `${ca.name || ca.common_name || 'ca'}.${ext}`
      a.click()
      URL.revokeObjectURL(url)
      showSuccess(t('messages.success.export.ca'))
    } catch (error) {
      showError(error.message || t('cas.exportFailed'))
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
      keyAlgo: createFormKeyAlgo,
      keySize: createFormKeyAlgo === 'ECDSA' ? createFormKeySize : parseInt(createFormKeySize),
      validityYears: parseInt(createFormValidity),
      type: createFormType,
      parentCAId: createFormType === 'intermediate' ? createFormParentCAId : null
    }
    
    try {
      await casService.create(data)
      showSuccess(t('messages.success.create.ca'))
      closeModal('create')
      loadCAs()
    } catch (error) {
      showError(error.message || t('cas.createFailed'))
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
      { icon: Crown, label: t('common.rootCA'), value: rootCount, variant: 'warning' },
      { icon: ShieldCheck, label: t('common.intermediateCA'), value: intermediateCount, variant: 'primary' },
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
      placeholder: t('common.allTypes'),
      options: [
        { value: 'root', label: t('common.rootCA') },
        { value: 'intermediate', label: t('common.intermediateCA') }
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
        title={t('common.cas')}
        subtitle={t('cas.subtitle', { count: cas.length })}
        icon={ShieldCheck}
        stats={stats}
        afterStats={<ChainRepairBar data={chainRepair} running={chainRepairRunning} onRun={runChainRepair} canRunRepair={canWrite('cas')} t={t} />}
        helpPageKey="cas"
        // Split view on xl+ screens - panel always visible
        splitView={isMobile}
        splitEmptyContent={isMobile ? (
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
              <ShieldCheck size={24} className="text-text-tertiary" />
            </div>
            <p className="text-sm text-text-secondary">{t('cas.selectToView')}</p>
          </div>
        ) : undefined}
        slideOverOpen={isMobile && !!selectedCA}
        onSlideOverClose={() => setSelectedCA(null)}
        slideOverTitle={t('cas.caDetails')}
        slideOverWidth="wide"
        slideOverContent={isMobile && selectedCA ? (
          <CADetailsPanel 
            ca={selectedCA}
            canWrite={canWrite}
            canDelete={canDelete}
            onExport={(format, options) => handleExport(selectedCA, format, options)}
            onDelete={() => handleDelete(selectedCA.id)}
            t={t}
          />
        ) : null}
      >
        {/* Tree View Content */}
        <div className="flex flex-col h-full">
          {/* Search Bar + Filters + Actions */}
          <div className="shrink-0 p-3 border-b border-border-op50 bg-secondary-op30">
            <div className="flex items-center gap-2">
              <div className="relative flex-1 min-w-0">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder={t('common.searchPlaceholder')}
                  className={cn(
                    'w-full rounded-lg border border-border bg-bg-primary',
                    'text-text-primary placeholder:text-text-tertiary',
                    'focus:outline-none focus:ring-2 focus:ring-accent-primary-op30 focus:border-accent-primary',
                    isMobile ? 'h-11 px-4 text-base' : 'h-8 px-3 text-sm'
                  )}
                />
              </div>
              {!isMobile && (
                <>
                  {/* View Mode Toggle — 3 views */}
                  <div className="flex items-center rounded-lg border border-border bg-secondary-op50 p-0.5">
                    {[
                      { mode: 'org', icon: SquaresFour, tip: t('cas.orgView') },
                      { mode: 'columns', icon: Columns, tip: t('cas.columnsView') },
                      { mode: 'list', icon: List, tip: t('cas.listView') },
                    ].map(({ mode, icon: Icon, tip }) => (
                      <button
                        key={mode}
                        onClick={() => setViewMode(mode)}
                        className={cn(
                          'flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium transition-colors',
                          viewMode === mode
                            ? 'bg-accent-primary text-white'
                            : 'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary'
                        )}
                        title={tip}
                      >
                        <Icon size={14} weight={viewMode === mode ? 'fill' : 'regular'} />
                      </button>
                    ))}
                  </div>
                  
                  <div className="w-px h-5 bg-border-op50" />
                  
                  <FilterSelect
                    value={filterType}
                    onChange={setFilterType}
                    placeholder={t('common.allTypes')}
                    options={[
                      { value: 'root', label: t('common.rootCA') },
                      { value: 'intermediate', label: t('common.intermediateCA') },
                    ]}
                    size="sm"
                  />
                  <FilterSelect
                    value={filterStatus}
                    onChange={setFilterStatus}
                    placeholder={t('common.allStatus')}
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
                  <Button type="button" size="lg" onClick={() => openModal('create')} className="w-11 h-11 p-0 shrink-0">
                    <Plus size={22} weight="bold" />
                  </Button>
                ) : (
                  <>
                    <Button type="button" size="sm" onClick={() => openModal('create')} className="shrink-0">
                      <Plus size={14} weight="bold" />
                      {t('common.create')}
                    </Button>
                    <Button type="button" size="sm" variant="secondary" onClick={() => setShowImportModal(true)} className="shrink-0">
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
                <h3 className="text-lg font-medium text-text-primary mb-1">{t('common.noCA')}</h3>
                <p className="text-sm text-text-secondary text-center mb-4">{t('cas.createFirst')}</p>
                {canWrite('cas') && (
                  <Button type="button" onClick={() => openModal('create')}>
                    <Plus size={16} /> {t('common.createCA')}
                  </Button>
                )}
              </div>
            ) : (
              <div className={cn('p-3', viewMode === 'columns' ? '' : 'space-y-3')}>
                {viewMode === 'org' ? (
                  <OrgView
                    tree={filteredTree}
                    selectedId={selectedCA?.id}
                    expandedNodes={expandedNodes}
                    onToggle={toggleNode}
                    onSelect={loadCADetails}
                    isMobile={isMobile}
                    t={t}
                  />
                ) : viewMode === 'columns' ? (
                  <ColumnsView
                    tree={filteredTree}
                    orphans={filteredTree.filter(ca => ca.type !== 'root')}
                    selectedId={selectedCA?.id}
                    onSelect={loadCADetails}
                    isMobile={isMobile}
                    t={t}
                  />
                ) : (
                  <ListView
                    cas={cas.filter(ca => {
                      if (searchQuery) {
                        const q = searchQuery.toLowerCase()
                        if (!(ca.name || '').toLowerCase().includes(q) &&
                            !(ca.common_name || '').toLowerCase().includes(q) &&
                            !(ca.subject || '').toLowerCase().includes(q)) return false
                      }
                      if (filterType && ca.type !== filterType) return false
                      return true
                    })}
                    allCAs={cas}
                    selectedId={selectedCA?.id}
                    onSelect={loadCADetails}
                    isMobile={isMobile}
                    t={t}
                  />
                )}
              </div>
            )}
          </div>
        </div>
      </ResponsiveLayout>

      {/* Create CA Modal */}
      <Modal
        open={modals.create}
        onOpenChange={() => closeModal('create')}
        title={t('common.createCA')}
        size="lg"
      >
        <form onSubmit={handleCreateCA} className="space-y-6 p-4">
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-text-primary">{t('cas.subjectInfo')}</h3>
            <Input name="commonName" label={t('common.commonName') + ' (CN)'} placeholder={t('cas.cnPlaceholder')} required />
            <div className="grid grid-cols-2 gap-4">
              <Input name="organization" label={t('common.organization') + ' (O)'} placeholder={t('cas.orgPlaceholder')} />
              <Input name="country" label={t('common.country') + ' (C)'} placeholder={t('common.countryPlaceholder')} maxLength={2} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Input name="state" label={t('common.stateProvince') + ' (ST)'} placeholder={t('common.statePlaceholder')} />
              <Input name="locality" label={t('cas.locality') + ' (L)'} placeholder={t('cas.localityPlaceholder')} />
            </div>
          </div>

          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-text-primary">{t('cas.keyConfiguration')}</h3>
            <div className="grid grid-cols-2 gap-4">
              <Select
                label={t('common.keyAlgorithm')}
                options={[
                  { value: 'RSA', label: 'RSA' },
                  { value: 'ECDSA', label: 'ECDSA' }
                ]}
                value={createFormKeyAlgo}
                onChange={(value) => {
                  setCreateFormKeyAlgo(value)
                  setCreateFormKeySize(value === 'ECDSA' ? 'prime256v1' : '2048')
                }}
              />
              <Select
                label={t('common.keySize')}
                options={createFormKeyAlgo === 'ECDSA' ? [
                  { value: 'prime256v1', label: 'P-256 (256 bits)' },
                  { value: 'secp384r1', label: 'P-384 (384 bits)' },
                  { value: 'secp521r1', label: 'P-521 (521 bits)' }
                ] : [
                  { value: '2048', label: '2048 bits' },
                  { value: '3072', label: '3072 bits' },
                  { value: '4096', label: '4096 bits' }
                ]}
                value={createFormKeySize}
                onChange={(value) => setCreateFormKeySize(value)}
              />
            </div>
          </div>

          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-text-primary">{t('common.validityPeriod')}</h3>
            <Select
              label={t('common.validityPeriod')}
              options={[
                { value: '5', label: t('cas.yearsValidity', { count: 5 }) },
                { value: '10', label: t('cas.yearsValidity', { count: 10 }) },
                { value: '15', label: t('cas.yearsValidity', { count: 15 }) },
                { value: '20', label: t('cas.yearsValidity', { count: 20 }) }
              ]}
              value={createFormValidity}
              onChange={(value) => setCreateFormValidity(value)}
            />
          </div>

          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-text-primary">{t('cas.caType')}</h3>
            <Select
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
                label={t('cas.parentCA')}
                options={cas.map(ca => ({
                  value: ca.id.toString(),
                  label: ca.name || ca.descr || ca.common_name
                }))}
                value={createFormParentCAId}
                onChange={(value) => setCreateFormParentCAId(value)}
                required
              />
            )}
          </div>

          <div className="flex justify-end gap-2 pt-4 border-t border-border">
            <Button type="button" variant="secondary" onClick={() => closeModal('create')}>
              {t('common.cancel')}
            </Button>
            <Button type="submit">{t('common.createCA')}</Button>
          </div>
        </form>
      </Modal>

      {/* Smart Import Modal */}
      <SmartImportModal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        onImportComplete={() => {
          setShowImportModal(false)
          loadCAs()
        }}
      />
      
    </>
  )
}

// =============================================================================
// SHARED HELPERS
// =============================================================================

function formatExpiry(date, t) {
  if (!date) return null
  const d = new Date(date)
  const now = new Date()
  const diffDays = Math.ceil((d - now) / (1000 * 60 * 60 * 24))
  if (diffDays < 0) return { text: t('common.expired'), variant: 'danger' }
  if (diffDays < 30) return { text: t('cas.daysLeft', { count: diffDays }), variant: 'warning' }
  if (diffDays < 365) return { text: `${Math.floor(diffDays / 30)}mo`, variant: 'default' }
  return { text: d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' }), variant: 'default' }
}

function getStatusBadgeClass(status) {
  return status === 'Active' ? 'status-badge-success' : status === 'Expired' ? 'status-badge-danger' : 'status-badge-warning'
}

function getStatusDotClass(status) {
  return status === 'Active' ? 'bg-status-success' : status === 'Expired' ? 'bg-status-danger' : 'bg-status-warning'
}

/** Reusable CA info row — used by all 3 views */
function CAInfoLine({ ca, isMobile, t }) {
  const expiry = formatExpiry(ca.valid_to || ca.not_after, t)
  return (
    <div className="flex items-center gap-2 text-2xs text-text-tertiary flex-wrap">
      {ca.subject && (
        <span className="truncate max-w-[200px]">{ca.subject.split(',')[0]}</span>
      )}
      <span className="flex items-center gap-1">
        <Certificate size={11} weight="duotone" className="text-accent-primary" />
        <span className="font-semibold text-text-secondary">
          {t('cas.certificateCount', { count: ca.certs || 0 })}
        </span>
      </span>
      {expiry && (
        <>
          <span className="text-border">·</span>
          <span className={cn(
            'font-medium flex items-center gap-1',
            expiry.variant === 'danger' ? 'text-status-danger' :
            expiry.variant === 'warning' ? 'text-status-warning' : 'text-text-secondary'
          )}>
            <Clock size={11} weight="duotone" />
            {expiry.text}
          </span>
        </>
      )}
    </div>
  )
}

/** Status pill badge */
function StatusBadge({ status }) {
  return (
    <span className={cn(
      'shrink-0 px-2 py-0.5 rounded-full text-2xs font-medium flex items-center gap-1',
      getStatusBadgeClass(status)
    )}>
      <span className={cn('w-1.5 h-1.5 rounded-full', getStatusDotClass(status))} />
      {status || '?'}
    </span>
  )
}

/** Type badge (Root / Intermediate) */
function TypeBadge({ type, isMobile, t }) {
  return (
    <span className={cn(
      'shrink-0 px-1.5 py-0.5 rounded-md text-2xs font-semibold',
      type === 'root' ? 'badge-bg-amber' : 'badge-bg-blue'
    )}>
      {type === 'root' ? t('common.rootCA') : (isMobile ? 'Int.' : t('common.intermediateCA'))}
    </span>
  )
}

// =============================================================================
// VIEW A: ORGANIGRAMME — Root = big card, children nested inside
// =============================================================================

function OrgView({ tree, selectedId, expandedNodes, onToggle, onSelect, isMobile, t }) {
  // Separate roots from orphans
  const roots = tree.filter(ca => ca.type === 'root')
  const orphans = tree.filter(ca => ca.type !== 'root')

  return (
    <div className="space-y-3">
      {roots.map(root => (
        <OrgRootCard
          key={root.id}
          ca={root}
          selectedId={selectedId}
          expandedNodes={expandedNodes}
          onToggle={onToggle}
          onSelect={onSelect}
          isMobile={isMobile}
          t={t}
        />
      ))}
      {orphans.length > 0 && (
        <div className="space-y-2">
          <div className="text-2xs font-semibold text-text-tertiary uppercase tracking-wider px-1">
            {t('cas.orphanCAs')}
          </div>
          {orphans.map(ca => (
            <OrgChildCard
              key={ca.id}
              ca={ca}
              selectedId={selectedId}
              onSelect={onSelect}
              isMobile={isMobile}
              t={t}
              isOrphan
            />
          ))}
        </div>
      )}
    </div>
  )
}

function OrgRootCard({ ca, selectedId, expandedNodes, onToggle, onSelect, isMobile, t }) {
  const hasChildren = ca.children && ca.children.length > 0
  const isExpanded = expandedNodes.has(ca.id)
  const isSelected = selectedId === ca.id

  return (
    <div className={cn(
      'rounded-xl border overflow-hidden transition-all duration-200',
      isSelected ? 'border-accent-primary ca-org-root-selected' : 'border-border-op60'
    )}>
      {/* Root header — gradient */}
      <div
        onClick={() => onSelect(ca)}
        className={cn(
          'ca-org-root-header cursor-pointer transition-colors',
          isMobile ? 'px-3 py-3' : 'px-4 py-3'
        )}
      >
        <div className="flex items-center gap-2.5">
          {hasChildren && (
            <button
              onClick={(e) => { e.stopPropagation(); onToggle(ca.id) }}
              className="shrink-0 w-6 h-6 rounded-md flex items-center justify-center text-text-tertiary hover:text-accent-primary hover:bg-tertiary-op50 transition-all"
            >
              <CaretRight
                size={12} weight="bold"
                className={cn('transition-transform duration-200', isExpanded && 'rotate-90')}
              />
            </button>
          )}
          <CATypeIcon isRoot size={isMobile ? 'lg' : 'md'} />
          <div className="flex-1 min-w-0">
            <span className={cn(
              'font-bold truncate block',
              isMobile ? 'text-base' : 'text-sm',
              'text-text-primary'
            )}>
              {ca.name || ca.common_name || t('cas.unnamedCA')}
            </span>
          </div>
          <TypeBadge type="root" isMobile={isMobile} t={t} />
          <StatusBadge status={ca.status} />
        </div>
        <div className={cn('mt-1.5', hasChildren ? 'ml-8' : 'ml-0')}>
          <CAInfoLine ca={ca} isMobile={isMobile} t={t} />
        </div>
      </div>

      {/* Children area */}
      {hasChildren && isExpanded && (
        <div className={cn(
          'ca-org-children-area',
          isMobile ? 'px-2 py-2 space-y-1.5' : 'px-3 py-2.5 space-y-1.5'
        )}>
          {ca.children.map(child => (
            <OrgChildCard
              key={child.id}
              ca={child}
              selectedId={selectedId}
              expandedNodes={expandedNodes}
              onToggle={onToggle}
              onSelect={onSelect}
              isMobile={isMobile}
              t={t}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function OrgChildCard({ ca, selectedId, expandedNodes, onToggle, onSelect, isMobile, t, isOrphan, depth = 1 }) {
  const isSelected = selectedId === ca.id
  const hasChildren = ca.children && ca.children.length > 0
  const isExpanded = expandedNodes?.has(ca.id)

  return (
    <div>
      <div
        onClick={() => onSelect(ca)}
        className={cn(
          'rounded-lg border cursor-pointer transition-all duration-150',
          isMobile ? 'px-3 py-2.5' : 'px-3 py-2',
          isSelected
            ? 'ca-org-child-selected border-accent-primary'
            : 'border-border-op50 bg-bg-primary hover:border-border hover:shadow-sm',
          isOrphan && 'border-dashed'
        )}
      >
        <div className="flex items-center gap-2">
          {hasChildren ? (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onToggle(ca.id) }}
              className="shrink-0 w-5 h-5 rounded flex items-center justify-center text-text-tertiary hover:text-accent-primary hover:bg-tertiary-op50 transition-all"
            >
              <CaretRight
                size={10} weight="bold"
                className={cn('transition-transform duration-200', isExpanded && 'rotate-90')}
              />
            </button>
          ) : (
            <div className="w-5" />
          )}
          <CATypeIcon isRoot={false} size={isMobile ? 'md' : 'sm'} />
          <div className="flex-1 min-w-0">
            <span className={cn(
              'font-semibold truncate block',
              isMobile ? 'text-sm' : 'text-xs',
              isSelected ? 'text-accent-primary' : 'text-text-primary'
            )}>
              {ca.name || ca.common_name || t('cas.unnamedCA')}
            </span>
          </div>
          <TypeBadge type="intermediate" isMobile={isMobile} t={t} />
          <StatusBadge status={ca.status} />
        </div>
        <div className={cn('mt-1', isMobile ? 'ml-9' : 'ml-7')}>
          <CAInfoLine ca={ca} isMobile={isMobile} t={t} />
        </div>
      </div>
      {hasChildren && isExpanded && (
        <div className={cn('space-y-1.5', isMobile ? 'pl-4 pt-1.5' : 'pl-5 pt-1.5')}>
          {ca.children.map(child => (
            <OrgChildCard
              key={child.id}
              ca={child}
              selectedId={selectedId}
              expandedNodes={expandedNodes}
              onToggle={onToggle}
              onSelect={onSelect}
              isMobile={isMobile}
              t={t}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// =============================================================================
// VIEW B: COLUMNS — One column per Root CA
// =============================================================================

function ColumnsView({ tree, selectedId, onSelect, isMobile, t }) {
  const roots = tree.filter(ca => ca.type === 'root')
  const orphans = tree.filter(ca => ca.type !== 'root')

  if (isMobile) {
    // Mobile: stacked sections
    return (
      <div className="space-y-4">
        {roots.map(root => (
          <div key={root.id} className="space-y-1.5">
            <ColumnHeader ca={root} selectedId={selectedId} onSelect={onSelect} isMobile t={t} />
            {root.children?.map(child => (
              <ColumnChildCard key={child.id} ca={child} selectedId={selectedId} onSelect={onSelect} isMobile t={t} />
            ))}
            {(!root.children || root.children.length === 0) && (
              <div className="text-center py-4 text-xs text-text-tertiary rounded-lg border border-dashed border-border-op50">
                {t('cas.noIntermediate')}
              </div>
            )}
          </div>
        ))}
        {orphans.length > 0 && (
          <div className="space-y-1.5">
            <div className="ca-col-header-orphan rounded-lg px-3 py-2">
              <span className="text-xs font-bold text-text-secondary">{t('cas.orphanCAs')}</span>
            </div>
            {orphans.map(ca => (
              <ColumnChildCard key={ca.id} ca={ca} selectedId={selectedId} onSelect={onSelect} isMobile t={t} isOrphan />
            ))}
          </div>
        )}
      </div>
    )
  }

  // Desktop: side-by-side columns
  return (
    <div className="flex gap-3 overflow-x-auto pb-2" style={{ minHeight: 200 }}>
      {roots.map(root => (
        <div key={root.id} className="ca-col-wrapper flex-1 min-w-[240px] max-w-[400px] flex flex-col rounded-xl border border-border-op60 overflow-hidden">
          <ColumnHeader ca={root} selectedId={selectedId} onSelect={onSelect} isMobile={false} t={t} />
          <div className="flex-1 p-2 space-y-1.5 overflow-y-auto">
            {root.children?.map(child => (
              <ColumnChildCard key={child.id} ca={child} selectedId={selectedId} onSelect={onSelect} isMobile={false} t={t} />
            ))}
            {(!root.children || root.children.length === 0) && (
              <div className="text-center py-6 text-xs text-text-tertiary">
                {t('cas.noIntermediate')}
              </div>
            )}
          </div>
        </div>
      ))}
      {orphans.length > 0 && (
        <div className="ca-col-wrapper flex-1 min-w-[220px] max-w-[300px] flex flex-col rounded-xl border border-dashed border-border-op60 overflow-hidden">
          <div className="ca-col-header-orphan px-3 py-2.5">
            <span className="text-xs font-bold text-text-secondary">{t('cas.orphanCAs')}</span>
          </div>
          <div className="flex-1 p-2 space-y-1.5 overflow-y-auto">
            {orphans.map(ca => (
              <ColumnChildCard key={ca.id} ca={ca} selectedId={selectedId} onSelect={onSelect} isMobile={false} t={t} isOrphan />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function ColumnHeader({ ca, selectedId, onSelect, isMobile, t }) {
  const isSelected = selectedId === ca.id
  return (
    <div
      onClick={() => onSelect(ca)}
      className={cn(
        'ca-org-root-header cursor-pointer transition-colors',
        isMobile ? 'px-3 py-2.5 rounded-lg' : 'px-3 py-2.5'
      )}
    >
      <div className="flex items-center gap-2">
        <CATypeIcon isRoot size="sm" />
        <span className={cn(
          'font-bold truncate flex-1',
          isMobile ? 'text-sm' : 'text-xs',
          isSelected ? 'text-accent-primary' : 'text-text-primary'
        )}>
          {ca.name || ca.common_name}
        </span>
        <StatusBadge status={ca.status} />
      </div>
      <div className="mt-1 ml-7">
        <div className="flex items-center gap-2 text-2xs text-text-tertiary">
          <span className="flex items-center gap-1">
            <Certificate size={11} weight="duotone" className="text-accent-primary" />
            <span className="font-semibold text-text-secondary">{ca.certs || 0}</span>
          </span>
          <span className="flex items-center gap-1">
            <ShieldCheck size={11} weight="duotone" className="text-text-tertiary" />
            <span className="text-text-secondary">{ca.children?.length || 0} int.</span>
          </span>
        </div>
      </div>
    </div>
  )
}

function ColumnChildCard({ ca, selectedId, onSelect, isMobile, t, isOrphan, depth = 1 }) {
  const isSelected = selectedId === ca.id
  const expiry = formatExpiry(ca.valid_to || ca.not_after, t)
  const hasChildren = ca.children && ca.children.length > 0

  return (
    <div>
      <div
        onClick={() => onSelect(ca)}
        className={cn(
          'rounded-lg border cursor-pointer transition-all duration-150',
          isMobile ? 'px-3 py-2.5' : 'px-2.5 py-2',
          isSelected
            ? 'ca-org-child-selected border-accent-primary'
            : 'border-border-op40 bg-bg-primary hover:border-border hover:shadow-sm',
          isOrphan && 'border-dashed'
        )}
      >
        <div className="flex items-center gap-2">
          <CATypeIcon isRoot={false} size="sm" />
          <span className={cn(
            'font-medium truncate flex-1 text-xs',
            isSelected ? 'text-accent-primary' : 'text-text-primary'
          )}>
            {ca.name || ca.common_name}
          </span>
          <StatusBadge status={ca.status} />
        </div>
        <div className="mt-1 ml-7 flex items-center gap-2 text-2xs text-text-tertiary">
          <span className="flex items-center gap-1">
            <Certificate size={10} weight="duotone" className="text-accent-primary" />
            <span className="font-semibold text-text-secondary">{ca.certs || 0}</span>
          </span>
          {expiry && (
            <>
              <span className="text-border">·</span>
              <span className={cn(
                'font-medium',
                expiry.variant === 'danger' ? 'text-status-danger' :
                expiry.variant === 'warning' ? 'text-status-warning' : 'text-text-secondary'
              )}>
                {expiry.text}
              </span>
            </>
          )}
        </div>
      </div>
      {hasChildren && (
        <div className="pl-3 pt-1 space-y-1.5">
          {ca.children.map(child => (
            <ColumnChildCard
              key={child.id}
              ca={child}
              selectedId={selectedId}
              onSelect={onSelect}
              isMobile={isMobile}
              t={t}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// =============================================================================
// VIEW C: LIST — Flat card rows
// =============================================================================

function ListView({ cas, allCAs, selectedId, onSelect, isMobile, t }) {
  return (
    <div className="rounded-xl border border-border-op60 bg-secondary-op30 overflow-hidden">
      <div className={cn(isMobile ? 'p-1.5 space-y-0.5' : 'p-2 space-y-0.5')}>
        {cas.map(ca => {
          const isSelected = selectedId === ca.id
          const parentCA = ca.parent_id ? allCAs.find(c => c.id === ca.parent_id) : null

          return (
            <div
              key={ca.id}
              onClick={() => onSelect(ca)}
              className={cn(
                'relative rounded-lg cursor-pointer transition-all duration-150',
                'border border-transparent',
                isMobile ? 'px-3 py-2.5' : 'px-3 py-2',
                isSelected
                  ? 'ca-org-child-selected border-accent-primary'
                  : 'hover:bg-bg-tertiary hover:border-border'
              )}
            >
              {isSelected && (
                <div className="absolute left-0 top-1.5 bottom-1.5 w-1 rounded-r-full bg-accent-primary" />
              )}
              {/* Row 1 */}
              <div className="flex items-center gap-2">
                <CATypeIcon isRoot={ca.type === 'root'} size={isMobile ? 'md' : 'sm'} />
                <span className={cn(
                  'font-semibold truncate flex-1',
                  isMobile ? 'text-sm' : 'text-xs',
                  isSelected ? 'text-accent-primary' : 'text-text-primary'
                )}>
                  {ca.name || ca.common_name || t('cas.unnamedCA')}
                </span>
                <TypeBadge type={ca.type} isMobile={isMobile} t={t} />
                <StatusBadge status={ca.status} />
              </div>
              {/* Row 2 */}
              <div className={cn('mt-1 flex items-center gap-2 text-2xs text-text-tertiary', isMobile ? 'ml-9' : 'ml-7')}>
                {parentCA && (
                  <span className="flex items-center gap-1 shrink-0">
                    <TreeStructure size={10} className="text-text-tertiary" />
                    <span className="text-text-secondary truncate max-w-[100px]">{parentCA.name || parentCA.common_name}</span>
                    <span className="text-border">·</span>
                  </span>
                )}
                <CAInfoLine ca={ca} isMobile={isMobile} t={t} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// =============================================================================
// CA DETAILS PANEL
// =============================================================================

function CADetailsPanel({ ca, canWrite, canDelete, onExport, onDelete, t }) {
  const [showExportModal, setShowExportModal] = useState(false)
  return (
    <>
    <div className="p-3 space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2">
        <CATypeIcon isRoot={ca.type === 'root' || ca.is_root} size="lg" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-text-primary truncate">
              {ca.name || ca.common_name || t('common.certificateAuthority')}
            </h3>
            <Badge variant={ca.type === 'root' || ca.is_root ? 'warning' : 'primary'} size="sm">
              {ca.type === 'root' || ca.is_root ? t('common.rootCA') : t('common.intermediateCA')}
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

      {/* Export + Delete Actions */}
      <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
        <Button type="button" size="xs" variant="secondary" onClick={() => setShowExportModal(true)}>
          <Download size={14} /> {t('export.title')}
        </Button>
        {canDelete('cas') && (
          <Button type="button" size="xs" variant="danger" onClick={onDelete} className="sm:!h-8 sm:!px-3">
            <Trash size={12} className="sm:w-3.5 sm:h-3.5" />
          </Button>
        )}
      </div>

      {/* Subject Info */}
      <CompactSection title={t('common.subject')}>
        <CompactGrid>
          <CompactField autoIcon="commonName" label={t('common.commonName')} value={ca.common_name} copyable className="col-span-2" />
          <CompactField autoIcon="organization" label={t('common.organization')} value={ca.organization} />
          <CompactField autoIcon="country" label={t('common.country')} value={ca.country} />
          <CompactField autoIcon="stateProvince" label={t('common.stateProvince')} value={ca.state} />
          <CompactField autoIcon="locality" label={t('cas.locality')} value={ca.locality} />
        </CompactGrid>
      </CompactSection>

      {/* Key Info */}
      <CompactSection title={t('common.keyInformation')}>
        <CompactGrid>
          <CompactField autoIcon="algorithm" label={t('common.algorithm')} value={ca.key_algorithm || 'RSA'} />
          <CompactField autoIcon="keySize" label={t('common.keySize')} value={ca.key_size} />
          <CompactField autoIcon="signature" label={t('common.signature')} value={ca.signature_algorithm} />
        </CompactGrid>
      </CompactSection>

      {/* Validity */}
      <CompactSection title={t('common.validity')}>
        <CompactGrid>
          <CompactField autoIcon="validFrom" label={t('common.validFrom')} value={ca.valid_from ? formatDate(ca.valid_from) : '—'} />
          <CompactField autoIcon="validTo" label={t('common.validTo')} value={ca.valid_to ? formatDate(ca.valid_to) : '—'} />
          <CompactField autoIcon="serialNumber" label={t('common.serialNumber')} value={ca.serial_number} copyable mono className="col-span-2" />
        </CompactGrid>
      </CompactSection>

      {/* Fingerprints */}
      {(ca.thumbprint_sha1 || ca.thumbprint_sha256) && (
        <CompactSection title={t('common.fingerprints')}>
          <CompactGrid>
            {ca.thumbprint_sha1 && (
              <CompactField autoIcon="sha1" label="SHA-1" value={ca.thumbprint_sha1} copyable mono className="col-span-2" />
            )}
            {ca.thumbprint_sha256 && (
              <CompactField autoIcon="sha256" label="SHA-256" value={ca.thumbprint_sha256} copyable mono className="col-span-2" />
            )}
          </CompactGrid>
        </CompactSection>
      )}
    </div>

    <ExportModal
      open={showExportModal}
      onClose={() => setShowExportModal(false)}
      entityType="ca"
      entityName={ca.name || ca.common_name || ''}
      hasPrivateKey={!!ca.has_private_key}
      canExportKey={canWrite('cas')}
      onExport={onExport}
    />
    </>
  )
}

// Compact chain repair bar — sits under stats
function ChainRepairBar({ data, running, onRun, canRunRepair, t }) {
  const task = data?.task || {}
  const crStats = data?.stats || {}
  const [countdown, setCountdown] = useState('')

  useEffect(() => {
    if (!task.next_run) return
    const update = () => {
      const diff = Math.max(0, Math.floor((new Date(task.next_run).getTime() - Date.now()) / 1000))
      const m = Math.floor(diff / 60)
      const s = diff % 60
      setCountdown(`${m}:${String(s).padStart(2, '0')}`)
    }
    update()
    const id = setInterval(update, 1000)
    return () => clearInterval(id)
  }, [task.next_run])

  const total = crStats.total_cas || 0
  const orphans = crStats.orphan_cas || 0
  const linked = total - orphans
  const pct = total > 0 ? Math.round((linked / total) * 100) : 100

  if (!data) return null

  return (
    <div className="flex items-center gap-3 px-4 py-1.5 border-b border-border-op30 bg-secondary-op30">
      <div className="flex items-center gap-1.5 text-text-tertiary shrink-0">
        <LinkSimple size={13} weight="duotone" />
        <span className="text-[11px] font-medium">{t('dashboard.chainRepair')}</span>
      </div>

      <div className="flex items-center gap-2 flex-1 max-w-xs">
        <div className="flex-1 h-1.5 rounded-full bg-tertiary-op80 overflow-hidden">
          <div 
            className={`h-full rounded-full transition-all duration-700 ${pct === 100 ? 'bg-accent-success' : 'bg-accent-warning'}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="text-[10px] font-bold font-mono text-text-secondary w-8 text-right">{pct}%</span>
      </div>

      <div className="hidden sm:flex items-center gap-3 text-[10px] text-text-tertiary">
        <span>{crStats.total_cas || 0} CA{(crStats.total_cas || 0) > 1 ? 's' : ''}</span>
        <span>{crStats.total_certs || 0} certs</span>
        {orphans > 0 && <span className="text-accent-warning">{orphans} {t('dashboard.chainRepairOrphans')}</span>}
      </div>

      <div className="flex items-center gap-2 shrink-0">
        {running ? (
          <span className="text-[10px] text-accent-primary flex items-center gap-1">
            <CircleNotch size={10} className="animate-spin" />
          </span>
        ) : countdown ? (
          <span className="text-[10px] text-text-tertiary font-mono flex items-center gap-1">
            <Timer size={10} />
            {countdown}
          </span>
        ) : null}
        {canRunRepair && (
        <button
          onClick={onRun}
          disabled={running}
          className="p-1 rounded hover:bg-tertiary-op80 text-text-tertiary hover:text-accent-primary transition-all disabled:opacity-50"
          title={t('dashboard.chainRepairRun')}
        >
          {running 
            ? <CircleNotch size={12} className="animate-spin" />
            : <ArrowClockwise size={12} />
          }
        </button>
        )}
      </div>
    </div>
  )
}
