/**
 * Operations (import, export, bulk actions), on the mockup's sectioned form (settingsView()): the
 * table of contents of the operations, then the one chosen in its frame. Import: smart import and
 * OPNsense (its connection test as a settings test); export: the downloads as records; bulk: the
 * resource as the mockup's state chips, the list as its tableView() with the selection bar.
 */
import { useState, useEffect, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { SmartImportModal } from '../components/SmartImport'
import {
  opnsenseService, casService, certificatesService,
  csrsService, templatesService, usersService
} from '../services'
import { REVOCATION_REASONS } from '../components/RevokeCertificateModal'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { formatDate, extractCN, downloadBlob, warnSkippedExport } from '../lib/utils'
import { soleImported } from '../lib/importResult'
import { bulkLocalOnlyRevocationWarning } from '../lib/revocationOutcome'
import { hiddenFromIssuance, listedForIssuance, signingCas, unlistedSigningCas } from '../lib/caSelection'
import { HiddenCasToggle } from '../components/cas/HiddenCasToggle'
import { useOpenEntity } from '../hooks/useOpenEntity'
import {
  Zone, PageHead, Btn, Icon, Pill, RecordList, RecordRow, StateFilters, TableView, SearchField, FilterSelect, BatchBar,
  TableFooter, EmptyBlock, AtelierDialog,
} from '../components/atelier'
import { SettingsLayout, SettingsToc, SettingsJump, SettingsFrame, SettingsGroup, SettingsTest } from '../components/atelier/SettingsView'
import { ConfirmModal, Input, NumberInput, Notice, SecretInput, Select, ToggleSwitch } from '../components/atelier/Form'
import { useSectionParam } from '../components/atelier/useSectionParam'
import { ROLE_KEYS } from './users/userFacts'

const STORAGE_KEY = 'opnsense_config'
const TYPE_KEY = 'ucm-ops-resource-type'
const TYPES = ['certificates', 'cas', 'csrs', 'templates', 'users']
// What each resource offers in bulk, and the fields its local search reads
const ACTIONS = {
  certificates: ['revoke', 'renew', 'export', 'delete'], cas: ['export', 'delete'], csrs: ['sign', 'delete'], templates: ['delete'], users: ['delete'],
}
const SEARCH_KEYS = ['cn', 'descr', 'name', 'subject', 'username', 'email', 'common_name']
const TYPE_ICONS = { certificates: 'cert', cas: 'shield', csrs: 'file', templates: 'template', users: 'users' }

const certName = (row, t) => row.cn || row.common_name || extractCN(row.subject) || row.descr || t('common.certificate')
const certStatus = (row) => (row.revoked ? 'revoked' : row.status || 'unknown')
const STATUS = {
  valid: ['good', 'common.valid'], expiring: ['warn', 'common.expiring'], expired: ['bad', 'common.expired'],
  revoked: ['bad', 'common.revoked'], unknown: ['muted', 'common.status'],
}

/** The columns of each resource: { id, label, cell, value (sort), grow, fit }. */
function useColumns(t) {
  return useMemo(() => {
    const status = (row) => { const [tone, key] = STATUS[certStatus(row)] || STATUS.unknown; return <Pill tone={tone} label={t(key)} /> }
    const date = (key) => (row) => formatDate(row[key])
    const name = (row) => row.descr || extractCN(row.subject) || '—'
    // Every column sorts the rows shown, as the former table did
    const sortable = (cols) => cols.map((c) => ({ ...c, sort: c.id }))
    const all = {
      certificates: [
        { id: 'cn', label: t('common.commonName'), grow: true, value: (r) => certName(r, t),
          cell: (r) => <span className="row-actions"><span>{certName(r, t)}</span>{r.has_private_key && <span title={t('common.hasKey')}><Icon name="key" /></span>}</span> },
        { id: 'status', label: t('common.status'), fit: true, value: certStatus, cell: status },
        { id: 'issuer', label: t('common.issuer'), value: (r) => extractCN(r.issuer) || r.issuer_name || '', cell: (r) => extractCN(r.issuer) || r.issuer_name || '—' },
        { id: 'valid_to', label: t('common.expires'), fit: true, value: (r) => r.valid_to || '', cell: date('valid_to') },
      ],
      cas: [
        { id: 'descr', label: t('common.name'), grow: true, value: name, cell: name },
        { id: 'subject', label: t('common.subject'), value: (r) => extractCN(r.subject) || r.subject || '', cell: (r) => extractCN(r.subject) || r.subject || '—' },
        { id: 'valid_to', label: t('common.expires'), fit: true, value: (r) => r.valid_to || '', cell: date('valid_to') },
      ],
      csrs: [
        { id: 'descr', label: t('common.name'), grow: true, value: name, cell: name },
        { id: 'subject', label: t('common.subject'), value: (r) => extractCN(r.subject) || r.subject || '', cell: (r) => extractCN(r.subject) || r.subject || '—' },
        { id: 'created_at', label: t('common.created'), fit: true, value: (r) => r.created_at || '', cell: date('created_at') },
      ],
      templates: [
        { id: 'name', label: t('common.name'), grow: true, value: (r) => r.name || '', cell: (r) => r.name || '—' },
        { id: 'key_type', label: t('common.keyType'), fit: true, value: (r) => r.key_type || '', cell: (r) => r.key_type || '—' },
        { id: 'validity_days', label: t('common.validity'), fit: true, value: (r) => Number(r.validity_days) || 0,
          cell: (r) => (r.validity_days ? `${r.validity_days} ${t('common.days')}` : '—') },
      ],
      users: [
        { id: 'username', label: t('common.user'), grow: true, value: (r) => r.username || '', cell: (r) => r.username || '—' },
        { id: 'email', label: t('common.email'), value: (r) => r.email || '', cell: (r) => r.email || '—' },
        { id: 'role', label: t('common.role'), fit: true, value: (r) => r.role || '', cell: (r) => t(ROLE_KEYS[r.role] || ROLE_KEYS.viewer) },
        { id: 'active', label: t('common.status'), fit: true, value: (r) => (r.active ? 1 : 0),
          cell: (r) => <Pill tone={r.active ? 'good' : 'warn'} label={r.active ? t('common.active') : t('common.disabled')} /> },
      ],
    }
    return Object.fromEntries(Object.entries(all).map(([type, cols]) => [type, sortable(cols)]))
  }, [t])
}

/** A record's name, in the labels of its checkbox and on its phone card. */
function rowName(type, row, t) {
  if (type === 'certificates') return certName(row, t)
  if (type === 'users') return row.username || '—'
  if (type === 'templates') return row.name || '—'
  return row.descr || extractCN(row.subject) || '—'
}

export default function OperationsPage() {
  const { t } = useTranslation()
  const { showSuccess, showError, showWarning, showInfo } = useNotification()
  const { isAdmin } = usePermission()
  const openEntity = useOpenEntity()
  const COLUMNS = useColumns(t)

  const TABS = [
    { id: 'import', label: t('common.import'), description: t('operations.importHeaderDesc'), icon: 'upload' },
    { id: 'export', label: t('common.export'), description: t('operations.exportHeaderDesc'), icon: 'download' },
    { id: 'bulk', label: t('operations.bulkActions'), description: t('operations.bulkHeaderDesc'), icon: 'layers' },
  ]
  // The operation a link names (/operations?tab=bulk) is the one shown
  const [activeTab, setActiveTab] = useSectionParam(['import', 'export', 'bulk'], 'import')

  const [smartImport, setSmartImport] = useState(false)
  const [processing, setProcessing] = useState(false)
  const [cas, setCas] = useState([])
  const [opnsenseHost, setOpnsenseHost] = useState('')
  const [opnsensePort, setOpnsensePort] = useState('443')
  const [opnsenseApiKey, setOpnsenseApiKey] = useState('')
  const [opnsenseApiSecret, setOpnsenseApiSecret] = useState('')
  // Verify TLS by default — matches the backend default (#248). The UI used
  // to start with verification OFF, which silently overrode the backend's
  // secure default because the request body always carries the key.
  const [opnsenseVerifySsl, setOpnsenseVerifySsl] = useState(true)
  const [testResult, setTestResult] = useState(null)
  const [testItems, setTestItems] = useState([])

  const [bulkResourceType, setBulkResourceType] = useState(() => {
    try { const kept = localStorage.getItem(TYPE_KEY); return TYPES.includes(kept) ? kept : 'certificates' } catch { return 'certificates' }
  })
  const [bulkData, setBulkData] = useState([])
  const [bulkLoading, setBulkLoading] = useState(false)
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [bulkAction, setBulkAction] = useState(null)
  const [bulkRevokeReason, setBulkRevokeReason] = useState('unspecified')  // RFC 5280 reason (#334)
  const [bulkRevokeRelated, setBulkRevokeRelated] = useState(true)  // other member of a hybrid pair
  const [partnersLoading, setPartnersLoading] = useState(false)
  const [bulkProcessing, setBulkProcessing] = useState(false)
  const [bulkSignCaId, setBulkSignCaId] = useState('')
  const [showHiddenCas, setShowHiddenCas] = useState(false)
  // Each bulk dialog starts with the hidden CAs hidden again
  useEffect(() => { setShowHiddenCas(false) }, [bulkAction])
  const [bulkSignDays, setBulkSignDays] = useState('365')
  const [statusFilter, setStatusFilter] = useState('')
  const [caFilter, setCaFilter] = useState('')
  // The selection alone (the former basket): every ticked item, from any page
  const [selectionOnly, setSelectionOnly] = useState(false)
  const [resourceCounts, setResourceCounts] = useState({})
  const [bulkSearch, setBulkSearch] = useState('')
  const [bulkPage, setBulkPage] = useState(1)
  const [bulkPerPage, setBulkPerPage] = useState(25)
  const [bulkTotal, setBulkTotal] = useState(0)
  const [sort, setSort] = useState(null)
  // Items selected on other pages, kept so the selection view can still render
  // them after the page they were loaded with is replaced
  const seenItemsRef = useRef(new Map())

  // Certificates and CSRs are paginated server-side (default per_page=20), so
  // the full inventory is fetched page by page with server-side search/filters
  // (#294). CAs, templates and users return complete lists.
  const serverPaged = bulkResourceType === 'certificates' || bulkResourceType === 'csrs'

  // Load on mount
  useEffect(() => {
    try {
      const saved = sessionStorage.getItem(STORAGE_KEY)
      if (saved) {
        const config = JSON.parse(saved)
        setOpnsenseHost(config.host || '')
        setOpnsensePort(config.port || '443')
        setOpnsenseApiKey(config.api_key || '')
        setOpnsenseApiSecret(config.api_secret || '')
        // Only an explicitly saved `false` opts out of verification; a saved
        // config from before the key existed must not re-disable it
        // (`config.verify_ssl || false` did exactly that).
        setOpnsenseVerifySsl(config.verify_ssl !== false)
      }
    } catch { /* non-critical */ }
    loadCAs()
  }, [])

  // Server-side query inputs — the key is constant for client-paged resource
  // types so their full-list fetch only re-runs on type/tab changes
  const bulkQueryKey = serverPaged
    ? [bulkPage, bulkPerPage, bulkSearch, statusFilter, caFilter].join('|')
    : ''

  // Load bulk data when resource type or the server-side query changes
  useEffect(() => {
    if (activeTab === 'bulk') loadBulkData()
  }, [bulkResourceType, activeTab, bulkQueryKey])

  // Load resource counts when bulk tab becomes active
  useEffect(() => {
    if (activeTab === 'bulk') {
      Promise.allSettled([
        certificatesService.getAll({ per_page: 1 }),
        casService.getAll(),
        csrsService.getAll({ per_page: 1 }),
        templatesService.getAll(),
        usersService.getAll(),
      ]).then(([certs, cas, csrs, templates, users]) => {
        // Paginated endpoints report the inventory size in meta.total —
        // data.length is just the first page (#294)
        setResourceCounts({
          certificates: certs.status === 'fulfilled' ? (certs.value.meta?.total ?? certs.value.data?.length ?? 0) : 0,
          cas: cas.status === 'fulfilled' ? (cas.value.data?.length || 0) : 0,
          csrs: csrs.status === 'fulfilled' ? (csrs.value.meta?.total ?? csrs.value.data?.length ?? 0) : 0,
          templates: templates.status === 'fulfilled' ? (templates.value.data?.length || 0) : 0,
          users: users.status === 'fulfilled' ? (users.value.data?.length || 0) : 0,
        })
      })
    }
  }, [activeTab])

  const loadCAs = async () => {
    try {
      const response = await casService.getAll()
      setCas(response.data || [])
    } catch { /* non-critical */ }
  }

  const loadBulkData = async () => {
    setBulkLoading(true)
    try {
      let response
      switch (bulkResourceType) {
        case 'certificates': {
          const params = { page: bulkPage, per_page: bulkPerPage }
          if (bulkSearch) params.search = bulkSearch
          if (statusFilter) params.status = statusFilter
          if (caFilter) params.ca_id = caFilter
          response = await certificatesService.getAll(params)
          break
        }
        case 'cas':
          response = await casService.getAll()
          break
        case 'csrs': {
          const params = { page: bulkPage, per_page: bulkPerPage }
          if (bulkSearch) params.search = bulkSearch
          response = await csrsService.getAll(params)
          break
        }
        case 'templates':
          response = await templatesService.getAll()
          break
        case 'users':
          response = await usersService.getAll()
          break
      }
      const items = response?.data || []
      setBulkData(items)
      setBulkTotal(response?.meta?.total ?? items.length)
      items.forEach(item => { if (item?.id != null) seenItemsRef.current.set(item.id, item) })
    } catch (e) {
      showError(t('operations.loadFailed', 'Failed to load data'))
    } finally {
      setBulkLoading(false)
    }
  }

  // ===== IMPORT HANDLERS (from ImportExportPage) =====
  const saveOpnsenseConfig = () => {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
        host: opnsenseHost, port: opnsensePort,
        api_key: opnsenseApiKey, api_secret: opnsenseApiSecret,
        verify_ssl: opnsenseVerifySsl
      }))
      showSuccess(t('importExport.opnsense.configSaved'))
    } catch { /* non-critical */ }
  }

  const opnsenseTestButton = useRef(null)
  const handleTestConf = async () => {
    setProcessing(true)
    setTestResult(null)
    setTestItems([])
    try {
      const result = await opnsenseService.test({
        host: opnsenseHost, port: opnsensePort,
        api_key: opnsenseApiKey, api_secret: opnsenseApiSecret,
        verify_ssl: opnsenseVerifySsl
      })
      setTestResult({ success: true, stats: result.stats })
      setTestItems((result.items || []).map(item => ({ ...item, selected: true })))
      saveOpnsenseConfig()
    } catch (error) {
      setTestResult({ success: false, error: error.message })
      showError(error.message || t('importExport.opnsense.connectionFailed'))
    } finally {
      setProcessing(false)
      // The button was disabled during the test: the focus goes back to it, as in the mockup
      requestAnimationFrame(() => opnsenseTestButton.current?.focus())
    }
  }

  const toggleItemSelection = (id) => {
    setTestItems(prev => prev.map(item => 
      item.id === id ? { ...item, selected: !item.selected } : item
    ))
  }

  const toggleAllItems = (selected) => {
    setTestItems(prev => prev.map(item => ({ ...item, selected })))
  }

  const handleImportFromOpnsense = async () => {
    const selectedItems = testItems.filter(i => i.selected).map(i => i.id)
    if (selectedItems.length === 0) {
      showError(t('importExport.opnsense.noItemsSelected'))
      return
    }
    setProcessing(true)
    try {
      const result = await opnsenseService.import({
        host: opnsenseHost, port: opnsensePort,
        api_key: opnsenseApiKey, api_secret: opnsenseApiSecret,
        verify_ssl: opnsenseVerifySsl,
        items: selectedItems
      })
      const imported = (result.imported?.cas || 0) + (result.imported?.certificates || 0)
      showSuccess(t('importExport.opnsense.importSuccess', { count: imported, skipped: result.skipped || 0 }))
      for (const p of result.unverifiable_parents || []) {
        showWarning(t('import.unverifiableParent', { ca: p.ca_name, parent: p.candidate?.name, algorithm: p.algorithm }))
      }
      setTestResult(null)
      setTestItems([])
      loadCAs()
    } catch (error) {
      showError(error.message || t('common.importFailed'))
    } finally {
      setProcessing(false)
    }
  }

  const handleImportComplete = (result) => {
    const sole = soleImported(result)
    if (sole) openEntity(sole.type, sole.id)
  }

  // ===== EXPORT HANDLERS =====
  const handleExport = async (service, format, filename) => {
    try {
      const blob = await service(format)
      const ext = { pem: 'pem', pkcs7: 'p7b', p7b: 'p7b' }[format] || format
      downloadBlob(blob, `${filename}.${ext}`)
      showSuccess(t('importExport.export.certificatesExported'))
      warnSkippedExport(blob, t, showWarning)
    } catch (error) {
      showError(error.message || t('importExport.export.exportFailed'))
    }
  }

  // ===== BULK ACTION HANDLERS =====
  const relatedOf = (id) => seenItemsRef.current.get(id)?.related_certificate_id
  // The other member the server revokes or renews with id: it names id back and is not
  // revoked or superseded. null when there is none, undefined when it could not be read.
  const livePartner = (id) => {
    const other = relatedOf(id)
    if (other == null) return null
    const item = seenItemsRef.current.get(other)
    if (!item) return undefined
    return item.related_certificate_id === id && !item.revoked && !item.archived ? other : null
  }
  const pairAction = bulkResourceType === 'certificates' && (bulkAction === 'revoke' || bulkAction === 'renew')
  const selectionHasPairs = bulkResourceType === 'certificates'
    && [...selectedIds].some(id => livePartner(id) !== null)
  // A fresh choice for every bulk revocation
  useEffect(() => { if (bulkAction === 'revoke') setBulkRevokeRelated(true) }, [bulkAction])
  // Other members off the loaded pages are read before the dialog asks or reports about them
  useEffect(() => {
    if (!pairAction) return undefined
    const missing = [...new Set([...selectedIds].map(relatedOf))]
      .filter(other => other != null && !seenItemsRef.current.has(other))
    if (!missing.length) return undefined
    let live = true
    setPartnersLoading(true)
    Promise.allSettled(missing.map(other => certificatesService.getById(other))).then(results => {
      results.forEach(r => {
        const item = r.status === 'fulfilled' ? (r.value?.data ?? r.value) : null
        if (item?.id != null) seenItemsRef.current.set(item.id, item)
      })
      if (live) setPartnersLoading(false)
    })
    return () => { live = false; setPartnersLoading(false) }
  }, [pairAction, selectedIds])

  const executeBulkAction = async () => {
    if (selectedIds.size === 0 || partnersLoading) return
    setBulkProcessing(true)
    const ids = Array.from(selectedIds)
    // Read before the request: a refresh during it would show the partners already revoked
    const partnerBefore = new Map(pairAction ? ids.map(id => [id, livePartner(id)]) : [])
    try {
      let result
      switch (`${bulkResourceType}:${bulkAction}`) {
        case 'certificates:revoke':
          result = await certificatesService.bulkRevoke(ids, bulkRevokeReason, {
            relatedOf, ...(selectionHasPairs && { revokeRelated: bulkRevokeRelated }),
          })
          break
        case 'certificates:renew':
          result = await certificatesService.bulkRenew(ids, { relatedOf })
          break
        case 'certificates:delete':
          result = await certificatesService.bulkDelete(ids)
          break
        case 'cas:delete':
          result = await casService.bulkDelete(ids)
          break
        case 'csrs:sign':
          if (!bulkSignCaId) { showError(t('operations.selectCA')); setBulkProcessing(false); return }
          result = await csrsService.bulkSign(ids, parseInt(bulkSignCaId), parseInt(bulkSignDays))
          break
        case 'csrs:delete':
          result = await csrsService.bulkDelete(ids)
          break
        case 'templates:delete':
          result = await templatesService.bulkDelete(ids)
          break
        case 'users:delete':
          result = await usersService.bulkDelete(ids)
          break
      }
      const data = result?.data
      const successCount = data?.success?.length || 0
      const failedCount = data?.failed?.length || 0
      showSuccess(t('operations.bulkSuccess', { action: bulkAction, count: successCount }))
      if (failedCount > 0) {
        showError(t('operations.bulkPartialFail', {
          count: failedCount,
          defaultValue: `${failedCount} items failed`
        }))
      }
      // Other members of pairs revoked or renewed outside the selection, which the answer omits
      const notRevoked = data?.related_not_revoked || []
      const pairedOutside = new Set((data?.success || [])
        .map(id => partnerBefore.get(id))
        .filter(other => other != null && !selectedIds.has(other) && !notRevoked.includes(other)))
      // Deleting users revokes their certificates too: the same CA-not-told warning
      const revokes = bulkAction === 'revoke' || (bulkAction === 'delete' && bulkResourceType === 'users')
      const localOnly = revokes
        ? bulkLocalOnlyRevocationWarning(data, t, bulkAction === 'revoke' ? bulkRevokeReason : undefined) : null
      if (localOnly) showWarning(localOnly)
      // Users deleted whose mTLS certificates could not be revoked: those stay valid
      if (bulkAction === 'delete' && data?.unrevoked?.length > 0 && result?.message) showWarning(result.message)
      if (notRevoked.length > 0) {
        showWarning(t('revocation.bulkRelatedRevokeFailed', { count: notRevoked.length, ids: notRevoked.map(id => `#${id}`).join(', ') }))
      }
      if (pairedOutside.size > 0 && bulkAction === 'revoke' && !(selectionHasPairs && !bulkRevokeRelated)) {
        showWarning(t('revocation.bulkRelatedRevoked', { count: pairedOutside.size }))
      }
      if (pairedOutside.size > 0 && bulkAction === 'renew') {
        showInfo(t('certificates.hybrid.bulkRelatedRenewed', { count: pairedOutside.size }))
      }
      // What the server decided on other terms than asked, per renewed certificate
      for (const entry of data?.notices || []) {
        for (const notice of entry?.notices || []) showWarning(`#${entry.id}: ${notice}`)
      }
      const pendingCount = data?.pending_approval?.length || 0
      if (pendingCount > 0) {
        showWarning(t('operations.bulkPendingApproval', {
          count: pendingCount,
          defaultValue: `${pendingCount} items submitted for approval`
        }))
      }
      setBulkAction(null)
      setSelectedIds(new Set())
      loadBulkData()
    } catch (error) {
      showError(error.message || t('operations.bulkFailed', 'Bulk operation failed'))
    } finally {
      setBulkProcessing(false)
    }
  }

  // Status/CA filters for certificates are applied server-side (#294); other
  // resource types have no filters, so the loaded data is used as-is.
  // The basket view additionally keeps items selected on other pages visible.
  const basketItems = useMemo(() => {
    if (!serverPaged || selectedIds.size === 0) return bulkData
    const loaded = new Set(bulkData.map(item => item.id))
    const offPage = [...selectedIds]
      .filter(id => !loaded.has(id))
      .map(id => seenItemsRef.current.get(id))
      .filter(Boolean)
    return offPage.length ? [...bulkData, ...offPage] : bulkData
  }, [bulkData, selectedIds, serverPaged])

  // Confirm modal content
  const getConfirmMessage = () => {
    const count = selectedIds.size
    const actionLabels = {
      revoke: t('operations.confirmRevoke', { count, defaultValue: `Revoke ${count} certificate(s)? This cannot be undone.` }),
      renew: t('operations.confirmRenew', { count, defaultValue: `Renew ${count} certificate(s)? New keys will be generated.` }),
      delete: t('operations.confirmDelete', { count, defaultValue: `Delete ${count} item(s)? This cannot be undone.` }),
      export: t('operations.confirmExport', { count, defaultValue: `Export ${count} item(s)?` }),
      sign: t('operations.confirmSign', { count, defaultValue: `Sign ${count} CSR(s)?` }),
    }
    return actionLabels[bulkAction] || ''
  }

  const chooseType = (type) => {
    setBulkResourceType(type)
    try { localStorage.setItem(TYPE_KEY, type) } catch { /* private mode */ }
    setStatusFilter(''); setCaFilter(''); setSelectedIds(new Set()); setBulkSearch(''); setBulkPage(1); setSort(null); setSelectionOnly(false)
    seenItemsRef.current.clear()
  }

  const exportSelection = async () => {
    const ids = Array.from(selectedIds)
    if (!ids.length) return
    try {
      const service = bulkResourceType === 'certificates' ? certificatesService : casService
      const blob = await service.bulkExport(ids, 'pem')
      if (blob) downloadBlob(blob, `${bulkResourceType}_export.pem`)
      showSuccess(t('operations.bulkSuccess', { action: 'export', count: blob?.exportedCount ?? ids.length }))
      warnSkippedExport(blob, t, showWarning)
    } catch (e) { showError(e.message || t('importExport.export.exportFailed')) }
  }

  // ===== IMPORT =====
  const ticked = testItems.filter(i => i.selected).length
  const renderImportTab = () => (
    <>
      <SettingsGroup legend={t('importExport.smartImport.title')} hint={t('importExport.smartImport.description')} grid={false}>
        <div className="settings-actions">
          <Btn tone="primary" icon="upload" id="ops-smart-import" onClick={() => setSmartImport(true)}>{t('operations.openSmartImport')}</Btn>
        </div>
      </SettingsGroup>
      <SettingsGroup legend={t('importExport.opnsense.title')} hint={t('importExport.opnsense.description')} grid={false}>
        <form onSubmit={(e) => e.preventDefault()} noValidate className="settings-stack">
          <div className="settings-grid">
            <Input id="ops-opnsense-host" label={t('importExport.opnsense.hostLabel')} value={opnsenseHost} onChange={(e) => setOpnsenseHost(e.target.value)}
              placeholder={t('importExport.opnsense.hostPlaceholder')} />
            <NumberInput id="ops-opnsense-port" label={t('common.portLabel')} value={opnsensePort} onChange={(e) => setOpnsensePort(e.target.value)}
              placeholder={t('common.portPlaceholder')} />
            <Input id="ops-opnsense-key" label={t('importExport.opnsense.apiKeyLabel')} value={opnsenseApiKey} onChange={(e) => setOpnsenseApiKey(e.target.value)} />
            <SecretInput id="ops-opnsense-secret" label={t('importExport.opnsense.apiSecretLabel')} value={opnsenseApiSecret}
              onChange={(e) => setOpnsenseApiSecret(e.target.value)} />
            <ToggleSwitch id="ops-opnsense-ignore" checked={!opnsenseVerifySsl} onChange={(ignore) => setOpnsenseVerifySsl(!ignore)}
              label={t('importExport.opnsense.ignoreCert')} />
            {!opnsenseVerifySsl && <Notice tone="warn">{t('importExport.opnsense.sslWarning')}</Notice>}
          </div>
          {/* The test as the mockup's test zone: the button, then its result on the line */}
          <SettingsTest id="opnsense" icon="plug" label={processing ? t('common.testing') : t('common.testConnection')} buttonRef={opnsenseTestButton}
            write={false} busy={processing || !opnsenseHost || !opnsenseApiKey || !opnsenseApiSecret} onTest={handleTestConf}
            hint={t('importExport.opnsense.testHint')}
            result={testResult && {
              ok: testResult.success,
              text: testResult.success
                ? (testResult.stats
                  ? t('importExport.opnsense.connectedWithCounts', { cas: testResult.stats.cas, certificates: testResult.stats.certificates })
                  : t('importExport.opnsense.connectedSuccessfully'))
                : (testResult.error || t('importExport.opnsense.connectionFailed')),
            }} />
          {testResult?.success && testItems.length > 0 && (
            <>
              <ToggleSwitch id="ops-opnsense-all" checked={testItems.every(i => i.selected)} onChange={(on) => toggleAllItems(on)}
                label={`${t('importExport.opnsense.selectAll')} (${ticked}/${testItems.length})`} />
              <div className="columns-list compare-scroll" role="group" aria-label={t('importExport.opnsense.foundItems')}>
                {testItems.map(item => (
                  <label key={item.id} className="checkbox-line">
                    <input type="checkbox" checked={item.selected} onChange={() => toggleItemSelection(item.id)} />
                    {item.name || t('common.unnamed')}{' '}
                    <Pill tone="muted" icon={item.type === 'CA' ? 'shield' : 'cert'} label={item.type === 'CA' ? t('common.ca') : t('common.certificate')} />
                  </label>
                ))}
              </div>
              <div className="settings-actions">
                <Btn tone="primary" icon="upload" onClick={handleImportFromOpnsense} disabled={processing || !ticked || undefined}>
                  {t('importExport.opnsense.importSelected', { count: ticked })}
                </Btn>
              </div>
            </>
          )}
        </form>
      </SettingsGroup>
    </>
  )

  // ===== EXPORT: each download as a record of the mockup's list =====
  const exportRow = (key, label, desc, onClick) => (
    <RecordRow key={key} title={label} meta={desc}
      action={<Btn icon="download" write={false} onClick={onClick} aria-label={`${t('common.download')} ${label}`}>{t('common.download')}</Btn>} />
  )
  const renderExportTab = () => (
    <>
      <SettingsGroup legend={t('importExport.export.allCertsTitle')} hint={t('importExport.export.allCertsDesc')} grid={false}>
        <RecordList>
          {exportRow('cert-pem', t('importExport.export.pemBundle'), t('importExport.export.pemDesc'),
            () => handleExport(certificatesService.exportAll, 'pem', 'certificates'))}
          {exportRow('cert-p7b', t('importExport.export.p7bBundle'), t('importExport.export.p7bDesc'),
            () => handleExport(certificatesService.exportAll, 'pkcs7', 'certificates'))}
        </RecordList>
      </SettingsGroup>
      <SettingsGroup legend={t('importExport.export.allCAsTitle')} hint={t('importExport.export.allCAsDesc', { count: cas.length })} grid={false}>
        <RecordList>
          {exportRow('ca-pem', t('importExport.export.pemBundle'), t('importExport.export.pemDesc'),
            () => handleExport(casService.exportAll, 'pem', 'ca-certificates'))}
          {exportRow('ca-p7b', t('importExport.export.p7bBundle'), t('importExport.export.p7bDesc'),
            () => handleExport(casService.exportAll, 'pkcs7', 'ca-certificates'))}
        </RecordList>
      </SettingsGroup>
    </>
  )

  // ===== BULK =====
  const columns = COLUMNS[bulkResourceType]
  const actions = ACTIONS[bulkResourceType]
  // CAs, templates and users come whole: searched, sorted and paged here; certificates and CSRs by the server
  const searched = serverPaged || !bulkSearch ? bulkData : bulkData.filter((row) => SEARCH_KEYS.some((k) => String(row[k] ?? '').toLowerCase().includes(bulkSearch.toLowerCase())))
  const listed = selectionOnly ? basketItems.filter((row) => selectedIds.has(row.id)) : searched
  const sortCol = sort && columns.find((c) => c.id === sort.key)
  const sorted = sortCol ? [...listed].sort((a, b) => {
    const x = sortCol.value(a); const y = sortCol.value(b)
    const order = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y))
    return sort.asc ? order : -order
  }) : listed
  const localPages = !serverPaged && !selectionOnly
  const total = selectionOnly ? sorted.length : serverPaged ? bulkTotal : sorted.length
  const pages = Math.max(1, Math.ceil(total / bulkPerPage))
  const rows = localPages ? sorted.slice((bulkPage - 1) * bulkPerPage, bulkPage * bulkPerPage) : sorted
  const start = total ? (selectionOnly ? 1 : (bulkPage - 1) * bulkPerPage + 1) : 0
  const end = selectionOnly ? total : Math.min(total, start + rows.length - 1)
  const toggle = (id) => setSelectedIds((prev) => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next })
  const togglePage = (on) => setSelectedIds((prev) => { const next = new Set(prev); rows.forEach((r) => (on ? next.add(r.id) : next.delete(r.id))); return next })
  const n = selectedIds.size

  const renderBulkTab = () => (
    <>
      <StateFilters label={t('operations.selectResource')} active={bulkResourceType} onChange={chooseType}
        views={TYPES.map((type) => ({ id: type, label: t(`common.${type}Short`), count: resourceCounts[type] }))} />
      <TableView label={t('operations.bulkListLabel')} tableLabel={t('operations.bulkTableLabel')} kind="module" scrollId="ops-scroll"
        storageKey="ucm-operations" density
        search={<>
          <SearchField id="ops-search" label={t('common.search')} placeholder={t('common.search')} value={bulkSearch}
            onChange={(v) => { setBulkSearch(v); setBulkPage(1) }} />
          {bulkResourceType === 'certificates' && (
            <>
              <FilterSelect id="ops-status" label={t('common.status')} value={statusFilter} onChange={(v) => { setStatusFilter(v); setBulkPage(1) }}
                options={[
                  { value: '', label: t('common.allStatuses') },
                  { value: 'valid', label: t('common.valid') },
                  { value: 'expired', label: t('common.expired') },
                  { value: 'revoked', label: t('common.revoked') },
                ]} />
              <FilterSelect id="ops-ca" label={t('common.certificateAuthority')} value={caFilter} onChange={(v) => { setCaFilter(v); setBulkPage(1) }}
                options={[{ value: '', label: t('common.allCAs') }, ...cas.map(ca => ({ value: String(ca.id), label: ca.descr || ca.subject || `CA #${ca.id}` }))]} />
            </>
          )}
        </>}
        tools={(
          <button type="button" className="btn" id="ops-selection-only" aria-pressed={selectionOnly} disabled={(!n && !selectionOnly) || undefined}
            onClick={() => setSelectionOnly((v) => !v)}>
            <Icon name="check" />{t('operations.selectionOnly', { count: n })}
          </button>
        )}
        batch={n > 0 && isAdmin() && (
          // Every bulk route here is admin-only, and so is the page: the bar keeps the same check
          <BatchBar count={t('table.selectedCount', { count: n })} onClear={() => { setSelectedIds(new Set()); setSelectionOnly(false) }}>
            {actions.includes('revoke') && <Btn tone="danger" icon="block" onClick={() => setBulkAction('revoke')}>{t('common.revoke')}</Btn>}
            {actions.includes('renew') && <Btn write icon="refresh" onClick={() => setBulkAction('renew')}>{t('common.renew')}</Btn>}
            {actions.includes('sign') && <Btn write icon="stamp" onClick={() => setBulkAction('sign')}>{t('common.sign')}</Btn>}
            {actions.includes('export') && <Btn icon="download" onClick={exportSelection}>{t('operations.exportPem')}</Btn>}
            {actions.includes('delete') && <Btn tone="danger" icon="close" onClick={() => setBulkAction('delete')}>{t('common.delete')}</Btn>}
          </BatchBar>
        )}
        columns={columns} rows={rows} rowKey={(r) => r.id} rowLabel={(r) => rowName(bulkResourceType, r, t)}
        selection={{ selected: selectedIds, onToggle: toggle, onTogglePage: togglePage }}
        sort={sort} onSort={(key) => setSort((prev) => (prev?.key === key ? { key, asc: !prev.asc } : { key, asc: true }))}
        loading={bulkLoading}
        card={(r) => ({ description: columns[1]?.cell(r), meta: columns.slice(2).map((c) => c.cell(r)) })}
        empty={<EmptyBlock id="operations" icon={TYPE_ICONS[bulkResourceType]} title={t('operations.noData')} text={t('operations.noDataDesc')} />}
        footer={(
          <TableFooter range={total ? t('table.range', { start, end, total }) : ''}
            pagination={selectionOnly ? undefined : { page: bulkPage, pages, perPage: bulkPerPage, jump: serverPaged, onPage: setBulkPage, onPerPage: (v) => { setBulkPerPage(v); setBulkPage(1) } }} />
        )} />
    </>
  )

  const content = { import: renderImportTab, export: renderExportTab, bulk: renderBulkTab }
  const active = TABS.find(tab => tab.id === activeTab)
  const closeAction = () => { setBulkAction(null); setBulkRevokeReason('unspecified') }
  const unlisted = unlistedSigningCas(cas)
  const hidden = hiddenFromIssuance(signingCas(cas), bulkSignCaId)

  const dialogs = (
    <>
      {bulkAction === 'revoke' && (
        <AtelierDialog title={t('operations.confirmBulk')} size="narrow" onClose={closeAction} testId="ops-revoke">
          <p>{getConfirmMessage()}</p>
          <div className="form-fields">
            <Select id="ops-revoke-reason" full label={t('revocation.reasonLabel')} value={bulkRevokeReason} onChange={setBulkRevokeReason}
              hint={`${t(`revocation.hints.${bulkRevokeReason}`)} ${t('revocation.bulkReasonHelp')}`}
              options={REVOCATION_REASONS.map(r => ({ value: r, label: t(`revocation.reasons.${r}`) }))} />
            {selectionHasPairs && (
              <ToggleSwitch id="bulk-revoke-related" checked={bulkRevokeRelated} onChange={setBulkRevokeRelated}
                label={t('revocation.revokeRelatedBulk')} description={t('revocation.revokeRelatedBulkHint')} />
            )}
          </div>
          <div className="modal-actions">
            <button type="button" className="btn" data-action="close-modal" disabled={bulkProcessing || undefined} onClick={closeAction}>{t('common.cancel')}</button>
            <Btn tone="danger" icon="block" disabled={bulkProcessing || partnersLoading || undefined} onClick={executeBulkAction}>{t('common.revoke')}</Btn>
          </div>
        </AtelierDialog>
      )}
      <ConfirmModal open={bulkAction === 'renew' || bulkAction === 'delete'} onClose={closeAction} onConfirm={executeBulkAction}
        title={t('operations.confirmBulk')} message={getConfirmMessage()}
        confirmLabel={bulkAction === 'delete' ? t('common.delete') : t('common.renew')}
        variant={bulkAction === 'delete' ? 'danger' : 'primary'} loading={bulkProcessing || partnersLoading} />
      {bulkAction === 'sign' && (
        <AtelierDialog title={t('operations.signCSRs', { count: n })} size="narrow" onClose={closeAction} testId="ops-sign">
          <p>{t('operations.selectCAForSign')}</p>
          <div className="form-fields">
            <Select id="ops-sign-ca" full label={t('common.certificateAuthority')} value={bulkSignCaId} onChange={setBulkSignCaId} placeholder={t('common.selectCA')}
              options={listedForIssuance(signingCas(cas), showHiddenCas, bulkSignCaId).map(ca => ({ value: String(ca.id), label: ca.descr || ca.subject }))}
              hint={(unlisted > 0 || hidden > 0) && <>
                {unlisted > 0 && t('cas.notListedForSigning', { count: unlisted })}{' '}
                <HiddenCasToggle count={hidden} shown={showHiddenCas} onToggle={() => setShowHiddenCas(v => !v)} />
              </>} />
            <NumberInput id="ops-sign-days" label={t('account.mtlsValidityDays')} value={bulkSignDays} onChange={(e) => setBulkSignDays(e.target.value)} />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn" data-action="close-modal" disabled={bulkProcessing || undefined} onClick={closeAction}>{t('common.cancel')}</button>
            <Btn tone="primary" icon="stamp" disabled={bulkProcessing || undefined} onClick={executeBulkAction}>{t('common.sign')}</Btn>
          </div>
        </AtelierDialog>
      )}
    </>
  )

  // One operation at a time in its frame; import and export keep their own actions, no save bar
  return (
    <>
      <Zone testId="operations-page" after={dialogs}>
        <PageHead title={t('operations.title')} total={t('sectioned.sectionCount', { count: TABS.length })} intent={t('shell.moduleDesc.operations')} />
        <SettingsLayout
          toc={<SettingsToc label={t('operations.tocLabel')} sections={TABS} current={activeTab}
            hrefFor={(id) => (id === 'import' ? '/operations' : `/operations?tab=${id}`)} onJump={setActiveTab} />}
        >
          <SettingsJump sections={TABS} current={activeTab} onJump={setActiveTab} />
          <SettingsFrame id={active.id} label={active.label} desc={active.description}>{content[activeTab]()}</SettingsFrame>
        </SettingsLayout>
      </Zone>
      <SmartImportModal isOpen={smartImport} onClose={() => setSmartImport(false)}
        onImportComplete={(result) => { setSmartImport(false); handleImportComplete(result) }} />
    </>
  )
}
