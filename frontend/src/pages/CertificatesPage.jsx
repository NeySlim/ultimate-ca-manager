/**
 * CertificatesPage: the list template (page head, state tabs, flat table) over
 * ResponsiveLayout and ResponsiveDataTable. A certificate's name opens it in the
 * inspector, where its actions live: in the page flow, full screen on a phone.
 */
import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams, useNavigate, useLocation } from 'react-router-dom'
import { Trans } from 'react-i18next'
import {
  Certificate, DownloadSimple, Plus, UploadSimple, ArrowsLeftRight, Warning, CaretRight, X
} from '@phosphor-icons/react'
import {
  ResponsiveLayout, ResponsiveDataTable, ListButton,
  CertificateCompareModal
} from '../components'
import { AppliedFilters, RefreshIcon } from '../components/list'
import { ExportModal } from '../components/ExportModal'
import { SmartImportModal } from '../components/SmartImport'
import { certificatesService, casService } from '../services'
import { useNotification, useInspector } from '../contexts'
import { usePermission, useRecentHistory, useWebSocket, usePersistedState } from '../hooks'
import { extractCN, certificateNames, downloadBlob, warnSkippedExport } from '../lib/utils'
import { CERT_STATUSES, parseOverviewFilters, toListParams, toSearch, withoutFilter } from '../lib/overviewFilters'
import { SetupCard } from '../components/shell/SetupCard'
import { canExportPrivateKey } from '../lib/exportPermissions'
import { downloadExport } from '../lib/exportDownload'
import { IssueCertificateDialog } from './certificates/IssueCertificateDialog'
import { useCertificateColumns, useCertificateCard } from './certificates/useCertificateColumns'
import { soleImported } from '../lib/importResult'
import { useOpenEntity } from '../hooks/useOpenEntity'
import { sourceLabel } from './certificates/certificateSources'

const NONE = []
// The state tabs, in order; orphan shows when there are some, archived (no counter) comes last
const STATE_VIEWS = ['expiring', 'valid', 'expired', 'revoked']
// Page sizes of the footer; 12 as the mockup, the choice is kept
const PAGE_SIZES = [12, 25, 50, 100]
const DEFAULT_SORT = { key: 'valid_to', direction: 'asc' }

// The row as the table shows it; the export uses the same one
function normalizeCertificate(cert) {
  const { name, subtitle } = certificateNames(cert)
  return {
    ...cert,
    status: cert.revoked ? 'revoked' : cert.status,
    cn: name || extractCN(cert.subject) || (cert.san_dns ? JSON.parse(cert.san_dns)[0] : null) || 'Certificate',
    subtitle,
  }
}

// One chip for the two filters of the weak-key link
const WEAK_KEY = 'weak_key'

export default function CertificatesPage() {
  const { t } = useTranslation()
  const { id: urlCertId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const openEntity = useOpenEntity()
  // The certificate on top in the dock marks its row
  const { opened = [], activeKey } = useInspector()
  const docked = opened.find((o) => o.key === activeKey)
  const dockedId = docked?.type === 'certificate' ? Number(docked.entityId) : undefined
  const { addToHistory } = useRecentHistory('certificates')
  
  // Data
  const [certificates, setCertificates] = useState([])
  const [cas, setCas] = useState([])
  const [loading, setLoading] = useState(true)
  // Why the last read failed ({ status, request, message }); the banner replaces an empty list until a read succeeds
  const [loadError, setLoadError] = useState(null)
  // Until the first read answers, the counters are bars, not zeros
  const [counted, setCounted] = useState(false)
  const [certStats, setCertStats] = useState({ valid: 0, expiring: 0, expired: 0, revoked: 0, orphan: 0, total: 0 })
  
  // Selection
  const [showIssueModal, setShowIssueModal] = useState(false)
  const [issueInitialData, setIssueInitialData] = useState(null)
  const [showImportModal, setShowImportModal] = useState(false)
  const [showCompareModal, setShowCompareModal] = useState(false)
  const [exportRowCert, setExportRowCert] = useState(null)
  // Rows ticked on the page on screen, and the two handed to the comparison
  const [selectedIds, setSelectedIds] = useState(() => new Set())
  const [comparePair, setComparePair] = useState([null, null])
  
  // Pagination
  const [page, setPage] = useState(1)
  const [savedPerPage, setPerPage] = usePersistedState('ucm-certs-per-page', PAGE_SIZES[0])
  const perPage = PAGE_SIZES.includes(savedPerPage) ? savedPerPage : PAGE_SIZES[0]
  const [total, setTotal] = useState(0)
  
  // Sorting (server-side): the nearest expiry first, as the mockup opens
  const [sortBy, setSortBy] = useState('valid_to')
  const [sortOrder, setSortOrder] = useState('asc')
  
  // Filters
  const [filterCA, setFilterCA] = usePersistedState('ucm-filter-certs-ca', [])
  const [filterSource, setFilterSource] = usePersistedState('ucm-filter-certs-source', [])
  const [filterTemplate, setFilterTemplate] = usePersistedState('ucm-filter-certs-template', [])
  const [searchValue, setSearchValue] = useState('')

  // Filters carried by overview links: the URL is their only state, so removing one rewrites it
  const urlFilters = useMemo(() => parseOverviewFilters(location.search), [location.search])
  const urlFiltersKey = JSON.stringify(urlFilters)
  const overviewChips = useMemo(() => {
    const byKey = {}
    for (const [key, value] of urlFilters) (byKey[key] = byKey[key] || []).push(value)
    const chips = Object.entries(byKey).map(([key, value]) => ({
      key, value, label: t(`overview.filter.${key}`),
      optionLabels: Object.fromEntries(value.map((v) => [v, t(`overview.filterValue.${v}`, { defaultValue: v })])),
    }))
    // The weak-key link of the compliance card reads as one chip, « Conformité : Clé faible, RSA < 3072 »
    if (!byKey.key_algo_prefix || !byKey.key_bits_below) return chips
    const [algo] = byKey.key_algo_prefix
    const [bits] = byKey.key_bits_below
    const weak = { key: WEAK_KEY, value: 'on', label: t('overview.filter.weak_key'), optionLabels: { on: t('overview.filterValue.weakKey', { algo, bits }) } }
    const at = chips.findIndex((c) => c.key === 'key_algo_prefix' || c.key === 'key_bits_below')
    const rest = chips.filter((c) => c.key !== 'key_algo_prefix' && c.key !== 'key_bits_below')
    rest.splice(at, 0, weak)
    return rest
  }, [urlFilters, t])
  const removeUrlFilter = useCallback((key, value) => {
    setPage(1)
    const search = key === WEAK_KEY
      ? withoutFilter(withoutFilter(location.search, 'key_algo_prefix'), 'key_bits_below')
      : withoutFilter(location.search, key, value)
    navigate({ pathname: location.pathname, search }, { replace: true })
  }, [location.pathname, location.search, navigate])
  // An overview link shows exactly what its counter counts: the saved filters step aside
  // while it is open, unapplied but kept in storage, and return once its filters are gone
  const linkView = urlFilters.length > 0
  const urlStatus = useMemo(() => urlFilters.filter(([k]) => k === 'status').map(([, v]) => v), [urlFilters])
  // The state tab lives in the URL (`view`), so a reload or a shared link keeps it; a
  // link view carries its own statuses instead and the tabs then edit those
  const viewKey = new URLSearchParams(location.search).getAll('view').filter((v) => CERT_STATUSES.includes(v)).join(',')
  const viewStatus = useMemo(() => (viewKey ? viewKey.split(',') : NONE), [viewKey])
  const savedStatus = linkView ? NONE : viewStatus
  const activeStatus = linkView ? urlStatus : viewStatus
  const savedCA = linkView ? NONE : filterCA
  const savedSource = linkView ? NONE : filterSource
  const savedTemplate = linkView ? NONE : filterTemplate
  // The search restarts on entering a link view or when its non-status filters change;
  // a status edit (card, selector) keeps it
  const linkScopeKey = JSON.stringify(urlFilters.filter(([k]) => k !== 'status'))
  useEffect(() => {
    if (!linkView) return
    setPage(1)
    setSearchValue('')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [linkView, linkScopeKey])
  useEffect(() => { if (linkView) setPage(1) }, [linkView, urlFiltersKey])
  // A preset saved in a link view carries the link, so applying it reopens the same view
  const presetExtras = useMemo(() => (linkView ? { link: toSearch(urlFilters) } : undefined), [linkView, urlFilters])
  // Touching a saved filter leaves the link view, so the change applies at once
  const leaveLink = useCallback(() => {
    if (linkView) navigate({ pathname: location.pathname, search: '' }, { replace: true })
  }, [linkView, location.pathname, navigate])

  // Apply filter preset callback
  const handleApplyFilterPreset = useCallback((filters) => {
    setPage(1) // Reset to first page when applying preset
    // The stored link is re-validated: unknown filters or values are dropped
    const linked = parseOverviewFilters(typeof filters.link === 'string' ? filters.link : '')
    if (linked.length > 0) {
      navigate({ pathname: location.pathname, search: toSearch(linked) }, { replace: true })
      return
    }
    // One navigation leaves any link view and sets the statuses of the preset
    const status = [].concat(filters.status || []).filter((v) => CERT_STATUSES.includes(v))
    navigate({ pathname: location.pathname, search: status.length ? `?${status.map((v) => `view=${v}`).join('&')}` : '' }, { replace: true })
    if (filters.ca) setFilterCA(Array.isArray(filters.ca) ? filters.ca : [filters.ca])
    else setFilterCA([])
    if (filters.source) setFilterSource(Array.isArray(filters.source) ? filters.source : [filters.source])
    else setFilterSource([])
  }, [navigate, location.pathname])
  
  const { showSuccess, showError, showWarning } = useNotification()
  const { canWrite, hasPermission } = usePermission()
  const failed = Boolean(loadError) && certificates.length === 0
  // One rule for every export surface on this page — the server's own (see
  // lib/exportPermissions): read:private_keys, not write:certificates.
  const canExportKey = canExportPrivateKey('certificate', { hasPermission, canWrite })
  const { muteToasts } = useWebSocket()

  const requestSeq = useRef(0)
  // The filters and sort of the list on screen, for the table's export
  const listParams = useRef({})
  const exportLoader = useCallback(
    async (paging) => {
      const res = await certificatesService.getAll({ ...listParams.current, ...paging })
      return { ...res, data: (res.data || []).map(normalizeCertificate) }
    }, [])
  const loadData = useCallback(async () => {
    // A reload started earlier must not overwrite a later one (filter changed
    // while an action's reload was in flight)
    const seq = ++requestSeq.current
    try {
      setLoading(true)
      
      // Build query params with filters and sort
      const params = { 
        page, 
        per_page: perPage,
        sort_by: sortBy,
        sort_order: sortOrder
      }
      if (savedStatus.length > 0) {
        // orphan included: the server selects it over the whole set, so it
        // pages like any other status (#345 review)
        params.status = savedStatus
      }
      if (savedCA.length > 0) {
        params.ca_id = savedCA
      }
      if (savedSource.length > 0) {
        params.source = savedSource
      }
      if (savedTemplate.includes('modified')) {
        params.template_modified = 'true'
      }
      if (searchValue) params.search = searchValue
      Object.assign(params, toListParams(urlFilters))
      
      listParams.current = Object.fromEntries(
        Object.entries(params).filter(([k]) => k !== 'page' && k !== 'per_page'))
      const [certsRes, casRes, statsRes] = await Promise.all([
        certificatesService.getAll(params),
        casService.getAll(),
        certificatesService.getStats()
      ])
      const certs = certsRes.data || []
      const caList = casRes.data || []

      if (seq !== requestSeq.current) return
      setLoadError(null)
      setCertificates(certs)
      // A selection never outlives the rows it was made on
      setSelectedIds((prev) => {
        const kept = new Set(certs.filter((c) => prev.has(c.id)).map((c) => c.id))
        return kept.size === prev.size ? prev : kept
      })
      const totalCount = certsRes.meta?.total || certs.length
      setTotal(totalCount)
      // The last row of the last page went away: stay on a page that exists
      const lastPage = Math.max(1, Math.ceil(totalCount / perPage))
      if (page > lastPage) setPage(lastPage)
      setCas(caList)
      setCertStats(statsRes.data || { valid: 0, expiring: 0, expired: 0, revoked: 0, orphan: 0, total: 0 })
      setCounted(true)
    } catch (error) {
      if (seq !== requestSeq.current) return
      // The same failure again keeps the same object: a reload must not re-render in a loop
      const next = { status: error?.status, request: error?.request, message: error?.message || t('messages.errors.loadFailed.certificates') }
      setLoadError((prev) => (prev && prev.status === next.status && prev.request === next.request && prev.message === next.message ? prev : next))
      showError(error.message || t('messages.errors.loadFailed.certificates'))
    } finally {
      if (seq === requestSeq.current) setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, perPage, JSON.stringify(savedStatus), JSON.stringify(savedCA), JSON.stringify(savedSource), JSON.stringify(savedTemplate), urlFiltersKey, sortBy, sortOrder, searchValue, showError, t])

  // Load data - reload when filters or sort change
  useEffect(() => {
    loadData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadData])

  // Reload when an action elsewhere changes the data (floating detail window).
  // loadData must be in the dependencies: a listener registered once keeps the
  // loader captured at mount, which reloads with the filters of that moment
  // and empties the active filter of everything set since (#345).
  useEffect(() => {
    const handler = (e) => {
      if (e.detail?.type === 'certificate') loadData()
    }
    window.addEventListener('ucm:data-changed', handler)
    return () => window.removeEventListener('ucm:data-changed', handler)
  }, [loadData])

  // `?action=create` (the overview's Issue button) opens the form, then leaves the URL
  useEffect(() => {
    if (new URLSearchParams(location.search).get('action') !== 'create') return
    if (canWrite('certificates')) setShowIssueModal(true)
    navigate({ pathname: location.pathname, search: withoutFilter(location.search, 'action') }, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search])

  // Handle re-key prefill from CSRs page navigation
  useEffect(() => {
    if (location.state?.prefill && location.state?.source === 'rekey') {
      if (canWrite('certificates')) {
        setIssueInitialData(location.state.prefill)
        setShowIssueModal(true)
      }
      // Clear navigation state to prevent re-triggering on refresh
      navigate(location.pathname, { replace: true, state: {} })
    }
  }, [location.state])


  // A certificate opens in the inspector (full screen on a phone), and joins the recent history
  const handleSelectCert = useCallback((cert) => {
    if (!cert) return
    openEntity('certificate', cert.id)
    if (cert.common_name || cert.subject) {
      addToHistory({
        id: cert.id,
        name: cert.common_name || extractCN(cert.subject) || `Certificate ${cert.id}`,
        subtitle: cert.issuer ? extractCN(cert.issuer) : ''
      })
    }
  }, [addToHistory, openEntity])

  // Deep-link: auto-select certificate from URL param
  useEffect(() => {
    // The row may be filtered out of the list: the detail is fetched by id
    if (urlCertId && !loading) {
      const id = parseInt(urlCertId, 10)
      if (!isNaN(id)) {
        openEntity('certificate', id)
        navigate('/certificates', { replace: true })
      }
    }
  }, [urlCertId, loading])

  // Normalize and filter data - detect orphans (cert without existing CA)
  const filteredCerts = useMemo(() => {
    const caRefIds = new Set(cas.map(ca => ca.refid))
    
    let result = certificates.map(cert => ({
      ...normalizeCertificate(cert),
      isOrphan: cert.caref && !caRefIds.has(cert.caref)
    }))
    
    // No second pass on the status here: the server already applied the
    // filter, over the whole set rather than the current page. Re-filtering
    // dropped rows the server had counted (a page of expiring certificates
    // under the Valid filter came back empty) and emptied the list entirely
    // for Orphan, which is not a status any row carries (#345 review).
    return result
  }, [certificates, cas])

  // Orphan count from the stats endpoint, over the whole set: counting the
  // rows on screen made the card follow the current page (#345 review)
  const orphanCount = certStats.orphan || 0

  // A link view edits the link's own statuses in the URL; the saved ones stay untouched
  const setUrlStatus = useCallback((next) => {
    const params = new URLSearchParams(withoutFilter(location.search, 'status'))
    params.delete('view')
    next.forEach((v) => params.append('status', v))
    const qs = params.toString()
    navigate({ pathname: location.pathname, search: qs ? `?${qs}` : '' }, { replace: true })
  }, [location.pathname, location.search, navigate])

  const setViewStatus = useCallback((next) => {
    const params = new URLSearchParams(location.search)
    params.delete('view')
    next.forEach((v) => params.append('view', v))
    const qs = params.toString()
    navigate({ pathname: location.pathname, search: qs ? `?${qs}` : '' }, { replace: true })
  }, [location.pathname, location.search, navigate])

  // One setter for the tabs, the chips and the presets: the link's statuses in a link view, the tab otherwise
  const setStatus = useCallback((next) => {
    setPage(1)
    if (linkView) setUrlStatus(next)
    else setViewStatus(next)
  }, [linkView, setUrlStatus, setViewStatus])

  // State tabs with the counters of the stats endpoint, over the whole inventory
  const views = useMemo(() => [
    { id: '', label: t('certificates.views.all'), count: certStats.total },
    ...STATE_VIEWS.map((id) => ({
      id, label: t(`certificates.views.${id}`), count: certStats[id],
      tone: id === 'expiring' ? 'warn' : undefined,
    })),
    ...(orphanCount > 0 || activeStatus.includes('orphan')
      ? [{ id: 'orphan', label: t('certificates.views.orphan'), count: orphanCount }] : []),
    // No counter: the stats endpoint does not count archived certificates
    { id: 'archived', label: t('certificates.views.archived') },
  ], [certStats, orphanCount, activeStatus, t])
  // Several statuses at once (a link, an older preset) are no single tab
  const activeView = activeStatus.length === 0 ? '' : activeStatus.length === 1 ? activeStatus[0] : null

  // Handle sort change (server-side)
  const handleSortChange = useCallback((newSort) => {
    setPage(1) // Reset to first page when sorting
    if (newSort) {
      // Map frontend column keys to backend field names
      const keyMap = {
        'cn': 'subject',
        'common_name': 'subject',
        'status': 'status', // Backend handles with CASE (groups by type)
        'issuer': 'issuer',
        'expires': 'valid_to',
        'valid_to': 'valid_to',
        'key_type': 'key_algo',
        'descr': 'descr',
        'created_at': 'created_at',
        'compliance_grade': 'compliance_grade'
      }
      const backendKey = keyMap[newSort.key]
      if (backendKey) {
        setSortBy(backendKey)
        setSortOrder(newSort.direction)
      }
    } else {
      setSortBy('valid_to')
      setSortOrder('asc')
    }
  }, [])

  // Column definitions (extracted to sub-module)
  const columns = useCertificateColumns(t)
  const card = useCertificateCard(t)

  // One action on the row; rename, renew, revoke and delete live in the inspector
  const rowActions = (row) => [
    { label: t('export.title'), icon: DownloadSimple, onClick: () => setExportRowCert(row) },
  ]

  const selectedRows = filteredCerts.filter((c) => selectedIds.has(c.id))
  const handleCompareSelected = () => {
    setComparePair([selectedRows[0] || null, selectedRows[1] || null])
    setShowCompareModal(true)
  }
  const handleExportSelected = async () => {
    const ids = selectedRows.map((c) => c.id)
    if (!ids.length) return
    try {
      const blob = await certificatesService.bulkExport(ids, 'pem')
      if (blob) downloadBlob(blob, 'certificates_export.pem')
      showSuccess(t('certificates.bulkExported', { count: blob?.exportedCount ?? ids.length }))
      warnSkippedExport(blob, t, showWarning)
    } catch (err) {
      showError(err?.status ? err.message : t('messages.errors.exportFailed.certificate'))
    }
  }

  // Export from row via ExportModal
  const handleExportRow = async (format, options = {}) => {
    if (!exportRowCert) return
    const cert = exportRowCert
    try {
      await downloadExport(
        certificatesService.export(cert.id, format, options),
        { format, name: cert.common_name || cert.cn || 'certificate' },
      )
      showSuccess(t('messages.success.export.certificate'))
    } catch (err) {
      showError(err?.status ? err.message : t('messages.errors.exportFailed.certificate'))
    }
  }

  // Filters
  const filters = useMemo(() => [
    {
      // The state tabs are its control: it stays here for the presets, the chips and Clear filters
      key: 'status',
      label: t('certificates.state'),
      type: 'multiSelect',
      hideControl: true,
      // One status is the tab on screen, the link's are in its own chip row
      hideChip: linkView || activeStatus.length < 2,
      // A link view shows (and a preset saves) the link's statuses
      value: activeStatus,
      onChange: setStatus,
      options: [
        { value: 'valid', label: t('common.valid') },
        { value: 'expiring', label: t('certificates.views.expiring') },
        { value: 'expired', label: t('common.expired') },
        { value: 'revoked', label: t('common.revoked') },
        { value: 'orphan', label: t('certificates.orphan') },
        { value: 'archived', label: t('certificates.archived') }
      ]
    },
    {
      key: 'ca',
      label: t('common.issuer'),
      type: 'multiSelect',
      value: savedCA,
      onChange: (val) => { if (linkView && val.length === 0) return; setPage(1); leaveLink(); setFilterCA(val) },
      placeholder: t('common.allCAs'),
      options: cas.map(ca => ({
        value: String(ca.id),
        label: ca.descr || ca.common_name
      }))
    },
    {
      key: 'source',
      label: t('certificates.source'),
      type: 'multiSelect',
      value: savedSource,
      onChange: (val) => { if (linkView && val.length === 0) return; setPage(1); leaveLink(); setFilterSource(val) },
      placeholder: t('certificates.allSources'),
      options: (certStats.sources || []).map(src => ({
        value: src,
        label: sourceLabel(src, t)
      }))
    },
    {
      key: 'template',
      label: t('certificates.template'),
      type: 'multiSelect',
      value: savedTemplate,
      onChange: (val) => { if (linkView && val.length === 0) return; setPage(1); leaveLink(); setFilterTemplate(val) },
      placeholder: t('certificates.allTemplates'),
      options: [
        { value: 'modified', label: t('certificates.modifiedFromTemplate') }
      ]
    }
  ], [linkView, activeStatus, setStatus, savedCA, savedSource, savedTemplate, leaveLink, certStats.sources, cas, t])

  // Everything the toolbar and the link set, back to the whole list; in a link view the
  // stored filters are not applied, so they stay stored for when the link is gone
  const resetFilters = useCallback(() => {
    setSearchValue('')
    if (!linkView) {
      setFilterCA([])
      setFilterSource([])
      setFilterTemplate([])
    }
    setPage(1)
    navigate({ pathname: location.pathname, search: '' }, { replace: true })
  }, [linkView, location.pathname, navigate])
  const narrowed = Boolean(searchValue) || savedCA.length > 0 || savedSource.length > 0 || savedTemplate.length > 0
  // `live` (an overview counter's scope) is said in words; the other link filters are chips
  const liveScope = urlFilters.some(([k]) => k === 'live')
  const linkChips = overviewChips.filter((c) => c.key !== 'live')

  // Cause of a failed read: the status and the request when the server answered, else the message
  const cause = loadError?.status && loadError.request ? (
    <Trans i18nKey="certificates.loadFailedStatus"
      values={{ status: loadError.status, reason: t(`certificates.httpStatus${loadError.status}`, { defaultValue: '' }), request: loadError.request }}
      components={{ mono: <span className="font-mono" /> }} />
  ) : loadError?.request ? (
    <Trans i18nKey="certificates.loadFailedNoAnswer" values={{ request: loadError.request }}
      components={{ mono: <span className="font-mono" /> }} />
  ) : t('certificates.loadFailedCause', { message: loadError?.message })

  return (
    <>
      <ResponsiveLayout
        title={t('common.certificates')}
        // No count before the first read succeeds: a zero there would be a claim
        total={failed || !counted ? '' : t('certificates.total', { count: certStats.total })}
        intent={t('certificates.intent')}
        actions={canWrite('certificates') && (
          <>
            <ListButton quiet icon={UploadSimple} data-write onClick={() => setShowImportModal(true)} className="lv-hide-mobile">
              {t('common.import')}
            </ListButton>
            <ListButton primary icon={Plus} title={t('certificates.issueCertificate')} onClick={() => setShowIssueModal(true)}>
              {t('certificates.issue')}
            </ListButton>
          </>
        )}
        beforeViews={<SetupCard admin={hasPermission('*')} />}
        views={failed ? [] : views}
        activeView={activeView}
        onViewChange={(id) => setStatus(id ? [id] : [])}
        viewsLabel={t('certificates.viewsLabel')}
        viewsPressed
        viewsBusy={!counted}
        viewsAside={narrowed && (
          <button type="button" className="lv-text-link" onClick={resetFilters} data-testid="clear-filters-link">
            <X size={14} aria-hidden="true" /> {t('certificates.clearSearchAndFilters')}
          </button>
        )}
      >
        {failed ? (
          <div className="lv-error" role="alert" data-testid="certificates-load-error">
            <Warning aria-hidden="true" />
            <div>
              <h2>{t('certificates.loadFailed')}</h2>
              <p>{cause}</p>
              <div className="lv-error-actions">
                <ListButton primary data-write="false" icon={RefreshIcon} onClick={() => loadData()}>{t('table.retry')}</ListButton>
                {hasPermission('read:audit') && (
                  <Link className="lv-text-link" to="/audit">{t('certificates.viewLog')}<CaretRight size={14} aria-hidden="true" /></Link>
                )}
              </div>
            </div>
          </div>
        ) : (
        <ResponsiveDataTable
          variant="list"
          data={filteredCerts}
          columns={columns}
          loading={loading}
          onRowClick={handleSelectCert}
          openFromName
          card={card}
          lockRowsOnSelect
          selectedId={dockedId}
          rowLabel={(row) => row.cn}
          tableLabel={t('certificates.listLabel')}
          rangeLabel={({ start, end, total: count }) => t('certificates.range', { start, end, count })}
          footNote={t('certificates.listNote')}
          searchable
          searchLabel={t('certificates.searchLabel')}
          searchPlaceholder={t('certificates.searchPlaceholder')}
          externalSearch={searchValue}
          onSearchChange={(v) => { setSearchValue(v); setPage(1) }}
          belowToolbar={(linkChips.length > 0 || liveScope) && (
            <AppliedFilters
              filters={linkChips}
              onRemove={removeUrlFilter}
              onClearAll={() => navigate({ pathname: location.pathname, search: '' }, { replace: true })}
              note={liveScope ? t('certificates.liveScope') : undefined}
              onRemoveNote={liveScope ? () => removeUrlFilter('live') : undefined}
            />
          )}
          columnStorageKey="ucm-certs-columns-v2"
          columnsNote={t('certificates.columnsNote')}
          filterPresetsKey="ucm-certs-presets"
          densityStorageKey="ucm-certs-density"
          onApplyFilterPreset={handleApplyFilterPreset}
          presetExtras={presetExtras}
          exportEnabled
          exportLoader={exportLoader}
          exportFilename="certificates"
          toolbarFilters={filters}
          multiSelect
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
          // The mockup: « 1 sélectionné » for part of the page, the long count once the page is whole
          selectionLabel={(count, { pageAll }) => t(pageAll ? 'certificates.selectedOnPage' : 'table.selectedCount', { count })}
          bulkActions={
            <>
              <ListButton
                small
                icon={ArrowsLeftRight}
                onClick={handleCompareSelected}
                disabled={selectedRows.length > 2}
                title={selectedRows.length > 2 ? t('certificates.compareHint') : undefined}
              >
                {t('common.compare')}
              </ListButton>
              <ListButton small icon={DownloadSimple} onClick={handleExportSelected} title={t('certificates.exportSelectedPem')}>
                {t('certificates.exportSelected')}
              </ListButton>
            </>
          }
          sortable
          defaultSort={DEFAULT_SORT}
          onSortChange={handleSortChange}
          rowActions={rowActions}
          pagination={{
            page,
            total,
            perPage,
            pageSizes: PAGE_SIZES,
            perPageLabel: t('certificates.perPageLabel'),
            onChange: setPage,
            onPerPageChange: (v) => { setPerPage(v); setPage(1) }
          }}
          noMatch={{
            title: t('certificates.noMatchTitle'),
            description: t('certificates.noMatchHint'),
            action: t('certificates.resetFilters'),
            onReset: resetFilters,
          }}
          emptyIcon={Certificate}
          emptyTitle={t('certificates.emptyTitle')}
          // As the mockup: the first issuance waits for an issuing CA, then the CA is ready
          emptyDescription={t(cas.length || !hasPermission('read:cas') ? 'certificates.emptyHintReady' : 'certificates.emptyHintNoCa')}
          emptyAction={canWrite('certificates') && (
            <ListButton primary icon={Plus} onClick={() => setShowIssueModal(true)}>
              {t('certificates.issueCertificate')}
            </ListButton>
          )}
        />
        )}
      </ResponsiveLayout>

      {/* Issue: Configure, then Review (the Atelier issue form) */}
      <IssueCertificateDialog
        open={showIssueModal}
        onOpenChange={(open) => {
          setShowIssueModal(open)
          if (!open) setIssueInitialData(null)
        }}
        cas={cas}
        initialData={issueInitialData}
        onMutate={muteToasts}
        onIssued={() => {
          setIssueInitialData(null)
          loadData()
        }}
        // "View the certificate" of the result screen
        onOpen={(issued) => { if (issued?.id) handleSelectCert(issued) }}
      />

      {/* Certificate Compare Modal */}
      <CertificateCompareModal
        open={showCompareModal}
        onClose={() => setShowCompareModal(false)}
        certificates={certificates}
        initialCert={comparePair[0]}
        secondCert={comparePair[1]}
      />

      {/* Smart Import Modal */}
      <SmartImportModal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        onImportComplete={(result) => {
          setShowImportModal(false)
          loadData()
          const sole = soleImported(result)
          if (sole?.type === 'certificate') handleSelectCert({ id: sole.id })
          else if (sole) openEntity(sole.type, sole.id)
        }}
      />

      {/* Row Export Modal */}
      <ExportModal
        open={!!exportRowCert}
        onClose={() => setExportRowCert(null)}
        entityType="certificate"
        entityName={exportRowCert?.common_name || exportRowCert?.subject || ''}
        hasPrivateKey={!!exportRowCert?.has_private_key}
        keyAlgorithm={exportRowCert?.key_algorithm || exportRowCert?.key_type}
        relatedCertificateId={exportRowCert?.related_certificate_id ?? null}
        canExportKey={canExportKey}
        onExport={handleExportRow}
        chainVariantsFor={exportRowCert ? { type: 'certificate', id: exportRowCert.id } : undefined}
      />
    </>
  )
}
