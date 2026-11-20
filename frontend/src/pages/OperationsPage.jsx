/**
 * Operations Page - Import, Export & Bulk Actions
 * Replaces ImportExportPage with unified operations center
 */
import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { 
  UploadSimple, DownloadSimple, Lightning,
  CheckCircle, XCircle, Clock, X, Certificate, ShieldCheck, Trash, 
  ArrowsClockwise, Prohibit, PencilSimple, FileText, User, Crown, Info,
  Table, ShoppingCart, CaretDown, MagnifyingGlass, WarningCircle, Question, PlugsConnected
} from '@phosphor-icons/react'
import { 
  ResponsiveLayout, ResponsiveDataTable, Button, Input, 
  ConfirmModal, Badge, KeyIndicator, TransferPanel
} from '../components'
import { HelpCard } from '../components/HelpCard'
import { ToggleSwitch } from '../components/ui/ToggleSwitch'
import { SmartImportWidget } from '../components/SmartImport'
import { 
  opnsenseService, casService, certificatesService, 
  csrsService, templatesService, usersService 
} from '../services'
import { REVOCATION_REASONS } from '../components/RevokeCertificateModal'
import { useNotification, useMobile } from '../contexts'
import { usePermission } from '../hooks'
import { formatDate, extractCN, cn, downloadBlob, warnSkippedExport } from '../lib/utils'
import { soleImported } from '../lib/importResult'
import { bulkLocalOnlyRevocationWarning } from '../lib/revocationOutcome'
import { hiddenFromIssuance, listedForIssuance, signingCas, unlistedSigningCas } from '../lib/caSelection'
import { HiddenCasToggle } from '../components/cas/HiddenCasToggle'
import { useOpenEntity } from '../hooks/useOpenEntity'
import { FormLayout, SectionToc, SectionJump, FormSection, FormGroup, useSectionParam } from '../components/sectioned'

const STORAGE_KEY = 'opnsense_config'

// Resource type definitions - built inside component to use t() for translations
function useResourceTypes(t) {
  return useMemo(() => ({
    certificates: {
      icon: Certificate,
      color: 'icon-bg-teal',
      actions: ['revoke', 'renew', 'delete', 'export'],
      columns: [
        {
          key: 'cn',
          header: t('common.commonName'),
          sortable: true, priority: 1,
          render: (val, row) => {
            const name = val || row.common_name || extractCN(row.subject) || row.descr || t('common.certificate')
            return (
              <div className="flex items-center gap-2">
                <span className="font-medium truncate">{name}</span>
                <KeyIndicator hasKey={row.has_private_key} size={14} />
              </div>
            )
          }
        },
        {
          key: 'status',
          header: t('common.status'),
          priority: 2, sortable: true, hideOnMobile: true,
          render: (val, row) => {
            const isRevoked = row.revoked
            const status = isRevoked ? 'revoked' : val || 'unknown'
            // The mockup's badge: an icon and the word, no dot
            const config = {
              valid: { variant: 'success', icon: CheckCircle, label: t('common.valid') },
              expiring: { variant: 'warning', icon: Clock, label: t('common.expiring') },
              expired: { variant: 'danger', icon: XCircle, label: t('common.expired') },
              revoked: { variant: 'danger', icon: X, label: t('common.revoked') },
              unknown: { variant: 'secondary', icon: Info, label: t('common.status') }
            }
            const { variant, icon, label } = config[status] || config.unknown
            return <Badge variant={variant} size="sm" icon={icon}>{label}</Badge>
          }
        },
        {
          key: 'issuer',
          header: t('common.issuer'),
          priority: 3, sortable: true, hideOnMobile: true,
          render: (val, row) => (
            <span className="text-text-secondary truncate">{extractCN(val) || row.issuer_name || '—'}</span>
          )
        },
        {
          key: 'valid_to',
          header: t('common.expires'),
          priority: 4, sortable: true,
          render: (val) => (
            <span className="text-xs text-text-secondary whitespace-nowrap">{formatDate(val)}</span>
          )
        }
      ],
      filterFields: ['status', 'ca']
    },
    cas: {
      icon: ShieldCheck,
      color: 'icon-bg-green',
      actions: ['delete', 'export'],
      columns: [
        {
          key: 'descr',
          header: t('common.name'),
          sortable: true, priority: 1,
          render: (val, row) => (
            <span className="font-medium truncate">{val || extractCN(row.subject) || '—'}</span>
          )
        },
        {
          key: 'subject',
          header: t('common.subject'),
          sortable: true, priority: 2, hideOnMobile: true,
          render: (val) => <span className="text-text-secondary truncate">{extractCN(val) || val || '—'}</span>
        },
        {
          key: 'valid_to',
          header: t('common.expires'),
          sortable: true, priority: 3,
          render: (val) => (
            <span className="text-xs text-text-secondary whitespace-nowrap">{formatDate(val)}</span>
          )
        }
      ],
      filterFields: []
    },
    csrs: {
      icon: FileText,
      color: 'icon-bg-amber',
      actions: ['sign', 'delete'],
      columns: [
        {
          key: 'descr',
          header: t('common.name'),
          sortable: true, priority: 1,
          render: (val, row) => (
            <span className="font-medium truncate">{val || extractCN(row.subject) || '—'}</span>
          )
        },
        {
          key: 'subject',
          header: t('common.subject'),
          sortable: true, priority: 2, hideOnMobile: true,
          render: (val) => <span className="text-text-secondary truncate">{extractCN(val) || val || '—'}</span>
        },
        {
          key: 'created_at',
          header: t('common.created'),
          sortable: true, priority: 3,
          render: (val) => (
            <span className="text-xs text-text-secondary whitespace-nowrap">{formatDate(val)}</span>
          )
        }
      ],
      filterFields: []
    },
    templates: {
      icon: PencilSimple,
      color: 'icon-bg-violet',
      actions: ['delete'],
      columns: [
        {
          key: 'name',
          header: t('common.name'),
          sortable: true, priority: 1,
          render: (val) => (
            <span className="font-medium truncate">{val || '—'}</span>
          )
        },
        {
          key: 'key_type',
          header: t('common.keyType'),
          sortable: true, priority: 2,
          render: (val) => <Badge variant="secondary" size="sm">{val || '—'}</Badge>
        },
        {
          key: 'validity_days',
          header: t('common.validity'),
          sortable: true, priority: 3,
          render: (val) => <span className="text-text-secondary">{val ? `${val} ${t('common.days')}` : '—'}</span>
        }
      ],
      filterFields: []
    },
    users: {
      icon: User,
      color: 'icon-bg-orange',
      actions: ['delete'],
      columns: [
        {
          key: 'username',
          header: t('common.user'),
          sortable: true, priority: 1,
          render: (val, row) => {
            return (
              <div className="min-w-0">
                <div className="font-medium text-text-primary truncate">{val || '—'}</div>
                <div className="text-xs text-text-secondary truncate">{row.email || '—'}</div>
              </div>
            )
          }
        },
        {
          key: 'role',
          header: t('common.role'),
          sortable: true, priority: 2,
          render: (val) => {
            const roleConfig = { admin: { variant: 'violet' }, operator: { variant: 'primary' }, auditor: { variant: 'orange' }, viewer: { variant: 'teal' } }
            const config = roleConfig[val] || roleConfig.viewer
            const roleLabels = { admin: t('users.admin', 'Admin'), operator: t('common.operator', 'Operator'), auditor: t('common.auditor', 'Auditor'), viewer: t('common.viewer', 'Viewer') }
            return (
              <Badge variant={config.variant} size="sm">
                {val === 'admin' && <Crown weight="fill" className="h-3 w-3 mr-1" />}
                {roleLabels[val] || t('common.viewer')}
              </Badge>
            )
          }
        },
        {
          key: 'active',
          header: t('common.status'),
          priority: 3, sortable: true,
          render: (v) => v 
            ? <Badge variant="success" size="sm">{t('common.active')}</Badge>
            : <Badge variant="orange" size="sm">{t('common.disabled')}</Badge>
        }
      ],
      filterFields: []
    }
  }), [t])
}

export default function OperationsPage() {
  const { t } = useTranslation()
  const { showSuccess, showError, showWarning, showInfo } = useNotification()
  const { isMobile } = useMobile()
  const { isAdmin } = usePermission()
  const openEntity = useOpenEntity()
  const RESOURCE_TYPES = useResourceTypes(t)
  
  const TABS = [
    { id: 'import', label: t('common.import'), description: t('operations.importHeaderDesc'), icon: UploadSimple },
    { id: 'export', label: t('common.export'), description: t('operations.exportHeaderDesc'), icon: DownloadSimple },
    { id: 'bulk', label: t('operations.bulkActions', 'Bulk Actions'), description: t('operations.bulkHeaderDesc'), icon: Lightning },
  ]
  // The operation a link names (/operations?tab=bulk) is the one shown
  const [activeTab, setActiveTab] = useSectionParam(['import', 'export', 'bulk'], 'import')

  // ===== IMPORT STATE (from ImportExportPage) =====
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

  // ===== BULK STATE =====
  const [bulkResourceType, setBulkResourceType] = useState(() => {
    try { return localStorage.getItem('ucm-ops-resource-type') || 'certificates' } catch { return 'certificates' }
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
  const [bulkViewMode, setBulkViewMode] = useState('table') // 'table' | 'basket'
  const [resourceCounts, setResourceCounts] = useState({})
  const [bulkSearch, setBulkSearch] = useState('')
  const [bulkPage, setBulkPage] = useState(1)
  const [bulkPerPage, setBulkPerPage] = useState(25)
  const [bulkTotal, setBulkTotal] = useState(0)
  // Items selected on other pages, kept so the basket view can still render
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
      showSuccess(t('operations.bulkSuccess', { 
        action: bulkAction, count: successCount,
        defaultValue: `${bulkAction}: ${successCount} succeeded${failedCount ? `, ${failedCount} failed` : ''}`
      }))
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

  // Toolbar filters for bulk table
  const bulkToolbarFilters = useMemo(() => {
    if (bulkResourceType !== 'certificates') return undefined
    return [
      {
        key: 'status',
        value: statusFilter,
        onChange: (v) => { setStatusFilter(v); setBulkPage(1) },
        placeholder: t('common.allStatuses', 'All Statuses'),
        options: [
          { value: 'valid', label: t('common.valid', 'Valid') },
          { value: 'expired', label: t('common.expired', 'Expired') },
          { value: 'revoked', label: t('common.revoked', 'Revoked') }
        ]
      },
      {
        key: 'ca',
        value: caFilter,
        onChange: (v) => { setCaFilter(v); setBulkPage(1) },
        placeholder: t('common.allCAs', 'All CAs'),
        options: cas.map(ca => ({ value: String(ca.id), label: ca.descr || ca.subject || `CA #${ca.id}` }))
      }
    ]
  }, [bulkResourceType, statusFilter, caFilter, cas, t])

  const resourceConfig = RESOURCE_TYPES[bulkResourceType]

  // Bulk action buttons
  const renderBulkActionButtons = useCallback(() => {
    // Every bulk route here is admin-only, and so is the page: keeping the
    // bar on the same check means a routing change cannot expose it.
    if (!resourceConfig || !isAdmin()) return null
    return (
      <div className="flex items-center gap-1.5">
        {resourceConfig.actions.includes('revoke') && (
          <Button type="button" size="sm" variant="secondary" onClick={() => setBulkAction('revoke')}>
            <Prohibit size={14} /> {t('common.revoke', 'Revoke')}
          </Button>
        )}
        {resourceConfig.actions.includes('renew') && (
          <Button type="button" size="sm" variant="secondary" onClick={() => setBulkAction('renew')}>
            <ArrowsClockwise size={14} /> {t('common.renew', 'Renew')}
          </Button>
        )}
        {resourceConfig.actions.includes('sign') && (
          <Button type="button" size="sm" variant="secondary" onClick={() => setBulkAction('sign')}>
            <PencilSimple size={14} /> {t('common.sign', 'Sign')}
          </Button>
        )}
        {resourceConfig.actions.includes('export') && (
          <Button type="button" size="sm" variant="secondary" onClick={async () => {
            const ids = Array.from(selectedIds)
            if (!ids.length) return
            try {
              const service = bulkResourceType === 'certificates' ? certificatesService : casService
              const blob = await service.bulkExport(ids, 'pem')
              if (blob) {
                downloadBlob(blob, `${bulkResourceType}_export.pem`)
              }
              showSuccess(t('operations.bulkSuccess', { action: 'export', count: blob?.exportedCount ?? ids.length, defaultValue: `Exported ${blob?.exportedCount ?? ids.length} items` }))
              warnSkippedExport(blob, t, showWarning)
            } catch (e) { showError(e.message || 'Export failed') }
          }}>
            <DownloadSimple size={14} /> {t('export.title', 'Export')} PEM
          </Button>
        )}
        {resourceConfig.actions.includes('delete') && (
          <Button type="button" size="sm" variant="danger" onClick={() => setBulkAction('delete')}>
            <Trash size={14} /> {t('common.delete', 'Delete')}
          </Button>
        )}
      </div>
    )
  }, [resourceConfig, selectedIds, bulkResourceType, t])

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

  // ===== TAB CONTENT =====
  const renderImportTab = () => (
    <>
      <FormGroup 
        title={t('importExport.smartImport.title')} 
        description={t('importExport.smartImport.description')}
      >
        <SmartImportWidget onImportComplete={handleImportComplete} />
      </FormGroup>

      <FormGroup title={t('importExport.opnsense.title')} description={t('importExport.opnsense.description')}>
        <form onSubmit={(e) => e.preventDefault()} className="sf-stack">
          <div className="sf-grid">
            <Input label={t('importExport.opnsense.hostLabel')} value={opnsenseHost} onChange={(e) => setOpnsenseHost(e.target.value)} placeholder={t('importExport.opnsense.hostPlaceholder')} />
            <Input className="sf-short" label={t('common.portLabel')} inputMode="numeric" value={opnsensePort} onChange={(e) => setOpnsensePort(e.target.value)} placeholder={t('common.portPlaceholder')} />
            <Input label={t('importExport.opnsense.apiKeyLabel')} value={opnsenseApiKey} onChange={(e) => setOpnsenseApiKey(e.target.value)} placeholder={t('importExport.opnsense.apiKeyLabel')} />
            <Input label={t('importExport.opnsense.apiSecretLabel')} type="password" noAutofill value={opnsenseApiSecret} onChange={(e) => setOpnsenseApiSecret(e.target.value)} placeholder={t('importExport.opnsense.apiSecretLabel')} />
          </div>
          <ToggleSwitch
            checked={!opnsenseVerifySsl}
            onChange={(ignore) => setOpnsenseVerifySsl(!ignore)}
            label={t('importExport.opnsense.ignoreCert')}
          />
          {!opnsenseVerifySsl && (
            <HelpCard variant="warning">{t('importExport.opnsense.sslWarning')}</HelpCard>
          )}

          {testResult?.success && testItems.length > 0 && (
            <div>
              <ToggleSwitch
                checked={testItems.every(i => i.selected)}
                onChange={(on) => toggleAllItems(on)}
                label={`${t('importExport.opnsense.selectAll')} (${testItems.filter(i => i.selected).length}/${testItems.length})`}
              />
              <ul className="sf-records sf-records-scroll">
                {testItems.map(item => (
                  <li key={item.id}>
                    <ToggleSwitch
                      checked={item.selected}
                      onChange={() => toggleItemSelection(item.id)}
                      label={(
                        <span className="sf-record-title">
                          <strong>{item.name || t('common.unnamed')}</strong>
                          <Badge variant={item.type === 'CA' ? 'primary' : 'info'}>{item.type === 'CA' ? t('common.ca') : t('common.certificate')}</Badge>
                        </span>
                      )}
                    />
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* The test as the mockup's test zone: the button, then its result on the line */}
          <div className="sf-test">
            <Button ref={opnsenseTestButton} type="button" variant="secondary" onClick={handleTestConf} disabled={processing || !opnsenseHost || !opnsenseApiKey || !opnsenseApiSecret}>
              <PlugsConnected size={16} />
              {processing ? t('common.testing') : t('common.testConnection')}
            </Button>
            {testResult?.success && testItems.some(i => i.selected) && (
              <Button type="button" onClick={handleImportFromOpnsense} disabled={processing}>
                <UploadSimple size={16} />
                {t('importExport.opnsense.importSelected', { count: testItems.filter(i => i.selected).length })}
              </Button>
            )}
            {testResult ? (
              <p className={testResult.success ? 'sf-test-result is-good' : 'sf-test-result is-bad'} role="status">
                {testResult.success ? <CheckCircle aria-hidden="true" /> : <WarningCircle aria-hidden="true" />}
                <span>
                  {testResult.success
                    ? (testResult.stats
                      ? t('importExport.opnsense.connectedWithCounts', { cas: testResult.stats.cas, certificates: testResult.stats.certificates })
                      : t('importExport.opnsense.connectedSuccessfully'))
                    : (testResult.error || t('importExport.opnsense.connectionFailed'))}
                </span>
              </p>
            ) : (
              <p className="sf-test-result">
                <Question aria-hidden="true" />
                <span>{t('importExport.opnsense.testHint')}</span>
              </p>
            )}
          </div>
        </form>
      </FormGroup>
    </>
  )

  // Each export as a record of the mockup's list: the format, what it holds, its download button
  const exportRow = (key, label, desc, onClick) => (
    <li key={key}>
      <div className="sf-record-main">
        <strong>{label}</strong>
        <span className="sf-record-meta">{desc}</span>
      </div>
      <div className="sf-record-actions">
        <Button type="button" variant="secondary" onClick={onClick} aria-label={`${t('common.download')} ${label}`}>
          <DownloadSimple size={16} />
          {t('common.download')}
        </Button>
      </div>
    </li>
  )

  const renderExportTab = () => (
    <>
      <FormGroup title={t('importExport.export.allCertsTitle')} description={t('importExport.export.allCertsDesc')}>
        <ul className="sf-records">
          {exportRow('cert-pem', t('importExport.export.pemBundle'), t('importExport.export.pemDesc'),
            () => handleExport(certificatesService.exportAll, 'pem', 'certificates'))}
          {exportRow('cert-p7b', t('importExport.export.p7bBundle'), t('importExport.export.p7bDesc'),
            () => handleExport(certificatesService.exportAll, 'pkcs7', 'certificates'))}
        </ul>
      </FormGroup>

      <FormGroup title={t('importExport.export.allCAsTitle')} description={t('importExport.export.allCAsDesc', { count: cas.length })}>
        <ul className="sf-records">
          {exportRow('ca-pem', t('importExport.export.pemBundle'), t('importExport.export.pemDesc'),
            () => handleExport(casService.exportAll, 'pem', 'ca-certificates'))}
          {exportRow('ca-p7b', t('importExport.export.p7bBundle'), t('importExport.export.p7bDesc'),
            () => handleExport(casService.exportAll, 'pkcs7', 'ca-certificates'))}
        </ul>
      </FormGroup>
    </>
  )

  // Render item for basket/transfer view — compact row per resource type
  const renderBasketItem = useCallback((item) => {
    const type = bulkResourceType
    if (type === 'certificates') {
      const name = item.cn || item.common_name || extractCN(item.subject) || item.descr || '?'
      const status = item.revoked ? 'revoked' : item.status || 'unknown'
      const statusColors = { valid: 'text-accent-success', expiring: 'text-accent-warning', expired: 'text-accent-danger', revoked: 'text-accent-danger' }
      const statusLabels = { valid: t('common.valid'), expiring: t('common.expiring'), expired: t('common.expired'), revoked: t('common.revoked') }
      return (
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium truncate flex-1">{name}</span>
          <span className={cn("text-xs", statusColors[status] || 'text-text-tertiary')}>{statusLabels[status] || t('common.status')}</span>
        </div>
      )
    }
    if (type === 'cas') {
      return (
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium truncate">{item.descr || extractCN(item.subject) || '—'}</span>
        </div>
      )
    }
    if (type === 'csrs') {
      return (
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium truncate">{item.descr || extractCN(item.subject) || '—'}</span>
        </div>
      )
    }
    if (type === 'templates') {
      return (
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium truncate flex-1">{item.name || '—'}</span>
          <span className="text-xs text-text-tertiary">{item.key_type}</span>
        </div>
      )
    }
    if (type === 'users') {
      return (
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium truncate flex-1">{item.username || '—'}</span>
          <span className="text-xs text-text-tertiary">{item.role}</span>
        </div>
      )
    }
    return <span className="text-sm truncate">{item.name || item.descr || item.username || '—'}</span>
  }, [bulkResourceType, t])

  const renderBulkTab = () => (
    <div className="flex flex-col h-full min-h-0">
      {/* Resource type selector, at the 20 px content edge of the other frames */}
      <div className="shrink-0 px-4 md:px-5 pb-1">
        {isMobile ? (
          /* Mobile: dropdown select */
          <div className="relative">
            <select
              value={bulkResourceType}
              onChange={(e) => { const v = e.target.value; setBulkResourceType(v); try { localStorage.setItem('ucm-ops-resource-type', v) } catch {}; setStatusFilter(''); setCaFilter(''); setSelectedIds(new Set()); setBulkSearch(''); setBulkPage(1); seenItemsRef.current.clear() }}
              className="ui-control w-full appearance-none pr-10"
            >
              {Object.entries(RESOURCE_TYPES).map(([key, config]) => {
                const count = resourceCounts[key]
                return (
                  <option key={key} value={key}>
                    {t(`common.${key}Short`, key)}{count !== undefined ? ` (${count})` : ''}
                  </option>
                )
              })}
            </select>
            <CaretDown size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-text-tertiary pointer-events-none" />
          </div>
        ) : (
          /* Desktop: two rows — chips, then search + filters + toggle */
          <div className="space-y-2">
            {/* The resource type as the mockup's segmented choice, its count after the name */}
            <div className="ui-segmented" role="group" aria-label={t('operations.selectResource')}>
              {Object.entries(RESOURCE_TYPES).map(([key, config]) => {
                const Icon = config.icon
                const isActive = bulkResourceType === key
                const count = resourceCounts[key]
                return (
                  <button
                    type="button"
                    key={key}
                    aria-pressed={isActive}
                    onClick={() => { setBulkResourceType(key); try { localStorage.setItem('ucm-ops-resource-type', key) } catch {}; setStatusFilter(''); setCaFilter(''); setSelectedIds(new Set()); setBulkSearch(''); setBulkPage(1); seenItemsRef.current.clear() }}
                  >
                    <Icon size={14} aria-hidden="true" />
                    {t(`common.${key}Short`, key)}
                    {count !== undefined && <span className="ops-count">{count}</span>}
                  </button>
                )
              })}
            </div>

            <div className="flex items-center gap-2">
              {/* Search */}
              <div className="relative flex-1 min-w-0">
                <MagnifyingGlass size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-tertiary" />
                <input
                  type="text"
                  value={bulkSearch}
                  onChange={(e) => { setBulkSearch(e.target.value); setBulkPage(1) }}
                  placeholder={t('common.search')}
                  className="ui-control pl-8"
                />
              </div>

              {/* Status & CA filters — only for certificates */}
              {bulkResourceType === 'certificates' && (
                <>
                  <select
                    value={statusFilter}
                    onChange={(e) => { setStatusFilter(e.target.value); setBulkPage(1) }}
                    className="ui-control is-filter shrink-0"
                  >
                    <option value="">{t('common.allStatuses', 'All Statuses')}</option>
                    <option value="valid">{t('common.valid', 'Valid')}</option>
                    <option value="expired">{t('common.expired', 'Expired')}</option>
                    <option value="revoked">{t('common.revoked', 'Revoked')}</option>
                  </select>
                  <select
                    value={caFilter}
                    onChange={(e) => { setCaFilter(e.target.value); setBulkPage(1) }}
                    className="ui-control is-filter shrink-0 truncate"
                  >
                    <option value="">{t('common.allCAs', 'All CAs')}</option>
                    {cas.map(ca => (
                      <option key={ca.id} value={String(ca.id)}>{ca.descr || ca.subject || `CA #${ca.id}`}</option>
                    ))}
                  </select>
                </>
              )}

              {/* View mode toggle */}
              <div className="ui-segmented shrink-0" role="group">
                <button
                  type="button"
                  onClick={() => setBulkViewMode('table')}
                  aria-pressed={bulkViewMode === 'table'}
                  aria-label={t('operations.tableView', 'Table View')}
                  title={t('operations.tableView', 'Table View')}
                >
                  <Table size={16} aria-hidden="true" />
                </button>
                <button
                  type="button"
                  onClick={() => setBulkViewMode('basket')}
                  aria-pressed={bulkViewMode === 'basket'}
                  aria-label={t('operations.basketView', 'Basket View')}
                  title={t('operations.basketView', 'Basket View')}
                >
                  <ShoppingCart size={16} aria-hidden="true" />
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Content area — table on mobile, table or basket on desktop */}
      <div className="flex-1 min-h-0 md:px-5 md:pb-5">
        {(isMobile || bulkViewMode === 'table') ? (
          <ResponsiveDataTable
            data={bulkData}
            columns={resourceConfig.columns}
            multiSelect={true}
            selectedIds={selectedIds}
            onSelectionChange={setSelectedIds}
            bulkActions={renderBulkActionButtons()}
            searchable={isMobile}
            externalSearch={serverPaged ? bulkSearch : (isMobile ? undefined : bulkSearch)}
            onSearchChange={serverPaged
              ? (v) => { setBulkSearch(v); setBulkPage(1) }
              : (isMobile ? undefined : setBulkSearch)}
            searchPlaceholder={t('common.search')}
            searchKeys={serverPaged ? [] : ['cn', 'descr', 'name', 'subject', 'username', 'email', 'common_name']}
            sortable
            densityStorageKey="ucm-operations-density"
            toolbarFilters={isMobile ? bulkToolbarFilters : undefined}
            loading={bulkLoading}
            pagination={serverPaged
              ? {
                  page: bulkPage,
                  total: bulkTotal,
                  perPage: bulkPerPage,
                  onChange: setBulkPage,
                  onPerPageChange: (v) => { setBulkPerPage(v); setBulkPage(1) }
                }
              : true}
            defaultPerPage={25}
            emptyIcon={resourceConfig.icon}
            emptyTitle={t('operations.noData', 'No items found')}
            emptyDescription={t('operations.noDataDesc', 'Try adjusting your filters')}
          />
        ) : (
          <div className="h-full px-4 md:px-0 pb-2">
            <TransferPanel
              items={basketItems}
              selectedIds={selectedIds}
              onSelectionChange={setSelectedIds}
              renderItem={renderBasketItem}
              searchKeys={['cn', 'descr', 'name', 'subject', 'username', 'email', 'common_name']}
              leftTitle={t(`common.${bulkResourceType}`, bulkResourceType)}
              rightTitle={t('operations.basket', 'Basket')}
              leftIcon={resourceConfig.icon}
              rightIcon={ShoppingCart}
              emptyRightMessage={t('operations.dragHere', 'Drag items here or click + to add')}
              bulkActions={renderBulkActionButtons()}
            />
          </div>
        )}
      </div>
    </div>
  )

  const renderContent = () => {
    switch (activeTab) {
      case 'import': return renderImportTab()
      case 'export': return renderExportTab()
      case 'bulk': return renderBulkTab()
      default: return null
    }
  }

  const active = TABS.find(tab => tab.id === activeTab)

  // One operation at a time in its frame; import and export keep their own actions, no save bar
  return (
    <ResponsiveLayout
      title={t('operations.title', 'Operations')}
      total={t('sectioned.sectionCount', { count: TABS.length })}
      intent={t('shell.moduleDesc.operations')}
      helpPageKey="operations"
    >
      <FormLayout
        toc={(
          <SectionToc
            label={t('operations.tocLabel')}
            sections={TABS}
            current={activeTab}
            hrefFor={(id) => (id === 'import' ? '/operations' : `/operations?tab=${id}`)}
            onJump={setActiveTab}
          />
        )}
      >
        <SectionJump label={t('sectioned.jumpLabel')} sections={TABS} value={activeTab} onJump={setActiveTab} />
        <FormSection
          id={active.id}
          title={active.label}
          description={active.description}
          bodyClassName={activeTab === 'bulk' ? 'sf-body-fill' : undefined}
        >
          {renderContent()}
        </FormSection>
      </FormLayout>

      {/* Confirm modal for bulk actions (not export/sign — they have their own) */}
      <ConfirmModal
        open={!!bulkAction && bulkAction !== 'export' && bulkAction !== 'sign'}
        onClose={() => { setBulkAction(null); setBulkRevokeReason('unspecified') }}
        onConfirm={executeBulkAction}
        title={t('operations.confirmBulk', 'Confirm Bulk Operation')}
        message={bulkAction === 'revoke' && bulkResourceType === 'certificates' ? (
          <div className="space-y-3">
            <p>{getConfirmMessage()}</p>
            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-text-secondary uppercase tracking-wide">
                {t('revocation.reasonLabel')}
              </label>
              <select
                value={bulkRevokeReason}
                onChange={(e) => setBulkRevokeReason(e.target.value)}
                className="ui-control w-full"
              >
                {REVOCATION_REASONS.map(r => (
                  <option key={r} value={r}>{t(`revocation.reasons.${r}`)}</option>
                ))}
              </select>
              <p className="text-xs text-text-tertiary">{t(`revocation.hints.${bulkRevokeReason}`)} {t('revocation.bulkReasonHelp')}</p>
            </div>
            {selectionHasPairs && (
              <div className="flex items-start gap-2.5">
                <input
                  type="checkbox"
                  id="bulk-revoke-related"
                  checked={bulkRevokeRelated}
                  onChange={(e) => setBulkRevokeRelated(e.target.checked)}
                  className="w-4 h-4 mt-0.5 rounded accent-accent-primary"
                />
                <div>
                  <label htmlFor="bulk-revoke-related" className="text-sm text-text-primary cursor-pointer">
                    {t('revocation.revokeRelatedBulk')}
                  </label>
                  <p className="text-xs text-text-tertiary">{t('revocation.revokeRelatedBulkHint')}</p>
                </div>
              </div>
            )}
          </div>
        ) : getConfirmMessage()}
        confirmLabel={bulkAction === 'delete' ? t('common.delete') : t('common.confirm', 'Confirm')}
        variant={bulkAction === 'delete' || bulkAction === 'revoke' ? 'danger' : 'primary'}
        loading={bulkProcessing || partnersLoading}
      />

      {/* Sign CSR modal (needs CA selection) */}
      {bulkAction === 'sign' && (
        <ConfirmModal
          open={true}
          onClose={() => setBulkAction(null)}
          onConfirm={executeBulkAction}
          title={t('operations.signCSRs', `Sign ${selectedIds.size} CSR(s)`)}
          message={
            <div className="space-y-3">
              <p>{t('operations.selectCAForSign', 'Select a CA to sign the CSRs:')}</p>
              <select
                value={bulkSignCaId}
                onChange={(e) => setBulkSignCaId(e.target.value)}
                className="ui-control w-full"
              >
                <option value="">{t('common.selectCA', 'Select CA...')}</option>
                {listedForIssuance(signingCas(cas), showHiddenCas, bulkSignCaId).map(ca => (
                  <option key={ca.id} value={ca.id}>{ca.descr || ca.subject}</option>
                ))}
              </select>
              <HiddenCasToggle count={hiddenFromIssuance(signingCas(cas), bulkSignCaId)} shown={showHiddenCas} onToggle={() => setShowHiddenCas(v => !v)} />
              {unlistedSigningCas(cas) > 0 && (
                <p className="text-xs text-text-tertiary">{t('cas.notListedForSigning', { count: unlistedSigningCas(cas) })}</p>
              )}
              <Input
                label={t('common.validityDays', 'Validity (days)')}
                type="number"
                value={bulkSignDays}
                onChange={(e) => setBulkSignDays(e.target.value)}
              />
            </div>
          }
          confirmLabel={t('common.sign', 'Sign')}
          variant="primary"
          loading={bulkProcessing}
        />
      )}

      {/* Export action is immediate, no confirmation needed */}
    </ResponsiveLayout>
  )
}
