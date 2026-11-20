/**
 * CAsPage: the list template (page head, state tabs) over the trust hierarchy.
 * The tree is the default view; columns and list stay one click away.
 *
 * DESKTOP: a node opens the authority in the inspector dock, where its actions live
 * MOBILE: full-screen slide-over
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams, useParams, useNavigate } from 'react-router-dom'
import {
  UploadSimple, Plus, ShieldCheck, Columns, List, TreeStructure, LinkSimple, MagnifyingGlass, X } from '@phosphor-icons/react'
import { Button, LoadingSpinner } from '../components'
import { ListButton } from '../components/list'
import { SmartImportModal } from '../components/SmartImport'
import { ResponsiveLayout } from '../components/ui/responsive'
import { casService } from '../services'
import { useNotification, useInspector } from '../contexts'
import { usePermission, useModals, useRecentHistory, useWebSocket } from '../hooks'
import { useMobile } from '../contexts/MobileContext'
import { extractData } from '../lib/utils'
import { downloadExport } from '../lib/exportDownload'
import { HierarchyTree } from './cas/HierarchyTree'
import { ColumnsView } from './cas/ColumnsView'
import { ListView } from './cas/ListView'
import { CADetailsPanel } from './cas/CADetailsPanel'
import { ManageTemplatePinsModal } from '../components/cas/ManageTemplatePinsModal'
import { ChainRepairBar } from './cas/ChainRepairBar'
import { CreateCAModal } from './cas/CreateCAModal'
import { RestorePrimaryModal } from '../components/cas/RestorePrimaryModal'
import { soleImported } from '../lib/importResult'
import { useOpenEntity } from '../hooks/useOpenEntity'
import { buildForest, nestedForest, filterCAs, viewCounts, chainNeedsAttention, nameOfCA } from './cas/caTree'
import './cas/hierarchy.css'

const VIEW_MODES = [
  { mode: 'tree', icon: TreeStructure, label: 'cas.treeView' },
  { mode: 'columns', icon: Columns, label: 'cas.columnsView' },
  { mode: 'list', icon: List, label: 'cas.listView' },
]
// 'org' is what the tree replaced: a stored choice of it opens the tree
const storedViewMode = () => {
  try {
    const mode = localStorage.getItem('ucm-ca-view-mode')
    return VIEW_MODES.some((v) => v.mode === mode) ? mode : 'tree'
  } catch { return 'tree' }
}
// Cross-certificate issuers are read per authority: only the first holders are asked
const CROSS_LINK_HOLDERS = 12

export default function CAsPage() {
  const { t } = useTranslation()
  const { id: urlCAId } = useParams()
  const navigate = useNavigate()
  const { isMobile } = useMobile()
  const openEntity = useOpenEntity()
  const { showSuccess, showError, showWarning, showConfirm } = useNotification()
  const { canWrite, canDelete, hasPermission } = usePermission()
  const { muteToasts } = useWebSocket()
  const [searchParams, setSearchParams] = useSearchParams()
  const { addToHistory } = useRecentHistory('cas')
  
  const [cas, setCAs] = useState([])
  const [selectedCA, setSelectedCA] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showPinsModal, setShowPinsModal] = useState(false)
  const [pinsModalCA, setPinsModalCA] = useState(null)
  const { modals, open: openModal, close: closeModal } = useModals(['create'])
  const [showImportModal, setShowImportModal] = useState(false)
  
  // The search filters the three views; the state tab lives in the URL (`view`)
  const [searchQuery, setSearchQuery] = useState('')

  // Chain repair state
  const [chainRepair, setChainRepair] = useState(null)
  const [chainRepairRunning, setChainRepairRunning] = useState(false)
  const [repairOpen, setRepairOpen] = useState(false)
  // CA records damaged before cross-certificates existed (#400), with their explicit repairs
  const [crossFindings, setCrossFindings] = useState([])
  const [restoreFinding, setRestoreFinding] = useState(null)
  // { from, to } authority ids: `from` issued a cross-certificate to `to`
  const [crossLinks, setCrossLinks] = useState([])

  const [viewMode, setViewMode] = useState(storedViewMode)
  useEffect(() => {
    try { localStorage.setItem('ucm-ca-view-mode', viewMode) } catch { /* Storage is optional. */ }
  }, [viewMode])

  // The authority on top in the dock marks its node
  const { opened = [], activeKey } = useInspector()
  const docked = opened.find((o) => o.key === activeKey)
  const dockedId = docked?.type === 'ca' ? Number(docked.entityId) : undefined
  const selectedId = isMobile ? selectedCA?.id : dockedId

  // Memoised so the 'ucm:data-changed' listener below can depend on it without
  // re-subscribing on every render. canWrite() is a fresh function each render,
  // so depend on the boolean it computes, not on the function.
  const canWriteCAs = canWrite('cas')
  const loadCAs = useCallback(async () => {
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
    if (canWriteCAs) {
      casService.getChainRepairStatus()
        .then(res => setChainRepair(res.data || null))
        .catch(() => {})
      casService.getCrossFindings()
        .then(res => setCrossFindings(res.data?.findings || []))
        .catch(() => setCrossFindings([]))
    }
  }, [canWriteCAs, showError, t])

  useEffect(() => {
    loadCAs()
    if (searchParams.get('action') === 'create') {
      openModal('create')
      searchParams.delete('action')
      setSearchParams(searchParams)
    }
  }, [])

  // Reload when inspector actions change data. loadCAs must be in the
  // dependencies: a listener registered once keeps the loader captured at
  // mount and reloads with the state of that moment (#345).
  useEffect(() => {
    const handler = (e) => {
      if (e.detail?.type === 'ca') loadCAs()
    }
    window.addEventListener('ucm:data-changed', handler)
    return () => window.removeEventListener('ucm:data-changed', handler)
  }, [loadCAs])

  // Handle open pins modal event from inspector
  useEffect(() => {
    const handler = (e) => {
      if (e.detail?.caId) {
        const ca = cas.find(c => c.id === e.detail.caId)
        if (ca) {
          setPinsModalCA(ca)
          setShowPinsModal(true)
        }
      }
    }
    window.addEventListener('ucm:open-pins-modal', handler)
    return () => window.removeEventListener('ucm:open-pins-modal', handler)
  }, [cas])

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
    // The row may be filtered out of the list: the detail is fetched by id
    if (urlCAId && !loading) {
      const id = parseInt(urlCAId, 10)
      if (!isNaN(id)) {
        if (!isMobile) {
          openEntity('ca', id)
        } else {
          loadCADetails({ id })
        }
        navigate('/cas', { replace: true })
      }
    }
  }, [urlCAId, loading])

  const getParentName = (ca) => {
    if (ca.is_root) return t('common.rootCA')
    if (ca.parent_id) {
      const parent = cas.find(c => c.id === ca.parent_id)
      if (parent) return parent.common_name || parent.descr
    }
    return t('common.intermediate')
  }

  const loadCADetails = async (ca) => {
    // Desktop: open inspector
    if (!isMobile) {
      openEntity('ca', ca.id)
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

  const handleConvertToCross = async (finding) => {
    const confirmed = await showConfirm(t('crossCerts.convertConfirm', { name: finding.ca_name, root: finding.root_name }), {
      title: t('crossCerts.convertToCross'),
      confirmText: t('crossCerts.convertToCross'),
      variant: 'danger'
    })
    if (!confirmed) return
    try {
      const res = await casService.convertToCross(finding.ca_id)
      for (const w of res?.data?.warnings || []) showWarning(w)
      showSuccess(t('crossCerts.converted'))
      loadCAs()
    } catch (error) {
      showError(error.message || t('crossCerts.convertFailed'))
    }
  }

  // CA actions of the slide-over (offline, restore, delete...) come from
  // useEntityActions and announce themselves with 'ucm:data-changed', which
  // this page already listens to.

  const handleDownload = async (ca) => {
    try {
      await downloadExport(casService.export(ca.id, 'pem'), { format: 'pem', name: nameOfCA(ca) || 'ca' })
      showSuccess(t('messages.success.export.ca'))
    } catch (error) {
      showError(error?.status ? error.message : t('messages.errors.exportFailed.generic'))
    }
  }

  // Who cross-certified whom, for the links of the tree
  const crossKey = cas.filter((c) => c.cross_certificate_count > 0).map((c) => `${c.id}:${c.cross_certificate_count}`).join(',')
  useEffect(() => {
    const holders = cas.filter((c) => c.cross_certificate_count > 0).slice(0, CROSS_LINK_HOLDERS)
    if (holders.length === 0) { setCrossLinks([]); return undefined }
    let live = true
    const byRef = new Map(cas.map((c) => [c.refid, c.id]))
    Promise.all(holders.map((ca) => casService.getCrossCertificates(ca.id)
      .then((res) => (res.data || []).map((x) => ({ from: byRef.get(x.issuer_caref), to: ca.id })))
      .catch(() => [])))
      .then((lists) => {
        if (!live) return
        const seen = new Set()
        setCrossLinks(lists.flat().filter((l) => {
          const key = `${l.from}-${l.to}`
          if (l.from === undefined || l.from === l.to || seen.has(key)) return false
          seen.add(key)
          return true
        }))
      })
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [crossKey])

  // State tabs: the counters cover every authority, whatever the search
  const counts = useMemo(() => viewCounts(cas), [cas])
  const views = useMemo(() => counts.map(({ id, count }) => ({
    id, count, label: t(`cas.views.${id || 'all'}`),
  })), [counts, t])
  const urlView = searchParams.get('view') || ''
  const activeView = counts.some((v) => v.id === urlView) ? urlView : ''
  const setView = (id) => {
    const next = new URLSearchParams(searchParams)
    if (id) next.set('view', id)
    else next.delete('view')
    setSearchParams(next, { replace: true })
  }

  const forest = useMemo(() => buildForest(cas, { view: activeView, query: searchQuery }), [cas, activeView, searchQuery])
  const nested = useMemo(() => (viewMode === 'columns' ? nestedForest(forest) : []), [viewMode, forest])
  const listed = useMemo(() => filterCAs(cas, { view: activeView, query: searchQuery }), [cas, activeView, searchQuery])

  const repairNeeded = chainNeedsAttention(chainRepair, crossFindings, chainRepairRunning)
  const showRepair = !!chainRepair && (repairNeeded || repairOpen)

  return (
    <>
      <ResponsiveLayout
        title={t('common.cas')}
        total={t('cas.total', { count: cas.length })}
        intent={t('cas.intent')}
        actions={(
          <>
            {chainRepair && !repairNeeded && (
              <ListButton quiet icon={LinkSimple} aria-expanded={repairOpen} onClick={() => setRepairOpen((v) => !v)}>
                {t('dashboard.chainRepair')}
              </ListButton>
            )}
            {canWrite('cas') && (
              <>
                <ListButton quiet icon={UploadSimple} onClick={() => setShowImportModal(true)} data-write>
                  {t('common.import')}
                </ListButton>
                <ListButton primary icon={Plus} title={t('common.createCA')} onClick={() => openModal('create')}>
                  {t('common.create')}
                </ListButton>
              </>
            )}
          </>
        )}
        views={views}
        activeView={activeView}
        onViewChange={setView}
        viewsLabel={t('cas.viewsLabel')}
        afterStats={showRepair && (
          <div className="ca-repair">
            <ChainRepairBar data={chainRepair} running={chainRepairRunning} onRun={runChainRepair} canRunRepair={canWrite('cas')} t={t}
              findings={crossFindings} canConvert={canWrite('cas') && canDelete('cas')} canRestore={canWrite('cas')}
              onConvert={handleConvertToCross} onRestore={(finding, caId) => setRestoreFinding({ ...finding, caId })}
              caName={(id) => cas.find(c => c.id === id)?.name || `#${id}`} />
          </div>
        )}
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
            hasPermission={hasPermission}
            onChanged={(updated) => setSelectedCA(prev => (prev && prev.id === updated.id ? { ...prev, ...updated } : prev))}
            onClose={() => setSelectedCA(null)}
            onMutate={muteToasts}
            t={t}
          />
        ) : null}
      >
        <div className="ca-page">
          <div className="lv-toolbar">
            <label className="lv-search">
              <MagnifyingGlass size={15} aria-hidden="true" />
              <input
                type="search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={t('cas.searchPlaceholder')}
                aria-label={t('cas.searchPlaceholder')}
              />
              {searchQuery && (
                <button type="button" className="lv-search-clear" aria-label={t('common.clear')} onClick={() => setSearchQuery('')}>
                  <X size={13} aria-hidden="true" />
                </button>
              )}
            </label>
            <div className="ca-switch" role="group" aria-label={t('cas.viewMode')}>
              {VIEW_MODES.map(({ mode, icon: Icon, label }) => (
                <button
                  key={mode}
                  type="button"
                  aria-pressed={viewMode === mode}
                  aria-label={t(label)}
                  title={t(label)}
                  onClick={() => setViewMode(mode)}
                >
                  <Icon size={15} aria-hidden="true" />
                </button>
              ))}
            </div>
          </div>

          {loading && cas.length === 0 ? (
            <div className="flex items-center justify-center py-12">
              <LoadingSpinner />
            </div>
          ) : cas.length === 0 ? (
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
          ) : viewMode === 'list' ? (
            <div className="ca-body is-table">
              <ListView
                cas={listed}
                allCAs={cas}
                selectedId={selectedId}
                onSelect={loadCADetails}
                onDownload={handleDownload}
                emptyTitle={t('cas.tree.noMatch')}
                t={t}
              />
            </div>
          ) : viewMode === 'columns' ? (
            <div className="ca-body">
              {nested.length === 0 ? (
                <p className="ca-empty" role="status">{t('cas.tree.noMatch')}</p>
              ) : (
                <ColumnsView
                  tree={nested}
                  selectedId={selectedId}
                  onSelect={loadCADetails}
                  isMobile={isMobile}
                  t={t}
                />
              )}
            </div>
          ) : (
            <div className="ca-body">
              <HierarchyTree
                // A search or a tab opens the branches it kept; leaving it starts from the default folds
                key={searchQuery.trim() || activeView ? 'filtered' : 'browse'}
                forest={forest}
                query={searchQuery}
                filtered={!!activeView}
                crossLinks={crossLinks}
                selectedId={selectedId}
                onSelect={loadCADetails}
                t={t}
              />
            </div>
          )}
        </div>
      </ResponsiveLayout>

      {/* Create CA Modal */}
      <CreateCAModal
        open={modals.create}
        onClose={() => closeModal('create')}
        cas={cas}
        onSuccess={(created) => {
          loadCAs()
          if (created?.id) loadCADetails(created)
        }}
      />

      {/* Smart Import Modal */}
      <SmartImportModal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        onImportComplete={(result) => {
          setShowImportModal(false)
          loadCAs()
          const sole = soleImported(result)
          if (sole?.type === 'ca') loadCADetails({ id: sole.id })
          else if (sole) openEntity(sole.type, sole.id)
        }}
      />

      <RestorePrimaryModal
        open={!!restoreFinding}
        onClose={() => setRestoreFinding(null)}
        ca={restoreFinding ? cas.find(c => c.id === restoreFinding.caId) : null}
        onDone={loadCAs}
      />

      {/* Manage Template Pins Modal */}
      <ManageTemplatePinsModal
        open={showPinsModal}
        onOpenChange={setShowPinsModal}
        ca={pinsModalCA}
        t={t}
      />
    </>
  )
}
