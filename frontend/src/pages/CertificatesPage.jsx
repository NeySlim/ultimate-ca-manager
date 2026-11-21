/**
 * CertificatesPage: the mockup's certificates view (pageHead(), statusFilters(), tableView(), the
 * inspector) drawn from the real list. The server filters, sorts and pages; the state tabs count
 * the whole inventory. A certificate's name or chevron opens it in the zone's inspector, where its
 * actions live.
 */
import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import {
  Zone, PageHead, Btn, IconBtn, TextLink, StateFilters, TableView, SearchField, FilterSelect, AppliedFilters, BatchBar,
  TableFooter, LoadError, LoadCause, EmptyBlock, NoMatch,
} from '../components/atelier'
import { SmartImportModal } from '../components/SmartImport'
import { certificatesService, casService } from '../services'
import { useNotification, useInspector } from '../contexts'
import { usePermission, useRecentHistory, useWebSocket, usePersistedState } from '../hooks'
import { extractCN, certificateNames, downloadBlob, warnSkippedExport, exportToCSV, exportToJSON } from '../lib/utils'
import { CERT_STATUSES, parseOverviewFilters, toListParams, toSearch, withoutFilter } from '../lib/overviewFilters'
import { fetchPages } from '../lib/fetchAllPages'
import { SetupCard } from '../components/shell/SetupCard'
import { canExportPrivateKey } from '../lib/exportPermissions'
import { downloadExport } from '../lib/exportDownload'
import { soleImported } from '../lib/importResult'
import { useOpenEntity } from '../hooks/useOpenEntity'
import { IssueCertificateDialog } from './certificates/IssueCertificateDialog'
import { certificateColumns, certificateCard, issuerOf, SORT_FIELDS } from './certificates/certificateRows'
import { sourceLabel, sourceOf } from './certificates/certificateSources'
import { CertificateInspector } from './certificates/inspector/CertificateInspector'
import { ExportDialog } from './certificates/dialogs/ExportDialog'
import { BulkExportDialog } from './certificates/dialogs/BulkExportDialog'
import { CompareDialog } from './certificates/dialogs/CompareDialog'
import { FiltersDialog } from './certificates/dialogs/FiltersDialog'
import { certificateKeyLabel } from '../lib/certificateDetail'

const NONE = []
// The state tabs after « Tous », in the mockup's order; orphan when there are some, archived (no counter) last
const STATE_VIEWS = ['expiring', 'valid', 'expired', 'revoked']
// The page sizes of the server-paged footer, the choice kept
const PAGE_SIZES = [12, 25, 50, 100]
const EXPORT_MAX = 10000
const PRESETS_KEY = 'ucm-certs-presets'
// One chip for the two filters of the weak-key link
const WEAK_KEY = 'weak_key'
const SEARCH_WAIT = 300

// The row as the table shows it; the exports use the same one
function normalizeCertificate(cert) {
  const { name, subtitle } = certificateNames(cert)
  return {
    ...cert,
    status: cert.revoked ? 'revoked' : cert.status,
    cn: name || extractCN(cert.subject) || (cert.san_dns ? JSON.parse(cert.san_dns)[0] : null) || 'Certificate',
    subtitle,
  }
}

function readPresets() {
  try { const saved = localStorage.getItem(PRESETS_KEY); return saved ? JSON.parse(saved) : [] } catch { return [] }
}

export default function CertificatesPage() {
  const { t, i18n } = useTranslation()
  const { id: urlCertId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const openEntity = useOpenEntity()
  const { opened = [], activeKey } = useInspector()
  const docked = opened.find((o) => o.key === activeKey)
  const dockedId = docked?.type === 'certificate' ? Number(docked.entityId) : undefined
  const { addToHistory } = useRecentHistory('certificates')
  const { showSuccess, showError, showWarning } = useNotification()
  const { canWrite, hasPermission } = usePermission()
  const canExportKey = canExportPrivateKey('certificate', { hasPermission, canWrite })
  const { muteToasts } = useWebSocket()
  const number = useMemo(() => new Intl.NumberFormat(i18n.language || undefined), [i18n.language])

  const [certificates, setCertificates] = useState([])
  const [cas, setCas] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [counted, setCounted] = useState(false)
  const [certStats, setCertStats] = useState({ valid: 0, expiring: 0, expired: 0, revoked: 0, orphan: 0, total: 0 })

  const [dialog, setDialog] = useState(null)
  const [issueInitialData, setIssueInitialData] = useState(null)
  const [exportRowCert, setExportRowCert] = useState(null)
  const [selectedIds, setSelectedIds] = useState(() => new Set())
  // « Sélectionner les N résultats »: the selection is every result of the query
  const [selectAll, setSelectAll] = useState(false)
  const [presets, setPresets] = useState(readPresets)
  useEffect(() => { try { localStorage.setItem(PRESETS_KEY, JSON.stringify(presets)) } catch { /* private mode */ } }, [presets])

  const [page, setPage] = useState(1)
  const [savedPerPage, setPerPage] = usePersistedState('ucm-certs-per-page', PAGE_SIZES[0])
  const perPage = PAGE_SIZES.includes(savedPerPage) ? savedPerPage : PAGE_SIZES[0]
  const [total, setTotal] = useState(0)
  // The nearest expiry first, as the mockup opens
  const [sort, setSort] = useState({ key: 'days', asc: true })

  const [filterCA, setFilterCA] = usePersistedState('ucm-filter-certs-ca', [])
  const [filterSource, setFilterSource] = usePersistedState('ucm-filter-certs-source', [])
  const [filterTemplate, setFilterTemplate] = usePersistedState('ucm-filter-certs-template', [])
  const [searchValue, setSearchValue] = useState('')
  const [typed, setTyped] = useState(null)
  const searchTimer = useRef(0)
  useEffect(() => () => clearTimeout(searchTimer.current), [])

  // Filters carried by overview links: the URL is their only state, so removing one rewrites it
  const urlFilters = useMemo(() => parseOverviewFilters(location.search), [location.search])
  const urlFiltersKey = JSON.stringify(urlFilters)
  const linkView = urlFilters.length > 0
  const urlStatus = useMemo(() => urlFilters.filter(([k]) => k === 'status').map(([, v]) => v), [urlFilters])
  // The state tab lives in the URL (`view`), so a reload or a shared link keeps it
  const viewKey = new URLSearchParams(location.search).getAll('view').filter((v) => CERT_STATUSES.includes(v)).join(',')
  const viewStatus = useMemo(() => (viewKey ? viewKey.split(',') : NONE), [viewKey])
  const savedStatus = linkView ? NONE : viewStatus
  const activeStatus = linkView ? urlStatus : viewStatus
  // An overview link shows exactly what its counter counts: the saved filters step aside while it is open
  const savedCA = linkView ? NONE : filterCA
  const savedSource = linkView ? NONE : filterSource
  const savedTemplate = linkView ? NONE : filterTemplate
  const linkScopeKey = JSON.stringify(urlFilters.filter(([k]) => k !== 'status'))
  useEffect(() => {
    if (!linkView) return
    setPage(1)
    setSearchValue('')
    setTyped(null)
  }, [linkView, linkScopeKey])
  useEffect(() => { if (linkView) setPage(1) }, [linkView, urlFiltersKey])
  const leaveLink = useCallback(() => {
    if (linkView) navigate({ pathname: location.pathname, search: '' }, { replace: true })
  }, [linkView, location.pathname, navigate])

  const failed = Boolean(loadError) && certificates.length === 0
  const requestSeq = useRef(0)
  const listParams = useRef({})
  const exportLoader = useCallback(async (paging) => {
    const res = await certificatesService.getAll({ ...listParams.current, ...paging })
    return { ...res, data: (res.data || []).map(normalizeCertificate) }
  }, [])
  const loadData = useCallback(async () => {
    // A read started earlier must not overwrite a later one
    const seq = ++requestSeq.current
    try {
      setLoading(true)
      const params = { page, per_page: perPage, sort_by: SORT_FIELDS[sort.key] || 'valid_to', sort_order: sort.asc ? 'asc' : 'desc' }
      if (savedStatus.length > 0) params.status = savedStatus
      if (savedCA.length > 0) params.ca_id = savedCA
      if (savedSource.length > 0) params.source = savedSource
      if (savedTemplate.includes('modified')) params.template_modified = 'true'
      if (searchValue) params.search = searchValue
      Object.assign(params, toListParams(urlFilters))
      listParams.current = Object.fromEntries(Object.entries(params).filter(([k]) => k !== 'page' && k !== 'per_page'))
      const [certsRes, casRes, statsRes] = await Promise.all([
        certificatesService.getAll(params), casService.getAll(), certificatesService.getStats(),
      ])
      if (seq !== requestSeq.current) return
      const certs = certsRes.data || []
      setLoadError(null)
      setCertificates(certs)
      // A selection never outlives the rows it was made on
      setSelectedIds((prev) => {
        const kept = new Set(certs.filter((c) => prev.has(c.id)).map((c) => c.id))
        return kept.size === prev.size ? prev : kept
      })
      const totalCount = certsRes.meta?.total || certs.length
      setTotal(totalCount)
      const lastPage = Math.max(1, Math.ceil(totalCount / perPage))
      if (page > lastPage) setPage(lastPage)
      setCas(casRes.data || [])
      setCertStats(statsRes.data || { valid: 0, expiring: 0, expired: 0, revoked: 0, orphan: 0, total: 0 })
      setCounted(true)
    } catch (error) {
      if (seq !== requestSeq.current) return
      const next = { status: error?.status, request: error?.request, message: error?.message || t('messages.errors.loadFailed.certificates') }
      setLoadError((prev) => (prev && prev.status === next.status && prev.request === next.request && prev.message === next.message ? prev : next))
      showError(error.message || t('messages.errors.loadFailed.certificates'))
    } finally {
      if (seq === requestSeq.current) setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, perPage, JSON.stringify(savedStatus), JSON.stringify(savedCA), JSON.stringify(savedSource), JSON.stringify(savedTemplate), urlFiltersKey, sort.key, sort.asc, searchValue, showError, t])

  useEffect(() => { loadData() }, [loadData])
  // A new query drops the « every result » selection
  useEffect(() => { setSelectAll(false) }, [searchValue, viewKey, urlFiltersKey, JSON.stringify(savedCA), JSON.stringify(savedSource), JSON.stringify(savedTemplate)]) // eslint-disable-line react-hooks/exhaustive-deps

  // Reload when an action elsewhere changes the data (loadData in the deps: a stale loader would drop the filters, #345)
  useEffect(() => {
    const handler = (e) => { if (e.detail?.type === 'certificate') loadData() }
    window.addEventListener('ucm:data-changed', handler)
    return () => window.removeEventListener('ucm:data-changed', handler)
  }, [loadData])

  // `?action=create` (the overview's Émettre) opens the form, then leaves the URL
  useEffect(() => {
    if (new URLSearchParams(location.search).get('action') !== 'create') return
    if (canWrite('certificates')) setDialog('issue')
    navigate({ pathname: location.pathname, search: withoutFilter(location.search, 'action') }, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search])

  // A re-key from the CSR page arrives with its prefill
  useEffect(() => {
    if (location.state?.prefill && location.state?.source === 'rekey') {
      if (canWrite('certificates')) {
        setIssueInitialData(location.state.prefill)
        setDialog('issue')
      }
      navigate(location.pathname, { replace: true, state: {} })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state])

  const handleSelectCert = useCallback((cert) => {
    if (!cert) return
    openEntity('certificate', cert.id)
    if (cert.common_name || cert.subject) {
      addToHistory({ id: cert.id, name: cert.common_name || extractCN(cert.subject) || `Certificate ${cert.id}`, subtitle: cert.issuer ? extractCN(cert.issuer) : '' })
    }
  }, [addToHistory, openEntity])

  // Deep link: the detail is read by id, even when the row is filtered out
  useEffect(() => {
    if (urlCertId && !loading) {
      const id = parseInt(urlCertId, 10)
      if (!isNaN(id)) {
        openEntity('certificate', id)
        navigate('/certificates', { replace: true })
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlCertId, loading])

  // Orphans: a certificate whose CA is gone
  const rows = useMemo(() => {
    const refs = new Set(cas.map((ca) => ca.refid))
    return certificates.map((cert) => ({ ...normalizeCertificate(cert), isOrphan: cert.caref && !refs.has(cert.caref) }))
  }, [certificates, cas])

  const setStatus = useCallback((next) => {
    setPage(1)
    const params = new URLSearchParams(linkView ? withoutFilter(location.search, 'status') : location.search)
    params.delete('view')
    next.forEach((v) => params.append(linkView ? 'status' : 'view', v))
    const qs = params.toString()
    navigate({ pathname: location.pathname, search: qs ? `?${qs}` : '' }, { replace: true })
  }, [linkView, location.pathname, location.search, navigate])

  const orphanCount = certStats.orphan || 0
  const views = [
    { id: '', label: t('certificates.views.all'), count: certStats.total },
    ...STATE_VIEWS.map((id) => ({ id, label: t(`certificates.views.${id}`), count: certStats[id] || 0, warn: id === 'expiring' })),
    ...(orphanCount > 0 || activeStatus.includes('orphan') ? [{ id: 'orphan', label: t('certificates.views.orphan'), count: orphanCount }] : []),
    // No counter: the stats do not count archived certificates
    { id: 'archived', label: t('certificates.views.archived') },
  ]
  // Several statuses at once (a link, an older preset) are no single tab: none is pressed
  const activeView = activeStatus.length === 0 ? '' : activeStatus.length === 1 ? activeStatus[0] : null

  const onSort = (key) => { setPage(1); setSort((s) => ({ key, asc: s.key === key ? !s.asc : true })) }

  const onSearch = (v) => {
    setTyped(v)
    clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => { setTyped(null); setSearchValue(v); setPage(1) }, SEARCH_WAIT)
  }
  const searching = typed !== null

  const resetFilters = useCallback(() => {
    clearTimeout(searchTimer.current)
    setTyped(null)
    setSearchValue('')
    if (!linkView) { setFilterCA([]); setFilterSource([]); setFilterTemplate([]) }
    setPage(1)
    navigate({ pathname: location.pathname, search: '' }, { replace: true })
    requestAnimationFrame(() => document.getElementById('search')?.focus())
  }, [linkView, location.pathname, navigate, setFilterCA, setFilterSource, setFilterTemplate])
  const narrowed = Boolean(searchValue) || savedCA.length > 0 || savedSource.length > 0 || savedTemplate.length > 0

  // Presets: the search, the statuses and the filters, and the overview link when one is open
  const savePreset = (name) => {
    const filters = {}
    if (activeStatus.length) filters.status = activeStatus
    if (savedCA.length) filters.ca = savedCA
    if (savedSource.length) filters.source = savedSource
    if (savedTemplate.length) filters.template = savedTemplate
    if (searchValue) filters._search = searchValue
    if (linkView) filters.link = toSearch(urlFilters)
    setPresets((prev) => [...prev, { id: Date.now(), name, filters }])
  }
  const applyPreset = (filters = {}) => {
    setPage(1)
    const linked = parseOverviewFilters(typeof filters.link === 'string' ? filters.link : '')
    if (linked.length > 0) {
      navigate({ pathname: location.pathname, search: toSearch(linked) }, { replace: true })
      return
    }
    const status = [].concat(filters.status || []).filter((v) => CERT_STATUSES.includes(v))
    navigate({ pathname: location.pathname, search: status.length ? `?${status.map((v) => `view=${v}`).join('&')}` : '' }, { replace: true })
    setFilterCA([].concat(filters.ca || []))
    setFilterSource([].concat(filters.source || []))
    setFilterTemplate([].concat(filters.template || []))
    setTyped(null)
    setSearchValue(typeof filters._search === 'string' ? filters._search : '')
  }

  // The overview link's filters, one chip per value; the weak-key link reads as one
  // An authority reads by its name; the other values by their word
  const caName = (v) => { const ca = cas.find((c) => String(c.id) === v); return ca?.name || ca?.common_name || `#${v}` }
  const chips = useMemo(() => {
    const byKey = {}
    for (const [key, value] of urlFilters) (byKey[key] = byKey[key] || []).push(value)
    const out = []
    for (const [key, values] of Object.entries(byKey)) {
      if (key === 'live' || key === 'key_bits_below') continue
      if (key === 'key_algo_prefix' && byKey.key_bits_below) {
        out.push({ key: WEAK_KEY, label: `${t('overview.filter.weak_key')} : ${t('overview.filterValue.weakKey', { algo: values[0], bits: byKey.key_bits_below[0] })}`, remove: [WEAK_KEY] })
        continue
      }
      for (const v of values) {
        out.push({ key: `${key}-${v}`, label: t('table.filterChip', { label: t(`overview.filter.${key}`), value: key === 'ca_id' ? caName(v) : t(`overview.filterValue.${v}`, { defaultValue: v }) }), remove: [key, v] })
      }
    }
    // The template filter lives in the Filters dialog: its chip says it is on
    if (savedTemplate.includes('modified')) {
      out.unshift({ key: 'template', label: t('table.filterChip', { label: t('certificates.template'), value: t('certificates.modifiedFromTemplate') }), remove: ['template'] })
    }
    // Several statuses outside a link (an older preset) are no single tab: one chip says them
    if (!linkView && viewStatus.length > 1) {
      out.unshift({ key: 'view', label: t('table.filterChip', { label: t('certificates.state'), value: viewStatus.map((v) => t(`overview.filterValue.${v}`, { defaultValue: v })).join(', ') }), remove: ['view'] })
    }
    return out
  }, [urlFilters, linkView, viewStatus, savedTemplate, cas, t])
  const removeUrlFilter = useCallback(([key, value]) => {
    setPage(1)
    if (key === 'template') { setFilterTemplate([]); return }
    const search = key === WEAK_KEY
      ? withoutFilter(withoutFilter(location.search, 'key_algo_prefix'), 'key_bits_below')
      : withoutFilter(location.search, key, value)
    navigate({ pathname: location.pathname, search }, { replace: true })
  }, [location.pathname, location.search, navigate, setFilterTemplate])
  const liveScope = urlFilters.some(([k]) => k === 'live')

  // Selection: the ticked rows of the page, or every result
  const selectedRows = rows.filter((c) => selectedIds.has(c.id))
  const selCount = selectAll ? total : selectedRows.length
  const pageAll = rows.length > 0 && rows.every((r) => selectedIds.has(r.id))
  const clearSelection = () => { setSelectedIds(new Set()); setSelectAll(false) }

  const allRows = async () => {
    const { rows: list, complete } = await fetchPages(exportLoader, { perPage: 100, max: EXPORT_MAX })
    if (!complete) throw new Error(t('table.exportFailed'))
    return list
  }
  const metadata = (r) => ({
    id: r.id, common_name: r.cn, description: r.subtitle || '', issuer: issuerOf(r), source: sourceLabel(sourceOf(r), t),
    status: r.status, expires: r.valid_to, algorithm: certificateKeyLabel(r, t) || '', serial: r.serial_number || '', template: r.template_name || '',
  })
  const csvColumns = [
    ['id', 'ID'], ['common_name', t('common.commonName')], ['description', t('common.description')], ['issuer', t('common.issuer')],
    ['source', t('certificates.source')], ['status', t('certificates.state')], ['expires', t('certificates.expiry')],
    ['algorithm', t('common.keyAlgorithm')], ['serial', t('inspector.cert.serial')], ['template', t('certificates.template')],
  ].map(([key, header]) => ({ key, header }))
  // all: the toolbar's export (every result); otherwise the selection, or every result once « all » is chosen
  const runBulkExport = async (format, all) => {
    try {
      const every = all || selectAll
      const list = every ? await allRows() : selectedRows
      if (format === 'pem') {
        const blob = await certificatesService.bulkExport(list.map((c) => c.id), 'pem')
        if (blob) downloadBlob(blob, 'certificates_export.pem')
        showSuccess(t('certificates.bulkExported', { count: blob?.exportedCount ?? list.length }))
        warnSkippedExport(blob, t, showWarning)
      } else {
        const data = list.map(metadata)
        if (format === 'csv') exportToCSV(data, csvColumns, 'certificates')
        else exportToJSON(data, 'certificates')
        if (every && total > EXPORT_MAX) showWarning(t('table.exportTruncated', { count: EXPORT_MAX, total }))
      }
      setDialog(null)
    } catch (err) {
      showError(err?.status ? err.message : t('messages.errors.exportFailed.certificate'))
    }
  }

  const handleExportRow = async (format, options = {}) => {
    const cert = exportRowCert
    if (!cert) return
    try {
      await downloadExport(certificatesService.export(cert.id, format, options), { format, name: cert.common_name || cert.cn || 'certificate' })
      showSuccess(t('messages.success.export.certificate'))
    } catch (err) {
      showError(err?.status ? err.message : t('messages.errors.exportFailed.certificate'))
    }
  }

  // The CA filter: one authority, grouped under its root as the mockup's select
  const caGroups = useMemo(() => {
    const byId = Object.fromEntries(cas.map((c) => [c.id, c]))
    const rootOf = (c) => { let x = c; const seen = new Set(); while (x?.parent_id && byId[x.parent_id] && !seen.has(x.id)) { seen.add(x.id); x = byId[x.parent_id] } return x }
    const name = (c) => c.descr || c.common_name || `#${c.id}`
    const groups = new Map()
    for (const c of cas) {
      const root = rootOf(c)
      if (!groups.has(root.id)) groups.set(root.id, { label: name(root), options: [] })
      groups.get(root.id).options.push({ value: String(c.id), label: name(c), root: c.id === root.id })
    }
    return [...groups.values()].map((g) => ({ ...g, options: [...g.options.filter((o) => o.root), ...g.options.filter((o) => !o.root)] }))
  }, [cas])
  const sources = (certStats.sources || []).map((s) => ({ value: s, label: sourceLabel(s, t) }))

  const columns = useMemo(() => certificateColumns(t), [t])
  const card = useMemo(() => certificateCard(t), [t])
  const pages = Math.max(1, Math.ceil(total / perPage))
  const start = total ? (page - 1) * perPage + 1 : 0
  const range = total ? t('certificates.range', { start: number.format(start), end: number.format(Math.min(page * perPage, total)), count: total }) : t('certificates.noneInRange')
  const head = (
    <PageHead title={t('common.certificates')}
      // No count before the first read: a zero there would be a claim
      total={failed || !counted ? '' : t('certificates.total', { count: certStats.total })}
      intent={t('certificates.intent')}
      actions={canWrite('certificates') && (
        <>
          <Btn tone="quiet" icon="upload" write data-action="import" onClick={() => setDialog('import')}>{t('common.import')}</Btn>
          <Btn tone="primary" icon="plus" data-action="issue" onClick={() => setDialog('issue')}>{t('certificates.issue')}</Btn>
        </>
      )} />
  )

  const issueDialog = (
    <IssueCertificateDialog open={dialog === 'issue'} onOpenChange={(open) => { if (!open) { setDialog(null); setIssueInitialData(null) } }}
      cas={cas} initialData={issueInitialData} onMutate={muteToasts}
      onIssued={() => { setIssueInitialData(null); loadData() }}
      onOpen={(issued) => { if (issued?.id) handleSelectCert(issued) }} />
  )
  const after = (
    <>
      {issueDialog}
      <SmartImportModal isOpen={dialog === 'import'} onClose={() => setDialog(null)}
        onImportComplete={(result) => {
          setDialog(null)
          loadData()
          const sole = soleImported(result)
          if (sole?.type === 'certificate') handleSelectCert({ id: sole.id })
          else if (sole) openEntity(sole.type, sole.id)
        }} />
      <ExportDialog open={!!exportRowCert} onClose={() => setExportRowCert(null)} entityType="certificate"
        entityName={exportRowCert?.common_name || exportRowCert?.cn || exportRowCert?.subject || ''} hasPrivateKey={!!exportRowCert?.has_private_key}
        keyAlgorithm={exportRowCert?.key_algorithm || exportRowCert?.key_type} relatedCertificateId={exportRowCert?.related_certificate_id ?? null}
        canExportKey={canExportKey} onExport={handleExportRow} chainVariantsFor={exportRowCert ? { type: 'certificate', id: exportRowCert.id } : undefined} />
      {(dialog === 'bulk' || dialog === 'bulk-all') && (
        <BulkExportDialog all={dialog === 'bulk-all' || selectAll} count={dialog === 'bulk-all' ? total : selCount} pageCount={rows.length} query={searchValue.trim()}
          onExport={(format) => runBulkExport(format, dialog === 'bulk-all')} onClose={() => setDialog(null)} />
      )}
      {dialog === 'compare' && selectedRows.length === 2 && <CompareDialog pair={selectedRows} onClose={() => setDialog(null)} />}
      {dialog === 'filters' && (
        <FiltersDialog template={savedTemplate.includes('modified') ? 'modified' : ''}
          onTemplate={(v) => { setPage(1); leaveLink(); setFilterTemplate(v ? [v] : []) }} presets={presets} canSave={narrowed || linkView || activeStatus.length > 0}
          onApply={(p) => { applyPreset(p.filters); setDialog(null) }} onDelete={(id) => setPresets((prev) => prev.filter((p) => p.id !== id))}
          onSave={savePreset} onClose={() => setDialog(null)} />
      )}
    </>
  )

  if (failed) {
    return (
      <Zone testId="certificates-zone" after={after}>
        {head}
        <div className="atl-out"><SetupCard admin={hasPermission('*')} /></div>
        <LoadError id="certificates" title={t('certificates.loadFailed')} onRetry={() => loadData()}
          journal={hasPermission('read:audit') ? '/audit' : undefined}
          cause={<LoadCause error={loadError} fallback={t('messages.errors.loadFailed.certificates')} />} />
      </Zone>
    )
  }

  const busy = loading && !rows.length
  const n = selCount
  return (
    <Zone testId="certificates-zone" dock={<CertificateInspector />} after={after}>
      {head}
      <div className="atl-out"><SetupCard admin={hasPermission('*')} /></div>
      <StateFilters views={views} active={activeView} onChange={(id) => setStatus(id ? [id] : [])} label={t('certificates.viewsLabel')} busy={!counted}
        aside={narrowed
          ? <TextLink icon="close" iconFirst data-action="clear-filters" onClick={resetFilters}> {t('certificates.clearSearchAndFilters')}</TextLink>
          : null} />
      <TableView label={t('certificates.listLabel')} tableLabel={t('certificates.tableLabel')} kind="certificates" scrollId="cert-scroll"
        caption={t('certificates.caption')} columns={columns} rows={rows} loading={busy} busy={busy || undefined}
        rowLabel={(r) => r.cn} onOpen={handleSelectCert} openedId={dockedId}
        rowActions={() => [{ icon: 'download', label: t('export.title'), onClick: (r) => setExportRowCert(r) }]}
        sort={sort} onSort={onSort} storageKey="ucm-certs-table"
        selection={{
          selected: selectAll ? new Set(rows.map((r) => r.id)) : selectedIds,
          onToggle: (id) => { setSelectAll(false); setSelectedIds((s) => { const x = new Set(s); if (x.has(id)) x.delete(id); else x.add(id); return x }) },
          onTogglePage: (on) => { setSelectAll(false); setSelectedIds(on ? new Set(rows.map((r) => r.id)) : new Set()) },
        }}
        search={(
          <>
            <SearchField id="search" name="q" label={t('certificates.searchLabel')} placeholder={t('certificates.searchPlaceholder')}
              value={searching ? typed : searchValue} onChange={onSearch}
              status={searching ? t('table.searching') : searchValue.trim() ? t('table.results', { count: total }) : ''} />
            <FilterSelect id="ca-filter" label={t('certificates.filterByCa')} value={savedCA[0] ? String(savedCA[0]) : ''}
              onChange={(v) => { setPage(1); leaveLink(); setFilterCA(v ? [v] : []) }}
              options={[{ value: '', label: t('common.allCAs') }]} groups={caGroups} />
            <FilterSelect id="source-filter" label={t('certificates.filterBySource')} value={savedSource[0] || ''}
              onChange={(v) => { setPage(1); leaveLink(); setFilterSource(v ? [v] : []) }}
              options={[{ value: '', label: t('certificates.allSources') }, ...sources]} />
          </>
        )}
        tools={(
          <>
            <IconBtn icon="filter" label={t('certificates.filters.title')} data-action="filters" onClick={() => setDialog('filters')} />
          </>
        )}
        columnsDialog={{ note: t('certificates.columnsNote') }} density
        exporter={{ label: t('certificates.exportList'), onClick: () => setDialog('bulk-all') }}
        applied={(chips.length > 0 || liveScope) && (
          <AppliedFilters chips={chips.map((c) => ({ key: c.key, label: c.label, onRemove: () => removeUrlFilter(c.remove) }))}
            note={liveScope ? t('certificates.liveScope') : undefined}
            onClearAll={() => { if (!linkView) setFilterTemplate([]); navigate({ pathname: location.pathname, search: '' }, { replace: true }) }} />
        )}
        batch={n > 0 && (
          <BatchBar onClear={clearSelection}
            count={selectAll ? t('certificates.allResultsSelected', { count: total }) : t('certificates.selectedOnPage', { count: n })}
            extra={selectAll
              ? <button type="button" className="text-link" id="select-page-only" data-action="select-page" onClick={() => setSelectAll(false)}>{t('certificates.keepPageOnly')}</button>
              : pageAll && total > rows.length
                ? <button type="button" className="text-link" id="select-all-results" data-action="select-results" onClick={() => setSelectAll(true)}>{t('certificates.selectAllResults', { count: total })}</button>
                : null}>
            <Btn icon="compare" data-action="compare" disabled={selectAll || n !== 2 || undefined} onClick={() => setDialog('compare')}>{t('common.compare')}</Btn>
            <Btn icon="download" id="bulk-export" data-action="bulk-export" onClick={() => setDialog('bulk')}>{t('certificates.exportSelection')}</Btn>
          </BatchBar>
        )}
        empty={!narrowed && !linkView && !activeStatus.length && !certStats.total ? (
          <EmptyBlock id="certificates" icon="cert" title={t('certificates.emptyTitle')}
            text={t(cas.length || !hasPermission('read:cas') ? 'certificates.emptyHintReady' : 'certificates.emptyHintNoCa')}
            action={canWrite('certificates') ? { label: t('certificates.issueCertificate'), icon: 'plus', primary: true, onClick: () => setDialog('issue') } : undefined} />
        ) : (
          <NoMatch title={t('certificates.noMatchTitle')} text={t('certificates.noMatchHint')} resetLabel={t('certificates.resetFilters')} onReset={resetFilters} />
        )}
        card={card}
        footer={(
          <TableFooter range={range}
            pagination={{ page, pages, perPage, sizes: PAGE_SIZES, jump: true, perPageLabel: t('certificates.perPageLabel'),
              onPage: setPage, onPerPage: (v) => { setPerPage(v); setPage(1) } }} />
        )}
        captionNote={t('certificates.listNote')} />
    </Zone>
  )
}

