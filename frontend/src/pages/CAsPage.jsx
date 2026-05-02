/**
 * CAs (Certificate Authorities) Page - Using ResponsiveLayout
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams, useParams, useNavigate } from 'react-router-dom'
import { 
  Certificate, UploadSimple, Clock, Plus, Crown, ShieldCheck, Columns, SquaresFour, List
} from '@phosphor-icons/react'
import {
  Button, LoadingSpinner, MultiSelectFilter
} from '../components'
import { SmartImportModal } from '../components/SmartImport'
import { ResponsiveLayout } from '../components/ui/responsive'
import { casService } from '../services'
import { useNotification } from '../contexts'
import { useWindowManager } from '../contexts/WindowManagerContext'
import { usePermission, useModals, useRecentHistory, useWebSocket, usePersistedState } from '../hooks'
import { useMobile } from '../contexts/MobileContext'
import { extractData, cn, downloadBlob } from '../lib/utils'
import { OrgView } from './cas/OrgView'
import { ColumnsView } from './cas/ColumnsView'
import { ListView } from './cas/ListView'
import { CADetailsPanel } from './cas/CADetailsPanel'
import { ChainRepairBar } from './cas/ChainRepairBar'
import { CreateCAModal } from './cas/CreateCAModal'

export default function CAsPage() {
  const { t } = useTranslation()
  const { id: urlCAId } = useParams()
  const navigate = useNavigate()
  const { isMobile } = useMobile()
  const { openWindow } = useWindowManager()
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canWrite, canDelete } = usePermission()
  const { muteToasts } = useWebSocket()
  const [searchParams, setSearchParams] = useSearchParams()
  const { addToHistory } = useRecentHistory('cas')
  
  const [cas, setCAs] = useState([])
  const [selectedCA, setSelectedCA] = useState(null)
  const [loading, setLoading] = useState(true)
  const { modals, open: openModal, close: closeModal } = useModals(['create'])
  const [showImportModal, setShowImportModal] = useState(false)
  
  // Filter state
  const [filterType, setFilterType] = usePersistedState('ucm-filter-cas-type', [])
  const [filterStatus, setFilterStatus] = usePersistedState('ucm-filter-cas-status', [])
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
    try { return localStorage.getItem('ucm-ca-view-mode') || 'org' } catch { return 'org' }
  })
  
  // Save view mode preference
  useEffect(() => {
    try { localStorage.setItem('ucm-ca-view-mode', viewMode) } catch {}
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
      casService.getChainRepairStatus()
        .then(res => setChainRepair(res.data || null))
        .catch(() => {})
    }
  }

  const getParentName = (ca) => {
    if (ca.is_root) return t('common.rootCA')
    if (ca.parent_id) {
      const parent = cas.find(c => c.id === ca.parent_id)
      if (parent) return parent.common_name || parent.descr
    }
    return t('common.intermediate')
  }

  const loadCADetails = async (ca) => {
    // Desktop: open floating window
    if (!isMobile) {
      openWindow('ca', ca.id)
      addToHistory({
        id: ca.id,
        name: ca.common_name || ca.descr || `CA ${ca.id}`,
        subtitle: getParentName(ca)
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
        subtitle: getParentName(fullCA)
      })
    } catch {
      setSelectedCA(ca)
    }
  }

  const runChainRepair = useCallback(async () => {
    setChainRepairRunning(true)
    try {
      const res = await casService.runChainRepair()
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
      muteToasts()
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
      const ext = { pem: 'pem', der: 'der', pkcs7: 'p7b', pkcs12: 'p12', jks: 'jks' }[format] || format
      downloadBlob(blob, `${ca.name || ca.common_name || 'ca'}.${ext}`)
      showSuccess(t('messages.success.export.ca'))
    } catch (error) {
      showError(error.message || t('cas.exportFailed'))
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
    if (filterType.length > 0) {
      const filterByType = (nodes) => nodes.filter(node => {
        if (filterType.includes(node.type)) return true
        if (node.children?.length) {
          node.children = filterByType(node.children)
          return node.children.length > 0
        }
        return false
      })
      result = filterByType([...result])
    }
    
    // Apply status filter (map: Active/Expired from API)
    if (filterStatus.length > 0) {
      const filterByStatus = (nodes) => nodes.filter(node => {
        if (filterStatus.includes(node.status)) return true
        if (node.children?.length) {
          node.children = filterByStatus(node.children)
          return node.children.length > 0
        }
        return false
      })
      result = filterByStatus([...result])
    }
    
    return result
  }, [treeData, searchQuery, filterType, filterStatus])

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
      type: 'multiSelect',
      value: filterType,
      onChange: setFilterType,
      placeholder: t('common.allTypes'),
      options: [
        { value: 'root', label: t('common.rootCA') },
        { value: 'intermediate', label: t('common.intermediateCA') }
      ]
    },
    {
      key: 'status',
      label: t('common.status'),
      type: 'multiSelect',
      value: filterStatus,
      onChange: setFilterStatus,
      placeholder: t('common.allStatus'),
      options: [
        { value: 'Active', label: t('common.active') },
        { value: 'Expired', label: t('common.expired') },
      ]
    }
  ], [filterType, filterStatus, t])

  const activeFiltersCount = (filterType.length > 0 ? 1 : 0) + (filterStatus.length > 0 ? 1 : 0)

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
                  
                  <MultiSelectFilter
                    value={filterType}
                    onChange={setFilterType}
                    placeholder={t('common.allTypes')}
                    options={[
                      { value: 'root', label: t('common.rootCA') },
                      { value: 'intermediate', label: t('common.intermediateCA') },
                    ]}
                  />
                  <MultiSelectFilter
                    value={filterStatus}
                    onChange={setFilterStatus}
                    placeholder={t('common.allStatus')}
                    options={[
                      { value: 'Active', label: t('common.active') },
                      { value: 'Expired', label: t('common.expired') },
                    ]}
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
                      if (filterType.length > 0 && !filterType.includes(ca.type)) return false
                      if (filterStatus.length > 0 && !filterStatus.includes(ca.status)) return false
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
      <CreateCAModal
        open={modals.create}
        onClose={() => closeModal('create')}
        cas={cas}
        onSuccess={loadCAs}
      />

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
