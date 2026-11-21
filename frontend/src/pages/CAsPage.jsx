/**
 * CAsPage: the mockup's Authorities view (pageHead, then caView(): the trust hierarchy beside the
 * side panel of the selected authority, caSide()). The product keeps its state filters, its search,
 * a flat list beside the tree, the chain repair, the import and the creation of an authority.
 * The selected authority lives in the URL (`?authority=`), as in the mockup.
 */
import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams, useParams, useNavigate } from 'react-router-dom'
import {
  Zone, PageHead, Btn, IconBtn, Icon, StateFilters, Toolbar, SearchField, EmptyBlock, LoadError, LoadCause, SkeletonCards, AtelierDialog,
} from '../components/atelier'
import { SmartImportModal } from '../components/SmartImport'
import { casService, crlService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useRecentHistory, useWebSocket } from '../hooks'
import { useMobile } from '../contexts/MobileContext'
import { downloadExport } from '../lib/exportDownload'
import { HierarchyTree } from './cas/HierarchyTree'
import { CAList } from './cas/CAList'
import { CASide } from './cas/CASide'
import { ManageTemplatePinsModal } from '../components/cas/ManageTemplatePinsModal'
import { ChainRepairBar } from './cas/ChainRepairBar'
import { CreateCAModal } from './cas/CreateCAModal'
import { RestorePrimaryModal } from '../components/cas/RestorePrimaryModal'
import { IssueCertificateDialog } from './certificates/IssueCertificateDialog'
import { soleImported } from '../lib/importResult'
import { useOpenEntity } from '../hooks/useOpenEntity'
import { buildForest, filterCAs, viewCounts, chainNeedsAttention, nameOfCA, layoutRoots } from './cas/caTree'
import { useSetup, setupPending, openSetupAction } from '../components/shell/useSetup'

const VIEW_MODES = ['tree', 'list']
// 'org' and 'columns' are views the tree replaced: a stored choice of them opens the tree
const storedViewMode = () => {
  try {
    const mode = localStorage.getItem('ucm-ca-view-mode')
    return VIEW_MODES.includes(mode) ? mode : 'tree'
  } catch { return 'tree' }
}
// Cross-certificate issuers are read per authority: only the first holders are asked
const CROSS_LINK_HOLDERS = 12
const REQUEST = 'GET /api/v2/cas'

/** No authority yet: while the first-run steps remain, the way to the assistant, else Create a CA (the mockup's emptyAction). */
function CAsEmpty({ onCreate }) {
  const { t } = useTranslation()
  const { hasPermission } = usePermission()
  // Mounted only on an empty page: the first-run state is read then, not on every visit
  const setup = useSetup({ admin: hasPermission('*') })
  const action = setupPending(setup) ? openSetupAction(t)
    : onCreate ? { label: t('common.createCA'), icon: 'plus', primary: true, onClick: onCreate } : undefined
  return <EmptyBlock id="cas" icon="shield" title={t('cas.empty.title')} text={t('cas.empty.text')} action={action} />
}

export default function CAsPage() {
  const { t } = useTranslation()
  const { id: urlCAId } = useParams()
  const navigate = useNavigate()
  const { isMobile } = useMobile()
  const openEntity = useOpenEntity()
  const { showSuccess, showError, showWarning, showConfirm } = useNotification()
  const { canWrite, canDelete, canRead } = usePermission()
  const { muteToasts } = useWebSocket()
  const [searchParams, setSearchParams] = useSearchParams()
  const { addToHistory } = useRecentHistory('cas')

  const [cas, setCAs] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [loaded, setLoaded] = useState(false)
  const [showPinsModal, setShowPinsModal] = useState(false)
  const [pinsModalCA, setPinsModalCA] = useState(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)
  // On a phone the mockup hides the head's secondary buttons: they stay one tap away under « ⋯ »
  const [pageMenu, setPageMenu] = useState(false)
  const [issueCA, setIssueCA] = useState(null)
  const [ocsp, setOcsp] = useState(null)
  const sideRef = useRef(null)

  // The search filters both views; the state tab lives in the URL (`view`)
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

  // canWrite() is a fresh function each render: depend on the boolean it computes
  const canWriteCAs = canWrite('cas')
  const loadCAs = useCallback(async () => {
    setLoading(true)
    try {
      const casData = await casService.getAll()
      setCAs(casData.data || [])
      setLoadError(null)
    } catch (error) {
      setLoadError({ status: error?.status, request: REQUEST, message: error?.message })
    } finally {
      setLoading(false)
      setLoaded(true)
    }
    // Chain repair status (non-blocking, writers only)
    if (canWriteCAs) {
      casService.getChainRepairStatus().then((res) => setChainRepair(res.data || null)).catch(() => {})
      casService.getCrossFindings().then((res) => setCrossFindings(res.data?.findings || [])).catch(() => setCrossFindings([]))
    }
  }, [canWriteCAs])

  useEffect(() => {
    loadCAs()
    if (canRead('certificates')) crlService.getOcspStatus().then((res) => setOcsp(res?.data || null)).catch(() => setOcsp(null))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // `?action=create` (setup steps, the palette) opens the form, the page already open or not, then leaves the URL
  const askedAction = searchParams.get('action')
  useEffect(() => {
    if (askedAction !== 'create') return
    if (canWriteCAs) setCreateOpen(true)
    const next = new URLSearchParams(searchParams)
    next.delete('action')
    setSearchParams(next, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [askedAction])

  // Reload when an action changed an authority; the listener follows the loader (#345)
  useEffect(() => {
    const handler = (e) => { if (e.detail?.type === 'ca') loadCAs() }
    window.addEventListener('ucm:data-changed', handler)
    return () => window.removeEventListener('ucm:data-changed', handler)
  }, [loadCAs])

  // « Gérer les épingles » of the actions opens the pins dialog of this page
  useEffect(() => {
    const handler = (e) => {
      const ca = cas.find((c) => c.id === e.detail?.caId)
      if (ca) { setPinsModalCA(ca); setShowPinsModal(true) }
    }
    window.addEventListener('ucm:open-pins-modal', handler)
    return () => window.removeEventListener('ucm:open-pins-modal', handler)
  }, [cas])

  // The authority shown beside the tree: `?authority=` (the mockup's), `?selected=` and /cas/:id lead there
  const select = useCallback((id) => {
    const next = new URLSearchParams(window.location.search)
    next.set('authority', String(id))
    next.delete('selected')
    setSearchParams(next, { replace: true })
  }, [setSearchParams])
  useEffect(() => {
    const legacy = urlCAId || searchParams.get('selected')
    if (!legacy) return
    const id = parseInt(legacy, 10)
    if (Number.isNaN(id)) return
    const next = new URLSearchParams(searchParams)
    next.delete('selected')
    next.set('authority', String(id))
    navigate({ pathname: '/cas', search: `?${next.toString()}` }, { replace: true })
  }, [urlCAId, searchParams, navigate])

  const runChainRepair = useCallback(async () => {
    setChainRepairRunning(true)
    try {
      const res = await casService.runChainRepair()
      setChainRepair(res.data || null)
      loadCAs()
    } catch { /* the strip keeps its last status */ }
    finally { setChainRepairRunning(false) }
  }, [loadCAs])

  const handleConvertToCross = async (finding) => {
    const confirmed = await showConfirm(t('crossCerts.convertConfirm', { name: finding.ca_name, root: finding.root_name }), {
      title: t('crossCerts.convertToCross'), confirmText: t('crossCerts.convertToCross'), variant: 'danger',
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

  const handleDownload = async (ca) => {
    try {
      await downloadExport(casService.export(ca.id, 'pem'), { format: 'pem', name: nameOfCA(ca) || 'ca' })
      showSuccess(t('messages.success.export.ca'))
    } catch (error) {
      showError(error?.status ? error.message : t('messages.errors.exportFailed.generic'))
    }
  }

  // Who cross-certified whom, for the links of the tree and the side panel
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

  // State filters: the counters cover every authority, whatever the search
  const counts = useMemo(() => viewCounts(cas), [cas])
  const views = useMemo(() => counts.map(({ id, count }) => ({ id, count, label: t(`cas.views.${id || 'all'}`) })), [counts, t])
  const urlView = searchParams.get('view') || ''
  const activeView = counts.some((v) => v.id === urlView) ? urlView : ''
  const setView = (id) => {
    const next = new URLSearchParams(searchParams)
    if (id) next.set('view', id)
    else next.delete('view')
    setSearchParams(next, { replace: true })
  }
  const resetFilters = () => { setSearchQuery(''); setView('') }

  const allForest = useMemo(() => buildForest(cas), [cas])
  const forest = useMemo(() => buildForest(cas, { view: activeView, query: searchQuery }), [cas, activeView, searchQuery])
  const listed = useMemo(() => filterCAs(cas, { view: activeView, query: searchQuery }), [cas, activeView, searchQuery])

  const wanted = Number(searchParams.get('authority'))
  // The mockup shows its first authority when none is chosen: the first card of the tree
  const first = useMemo(() => {
    const { branches, compact, idle } = layoutRoots(forest, { query: searchQuery, linked: new Set(crossLinks.flatMap((l) => [l.from, l.to])) })
    return branches[0] || compact[0] || idle[0] || cas[0]
  }, [forest, searchQuery, crossLinks, cas])
  const selected = allForest.byId.get(wanted) || (loaded ? first : null) || null
  const selectedId = selected?.id

  const onSelect = (ca, { keyboard = false } = {}) => {
    if (!ca) return
    select(ca.id)
    addToHistory({ id: ca.id, name: nameOfCA(ca) || `CA ${ca.id}`, subtitle: t(ca.type === 'root' ? 'common.rootCA' : 'common.intermediateCA') })
    // On a phone the panel sits under the tree: a tap brings it into view
    if (isMobile && !keyboard) requestAnimationFrame(() => sideRef.current?.scrollIntoView?.({ block: 'start' }))
  }
  // A link of the side panel: the mockup's selectCA(), which then focuses the node in the tree
  const pick = (id) => {
    const ca = allForest.byId.get(id)
    if (!ca) return
    onSelect(ca, { keyboard: true })
    requestAnimationFrame(() => document.getElementById(`ca-node-${id}`)?.focus())
  }

  const repairNeeded = chainNeedsAttention(chainRepair, crossFindings, chainRepairRunning)
  const showRepair = !!chainRepair && (repairNeeded || repairOpen)

  let body
  if (loadError && !cas.length) {
    body = <LoadError id="cas" title={t('cas.loadFailed')} cause={<LoadCause error={loadError} />} onRetry={loadCAs}
      journal={canRead('audit') ? '/audit' : undefined} />
  } else if (loading && !loaded) {
    body = (
      <div className="scroll-view" id="view-scroll" aria-busy="true">
        <div className="ca-layout">
          <section className="panel ca-tree-panel" aria-labelledby="ca-tree-title">
            <header className="panel-heading"><div><h2 id="ca-tree-title">{t('cas.tree.title')}</h2><p>{t('cas.tree.hint')}</p></div></header>
            <div className="ca-tree-scroll"><SkeletonCards count={3} /></div>
          </section>
        </div>
      </div>
    )
  } else if (!cas.length) {
    body = (
      <div className="scroll-view" id="view-scroll">
        <div className="panel">
          <CAsEmpty onCreate={canWriteCAs ? () => setCreateOpen(true) : undefined} />
        </div>
      </div>
    )
  } else {
    body = (
      <div className="scroll-view" id="view-scroll">
        <div className="ca-layout">
          {viewMode === 'list' ? (
            <CAList cas={listed} allCAs={cas} resetKey={`${searchQuery}|${activeView}`} selectedId={selectedId} onSelect={onSelect} onDownload={handleDownload} t={t}
              empty={(
                <div className="empty">
                  <Icon name="search" /><h3>{t('cas.tree.noMatch')}</h3><p>{t('cas.tree.noMatchHint')}</p>
                  <button type="button" className="btn" data-action="reset-filters" onClick={resetFilters}>{t('cas.tree.reset')}</button>
                </div>
              )} />
          ) : (
            <HierarchyTree
              // A search or a tab opens the branches it kept; leaving it starts from the default folds
              key={searchQuery.trim() || activeView ? 'filtered' : 'browse'}
              forest={forest}
              query={searchQuery}
              filtered={!!activeView}
              crossLinks={crossLinks}
              selectedId={selectedId}
              onSelect={onSelect}
              onReset={resetFilters}
              total={cas.length}
              t={t}
            />
          )}
          {selected && (
            <CASide key={selected.id} asideRef={sideRef} ca={selected} cas={cas} forest={allForest} crossLinks={crossLinks} ocsp={ocsp}
                onPick={pick} onIssue={(ca) => setIssueCA(ca)}
                onCleared={() => {
                  const next = new URLSearchParams(window.location.search)
                  next.delete('authority')
                  setSearchParams(next, { replace: true })
                  loadCAs()
                }} />
          )}
        </div>
      </div>
    )
  }

  return (
    <Zone testId="cas-page" after={(
      <>
        {pageMenu && (
          <AtelierDialog title={t('cas.pageActions')} size="narrow" onClose={() => setPageMenu(false)} testId="cas-page-menu">
            <div className="columns-list">
              <button type="button" className="btn" onClick={() => { setPageMenu(false); setHelpOpen(true) }}><Icon name="help" />{t('cas.help.title')}</button>
              {canWriteCAs && (
                <button type="button" className="btn" data-write="" onClick={() => { setPageMenu(false); setShowImportModal(true) }}><Icon name="upload" />{t('common.import')}</button>
              )}
              {chainRepair && (
                <button type="button" className="btn" onClick={() => { setPageMenu(false); setRepairOpen(true) }}><Icon name="link" />{t('dashboard.chainRepair')}</button>
              )}
            </div>
          </AtelierDialog>
        )}
        {helpOpen && (
          <AtelierDialog title={t('cas.help.title')} size="narrow" onClose={() => setHelpOpen(false)} testId="cas-help">
            <p className="event-detail">{t('cas.help.text')}</p>
            <div className="modal-actions"><button type="button" className="btn primary" onClick={() => setHelpOpen(false)}>{t('common.close')}</button></div>
          </AtelierDialog>
        )}
      </>
    )}>
      <PageHead
        title={t('common.cas')}
        total={loaded && !loadError ? t('cas.total', { count: cas.length }) : ''}
        intent={t('cas.intent')}
        actions={(
          <>
            {chainRepair && !repairNeeded && (
              <Btn tone="quiet" icon="link" aria-expanded={repairOpen} onClick={() => setRepairOpen((v) => !v)}>{t('dashboard.chainRepair')}</Btn>
            )}
            <Btn icon="help" data-action="ca-help" onClick={() => setHelpOpen(true)}>{t('cas.help.title')}</Btn>
            {isMobile && (
              <IconBtn icon="more" quiet label={t('cas.pageActions')} id="ca-page-menu" aria-haspopup="dialog" onClick={() => setPageMenu(true)} />
            )}
            {canWriteCAs && (
              <>
                <Btn tone="quiet" icon="upload" write data-action="import" onClick={() => setShowImportModal(true)}>{t('common.import')}</Btn>
                <Btn tone="primary" icon="plus" data-action="create-ca" onClick={() => setCreateOpen(true)}>{t('common.createCA')}</Btn>
              </>
            )}
          </>
        )}
      />
      {showRepair && (
        <ChainRepairBar data={chainRepair} running={chainRepairRunning} onRun={runChainRepair} canRunRepair={canWriteCAs} t={t}
          findings={crossFindings} canConvert={canWriteCAs && canDelete('cas')} canRestore={canWriteCAs}
          onConvert={handleConvertToCross} onRestore={(finding, caId) => setRestoreFinding({ ...finding, caId })}
          caName={(id) => nameOfCA(cas.find((c) => c.id === id)) || `#${id}`} />
      )}
      {cas.length > 0 && (
        <>
          <StateFilters views={views} active={activeView} onChange={setView} label={t('cas.viewsLabel')} />
          <Toolbar>
            <SearchField id="ca-search" name="caSearch" label={t('cas.searchLabel')} placeholder={t('cas.searchPlaceholder')}
              value={searchQuery} onChange={setSearchQuery} />
            <div className="segmented" role="group" aria-label={t('cas.viewMode')}>
              {VIEW_MODES.map((mode) => (
                <button key={mode} type="button" aria-pressed={viewMode === mode} data-view-mode={mode} onClick={() => setViewMode(mode)}>
                  {t(mode === 'tree' ? 'cas.hierarchy' : 'cas.listMode')}
                </button>
              ))}
            </div>
          </Toolbar>
        </>
      )}
      {body}

      <CreateCAModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        cas={cas}
        onSuccess={(created) => {
          loadCAs()
          if (created?.id) select(created.id)
        }}
      />
      <SmartImportModal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        onImportComplete={(result) => {
          setShowImportModal(false)
          loadCAs()
          const sole = soleImported(result)
          if (sole?.type === 'ca') select(sole.id)
          else if (sole) openEntity(sole.type, sole.id)
        }}
      />
      <RestorePrimaryModal
        open={!!restoreFinding}
        onClose={() => setRestoreFinding(null)}
        ca={restoreFinding ? cas.find((c) => c.id === restoreFinding.caId) : null}
        onDone={loadCAs}
      />
      <ManageTemplatePinsModal open={showPinsModal} onOpenChange={setShowPinsModal} ca={pinsModalCA} t={t} />
      <IssueCertificateDialog
        open={!!issueCA}
        onOpenChange={(open) => { if (!open) setIssueCA(null) }}
        cas={cas}
        initialData={issueCA ? { ca_id: issueCA.id } : null}
        onMutate={muteToasts}
        onIssued={() => loadCAs()}
        onOpen={(issued) => { if (issued?.id) openEntity('certificate', issued.id) }}
      />
    </Zone>
  )
}
