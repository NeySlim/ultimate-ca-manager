/**
 * Operations Page - Import, Export & Bulk Actions
 * Replaces ImportExportPage with unified operations center
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { 
  UploadSimple, DownloadSimple, CloudArrowUp, Lightning,
  CheckCircle, XCircle, Clock, X, Certificate, ShieldCheck, Key, Trash, 
  ArrowsClockwise, Prohibit, PencilSimple, FileText, Warning, User, Crown, Info,
  Table, ShoppingCart, Package
} from '@phosphor-icons/react'
import { 
  ResponsiveLayout, ResponsiveDataTable, Button, Input, 
  DetailSection, ConfirmModal, Badge, KeyIndicator, TransferPanel
} from '../components'
import { SmartImportWidget } from '../components/SmartImport'
import { 
  opnsenseService, casService, certificatesService, 
  csrsService, templatesService, usersService 
} from '../services'
import { useNotification } from '../contexts'
import { formatDate, extractCN, cn } from '../lib/utils'

const STORAGE_KEY = 'opnsense_config'

// Resource type definitions - built inside component to use t() for translations
function useResourceTypes(t) {
  return useMemo(() => ({
    certificates: {
      icon: Certificate,
      color: 'icon-bg-blue',
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
                <div className={cn(
                  "w-7 h-7 rounded-lg flex items-center justify-center shrink-0",
                  row.has_private_key ? "icon-bg-emerald" : "icon-bg-blue"
                )}>
                  <Certificate size={14} weight="duotone" />
                </div>
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
            const config = {
              valid: { variant: 'success', icon: CheckCircle, label: t('common.valid'), pulse: true },
              expiring: { variant: 'warning', icon: Clock, label: t('common.expiring'), pulse: true },
              expired: { variant: 'danger', icon: XCircle, label: t('common.expired'), pulse: false },
              revoked: { variant: 'danger', icon: X, label: t('common.revoked'), pulse: false },
              unknown: { variant: 'secondary', icon: Info, label: t('common.status'), pulse: false }
            }
            const { variant, icon, label, pulse } = config[status] || config.unknown
            return <Badge variant={variant} size="sm" icon={icon} dot pulse={pulse}>{label}</Badge>
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
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 icon-bg-green">
                <ShieldCheck size={14} weight="duotone" />
              </div>
              <span className="font-medium truncate">{val || extractCN(row.subject) || '—'}</span>
            </div>
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
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 icon-bg-amber">
                <FileText size={14} weight="duotone" />
              </div>
              <span className="font-medium truncate">{val || extractCN(row.subject) || '—'}</span>
            </div>
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
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 icon-bg-violet">
                <PencilSimple size={14} weight="duotone" />
              </div>
              <span className="font-medium truncate">{val || '—'}</span>
            </div>
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
            const avatarColors = { admin: 'icon-bg-violet', operator: 'icon-bg-blue', viewer: 'icon-bg-teal' }
            const colorClass = row.active ? (avatarColors[row.role] || avatarColors.viewer) : 'icon-bg-orange'
            return (
              <div className="flex items-center gap-3">
                <div className={cn(
                  "w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shadow-sm ring-1 ring-white/10",
                  colorClass
                )}>
                  {val?.charAt(0)?.toUpperCase() || '?'}
                </div>
                <div className="min-w-0">
                  <div className="font-medium text-text-primary truncate">{val || '—'}</div>
                  <div className="text-xs text-text-secondary truncate">{row.email || '—'}</div>
                </div>
              </div>
            )
          }
        },
        {
          key: 'role',
          header: t('common.role'),
          sortable: true, priority: 2,
          render: (val) => {
            const roleConfig = { admin: { variant: 'violet', dot: true }, operator: { variant: 'primary', dot: false }, viewer: { variant: 'teal', dot: false } }
            const config = roleConfig[val] || roleConfig.viewer
            const roleLabels = { admin: t('users.admin', 'Admin'), operator: t('common.operator', 'Operator'), viewer: t('common.viewer', 'Viewer') }
            return (
              <Badge variant={config.variant} size="sm" dot={config.dot}>
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
            ? <Badge variant="success" size="sm" dot>{t('common.active')}</Badge>
            : <Badge variant="orange" size="sm" dot>{t('common.disabled')}</Badge>
        }
      ],
      filterFields: []
    }
  }), [t])
}

export default function OperationsPage() {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const navigate = useNavigate()
  const RESOURCE_TYPES = useResourceTypes(t)
  
  const TABS = [
    { id: 'import', label: t('common.import'), icon: UploadSimple },
    { id: 'export', label: t('common.export'), icon: DownloadSimple },
    { id: 'bulk', label: t('operations.bulkActions', 'Bulk Actions'), icon: Lightning },
  ]
  const [activeTab, setActiveTab] = useState('import')

  // ===== IMPORT STATE (from ImportExportPage) =====
  const [processing, setProcessing] = useState(false)
  const [cas, setCas] = useState([])
  const [opnsenseHost, setOpnsenseHost] = useState('')
  const [opnsensePort, setOpnsensePort] = useState('443')
  const [opnsenseApiKey, setOpnsenseApiKey] = useState('')
  const [opnsenseApiSecret, setOpnsenseApiSecret] = useState('')
  const [testResult, setTestResult] = useState(null)
  const [testItems, setTestItems] = useState([])

  // ===== BULK STATE =====
  const [bulkResourceType, setBulkResourceType] = useState('certificates')
  const [bulkData, setBulkData] = useState([])
  const [bulkLoading, setBulkLoading] = useState(false)
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [bulkAction, setBulkAction] = useState(null)
  const [bulkProcessing, setBulkProcessing] = useState(false)
  const [bulkSignCaId, setBulkSignCaId] = useState('')
  const [bulkSignDays, setBulkSignDays] = useState('365')
  const [statusFilter, setStatusFilter] = useState('')
  const [caFilter, setCaFilter] = useState('')
  const [bulkViewMode, setBulkViewMode] = useState('table') // 'table' | 'basket'

  // Load on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved) {
        const config = JSON.parse(saved)
        setOpnsenseHost(config.host || '')
        setOpnsensePort(config.port || '443')
        setOpnsenseApiKey(config.api_key || '')
        setOpnsenseApiSecret(config.api_secret || '')
      }
    } catch (e) {}
    loadCAs()
  }, [])

  // Load bulk data when resource type changes
  useEffect(() => {
    if (activeTab === 'bulk') loadBulkData()
  }, [bulkResourceType, activeTab])

  const loadCAs = async () => {
    try {
      const response = await casService.getAll()
      setCas(response.data || [])
    } catch (e) {}
  }

  const loadBulkData = async () => {
    setBulkLoading(true)
    setSelectedIds(new Set())
    try {
      let response
      switch (bulkResourceType) {
        case 'certificates':
          response = await certificatesService.getAll()
          break
        case 'cas':
          response = await casService.getAll()
          break
        case 'csrs':
          response = await csrsService.getAll()
          break
        case 'templates':
          response = await templatesService.getAll()
          break
        case 'users':
          response = await usersService.getAll()
          break
      }
      setBulkData(response?.data || [])
    } catch (e) {
      showError(t('operations.loadFailed', 'Failed to load data'))
    } finally {
      setBulkLoading(false)
    }
  }

  // ===== IMPORT HANDLERS (from ImportExportPage) =====
  const saveOpnsenseConfig = () => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        host: opnsenseHost, port: opnsensePort,
        api_key: opnsenseApiKey, api_secret: opnsenseApiSecret
      }))
      showSuccess(t('importExport.opnsense.configSaved'))
    } catch (e) {}
  }

  const handleTestConf = async () => {
    setProcessing(true)
    setTestResult(null)
    setTestItems([])
    try {
      const result = await opnsenseService.test({
        host: opnsenseHost, port: opnsensePort,
        api_key: opnsenseApiKey, api_secret: opnsenseApiSecret
      })
      setTestResult({ success: true, stats: result.stats })
      setTestItems((result.items || []).map(item => ({ ...item, selected: true })))
      saveOpnsenseConfig()
    } catch (error) {
      setTestResult({ success: false, error: error.message })
      showError(error.message || t('importExport.opnsense.connectionFailed'))
    } finally {
      setProcessing(false)
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
        items: selectedItems
      })
      const imported = (result.imported?.cas || 0) + (result.imported?.certificates || 0)
      showSuccess(t('importExport.opnsense.importSuccess', { count: imported, skipped: result.skipped || 0 }))
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
    if (result?.imported?.length > 0) {
      const first = result.imported[0]
      if (first.type === 'ca' || first.type === 'ca_certificate') {
        navigate(`/cas?selected=${first.id}`)
      } else if (first.type === 'certificate') {
        navigate(`/certificates?selected=${first.id}`)
      }
    }
  }

  // ===== EXPORT HANDLERS =====
  const handleExport = async (service, format, filename) => {
    try {
      const blob = await service(format)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const ext = { pem: 'pem', pkcs7: 'p7b', p7b: 'p7b' }[format] || format
      a.download = `${filename}.${ext}`
      a.click()
      URL.revokeObjectURL(url)
      showSuccess(t('importExport.export.certificatesExported'))
    } catch (error) {
      showError(error.message || t('importExport.export.exportFailed'))
    }
  }

  // ===== BULK ACTION HANDLERS =====
  const executeBulkAction = async () => {
    if (selectedIds.size === 0) return
    setBulkProcessing(true)
    const ids = Array.from(selectedIds)
    try {
      let result
      switch (`${bulkResourceType}:${bulkAction}`) {
        case 'certificates:revoke':
          result = await certificatesService.bulkRevoke(ids)
          break
        case 'certificates:renew':
          result = await certificatesService.bulkRenew(ids)
          break
        case 'certificates:delete':
          result = await certificatesService.bulkDelete(ids)
          break
        case 'cas:delete':
          result = await casService.bulkDelete(ids)
          break
        case 'csrs:sign':
          if (!bulkSignCaId) { showError('Select a CA'); setBulkProcessing(false); return }
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
      setBulkAction(null)
      setSelectedIds(new Set())
      loadBulkData()
    } catch (error) {
      showError(error.message || t('operations.bulkFailed', 'Bulk operation failed'))
    } finally {
      setBulkProcessing(false)
    }
  }

  // Filter bulk data
  const filteredBulkData = useMemo(() => {
    let data = bulkData
    if (bulkResourceType === 'certificates') {
      if (statusFilter === 'valid') data = data.filter(c => !c.revoked && (!c.valid_to || new Date(c.valid_to) > new Date()))
      if (statusFilter === 'expired') data = data.filter(c => c.valid_to && new Date(c.valid_to) < new Date())
      if (statusFilter === 'revoked') data = data.filter(c => c.revoked)
      if (caFilter) data = data.filter(c => c.caref === caFilter || c.issuer_id === parseInt(caFilter))
    }
    return data
  }, [bulkData, statusFilter, caFilter, bulkResourceType])

  // Toolbar filters for bulk table
  const bulkToolbarFilters = useMemo(() => {
    if (bulkResourceType !== 'certificates') return undefined
    return [
      {
        key: 'status',
        value: statusFilter,
        onChange: setStatusFilter,
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
        onChange: setCaFilter,
        placeholder: t('common.allCAs', 'All CAs'),
        options: cas.map(ca => ({ value: String(ca.id || ca.refid), label: ca.descr || ca.subject || `CA #${ca.id}` }))
      }
    ]
  }, [bulkResourceType, statusFilter, caFilter, cas, t])

  const resourceConfig = RESOURCE_TYPES[bulkResourceType]

  // Bulk action buttons
  const renderBulkActionButtons = useCallback(() => {
    if (!resourceConfig) return null
    return (
      <div className="flex items-center gap-1.5">
        {resourceConfig.actions.includes('revoke') && (
          <Button size="sm" variant="secondary" onClick={() => setBulkAction('revoke')}>
            <Prohibit size={14} /> {t('common.revoke', 'Revoke')}
          </Button>
        )}
        {resourceConfig.actions.includes('renew') && (
          <Button size="sm" variant="secondary" onClick={() => setBulkAction('renew')}>
            <ArrowsClockwise size={14} /> {t('common.renew', 'Renew')}
          </Button>
        )}
        {resourceConfig.actions.includes('sign') && (
          <Button size="sm" variant="secondary" onClick={() => setBulkAction('sign')}>
            <PencilSimple size={14} /> {t('common.sign', 'Sign')}
          </Button>
        )}
        {resourceConfig.actions.includes('export') && (
          <Button size="sm" variant="secondary" onClick={async () => {
            const ids = Array.from(selectedIds)
            try {
              if (bulkResourceType === 'certificates') await certificatesService.bulkExport(ids)
              else if (bulkResourceType === 'cas') await casService.bulkExport(ids)
              showSuccess(t('operations.bulkSuccess', { action: 'export', count: ids.length, defaultValue: `Exported ${ids.length} items` }))
            } catch (e) { showError(e.message || 'Export failed') }
          }}>
            <DownloadSimple size={14} /> {t('common.export', 'Export')}
          </Button>
        )}
        {resourceConfig.actions.includes('delete') && (
          <Button size="sm" variant="danger" onClick={() => setBulkAction('delete')}>
            <Trash size={14} /> {t('common.delete', 'Delete')}
          </Button>
        )}
      </div>
    )
  }, [resourceConfig, t])

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
    <div className="max-w-3xl mx-auto space-y-6">
      <DetailSection 
        title={t('importExport.smartImport.title')}
        icon={UploadSimple} 
        iconClass="icon-bg-violet" 
        description={t('importExport.smartImport.description')}
      >
        <SmartImportWidget onImportComplete={handleImportComplete} />
      </DetailSection>

      <DetailSection title={t('importExport.opnsense.title')} icon={CloudArrowUp} iconClass="icon-bg-orange" description={t('importExport.opnsense.description')}>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Input label={t('importExport.opnsense.hostLabel')} value={opnsenseHost} onChange={(e) => setOpnsenseHost(e.target.value)} placeholder={t('importExport.opnsense.hostPlaceholder')} />
          <Input label={t('common.portLabel')} value={opnsensePort} onChange={(e) => setOpnsensePort(e.target.value)} placeholder={t('common.portPlaceholder')} />
          <Input label={t('importExport.opnsense.apiKeyLabel')} value={opnsenseApiKey} onChange={(e) => setOpnsenseApiKey(e.target.value)} placeholder={t('importExport.opnsense.apiKeyLabel')} />
          <Input label={t('importExport.opnsense.apiSecretLabel')} type="password" value={opnsenseApiSecret} onChange={(e) => setOpnsenseApiSecret(e.target.value)} placeholder={t('importExport.opnsense.apiSecretLabel')} />
        </div>
      </DetailSection>

      {testResult && (
        <DetailSection 
          title={t('importExport.opnsense.connectionResult')} 
          icon={testResult.success ? CheckCircle : Key} 
          iconClass={testResult.success ? 'icon-bg-emerald' : 'icon-bg-orange'}
        >
          {testResult.success ? (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-status-success">
                <CheckCircle size={18} weight="fill" />
                <span className="text-sm font-medium">{t('importExport.opnsense.connectedSuccessfully')}</span>
              </div>
              {testResult.stats && (
                <div className="flex gap-4">
                  <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-bg-secondary">
                    <ShieldCheck size={16} className="text-accent-primary" />
                    <span className="text-sm font-medium">{testResult.stats.cas} CA{testResult.stats.cas > 1 ? 's' : ''}</span>
                  </div>
                  <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-bg-secondary">
                    <Certificate size={16} className="text-accent-primary" />
                    <span className="text-sm font-medium">{testResult.stats.certificates} {t('common.certificates')}</span>
                  </div>
                </div>
              )}
              {testItems.length > 0 && (
                <div className="border border-border rounded-lg overflow-hidden">
                  <div className="flex items-center justify-between px-3 py-2 bg-bg-secondary border-b border-border">
                    <label className="flex items-center gap-2 text-sm font-medium cursor-pointer">
                      <input type="checkbox" checked={testItems.every(i => i.selected)} onChange={(e) => toggleAllItems(e.target.checked)} className="w-4 h-4 rounded border-border text-accent-primary" />
                      {t('importExport.opnsense.selectAll')} ({testItems.filter(i => i.selected).length}/{testItems.length})
                    </label>
                  </div>
                  <div className="max-h-64 overflow-y-auto divide-y divide-border">
                    {testItems.map(item => (
                      <label key={item.id} className="flex items-center gap-3 px-3 py-2 hover:bg-bg-secondary cursor-pointer transition-colors">
                        <input type="checkbox" checked={item.selected} onChange={() => toggleItemSelection(item.id)} className="w-4 h-4 rounded border-border text-accent-primary shrink-0" />
                        <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase shrink-0 ${item.type === 'CA' ? 'bg-accent-primary/15 text-accent-primary' : 'bg-status-info/15 text-status-info'}`}>
                          {item.type}
                        </span>
                        <span className="text-sm truncate">{item.name || t('common.unnamed')}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-sm text-status-danger">{testResult.error || t('importExport.opnsense.connectionFailed')}</div>
          )}
        </DetailSection>
      )}

      <div className="flex gap-3 pt-2">
        <Button variant="secondary" onClick={handleTestConf} disabled={processing || !opnsenseHost || !opnsenseApiKey || !opnsenseApiSecret} size="lg">
          {processing ? t('common.testing') : t('common.testConnection')}
        </Button>
        {testResult?.success && testItems.some(i => i.selected) && (
          <Button onClick={handleImportFromOpnsense} disabled={processing} size="lg">
            <UploadSimple size={18} />
            {t('importExport.opnsense.importSelected', { count: testItems.filter(i => i.selected).length })}
          </Button>
        )}
      </div>
    </div>
  )

  const renderExportTab = () => (
    <div className="max-w-3xl mx-auto space-y-6">
      <DetailSection title={t('importExport.export.allCertsTitle')} icon={Certificate} iconClass="icon-bg-blue" description={t('importExport.export.allCertsDesc')}>
        <div className="grid grid-cols-2 gap-3">
          <Button variant="secondary" onClick={() => handleExport(certificatesService.exportAll, 'pem', 'certificates')} className="justify-center">
            <DownloadSimple size={16} /> {t('importExport.export.pemBundle')}
          </Button>
          <Button onClick={() => handleExport(certificatesService.exportAll, 'pkcs7', 'certificates')} className="justify-center">
            <DownloadSimple size={16} /> {t('importExport.export.p7bBundle')}
          </Button>
        </div>
      </DetailSection>

      <DetailSection title={t('importExport.export.allCAsTitle')} icon={ShieldCheck} iconClass="icon-bg-green" description={t('importExport.export.allCAsDesc', { count: cas.length })}>
        <div className="grid grid-cols-2 gap-3">
          <Button variant="secondary" onClick={() => handleExport(casService.exportAll, 'pem', 'ca-certificates')} className="justify-center">
            <DownloadSimple size={16} /> {t('importExport.export.pemBundle')}
          </Button>
          <Button onClick={() => handleExport(casService.exportAll, 'pkcs7', 'ca-certificates')} className="justify-center">
            <DownloadSimple size={16} /> {t('importExport.export.p7bBundle')}
          </Button>
        </div>
      </DetailSection>
    </div>
  )

  // Render item for basket/transfer view — compact row per resource type
  const renderBasketItem = useCallback((item) => {
    const type = bulkResourceType
    if (type === 'certificates') {
      const name = item.cn || item.common_name || extractCN(item.subject) || item.descr || '?'
      const status = item.revoked ? 'revoked' : item.status || 'unknown'
      const statusColors = { valid: 'text-accent-success', expiring: 'text-accent-warning', expired: 'text-accent-danger', revoked: 'text-accent-danger' }
      return (
        <div className="flex items-center gap-2">
          <div className={cn("w-6 h-6 rounded-md flex items-center justify-center shrink-0", item.has_private_key ? "icon-bg-emerald" : "icon-bg-blue")}>
            <Certificate size={12} weight="duotone" />
          </div>
          <span className="text-sm font-medium truncate flex-1">{name}</span>
          <span className={cn("text-[10px] font-medium uppercase", statusColors[status] || 'text-text-tertiary')}>{status}</span>
        </div>
      )
    }
    if (type === 'cas') {
      return (
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md flex items-center justify-center shrink-0 icon-bg-green">
            <ShieldCheck size={12} weight="duotone" />
          </div>
          <span className="text-sm font-medium truncate">{item.descr || extractCN(item.subject) || '—'}</span>
        </div>
      )
    }
    if (type === 'csrs') {
      return (
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md flex items-center justify-center shrink-0 icon-bg-amber">
            <FileText size={12} weight="duotone" />
          </div>
          <span className="text-sm font-medium truncate">{item.descr || extractCN(item.subject) || '—'}</span>
        </div>
      )
    }
    if (type === 'templates') {
      return (
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md flex items-center justify-center shrink-0 icon-bg-violet">
            <PencilSimple size={12} weight="duotone" />
          </div>
          <span className="text-sm font-medium truncate flex-1">{item.name || '—'}</span>
          <span className="text-[10px] text-text-tertiary">{item.key_type}</span>
        </div>
      )
    }
    if (type === 'users') {
      const avatarColors = { admin: 'icon-bg-violet', operator: 'icon-bg-blue', viewer: 'icon-bg-teal' }
      return (
        <div className="flex items-center gap-2">
          <div className={cn("w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0", avatarColors[item.role] || 'icon-bg-teal')}>
            {item.username?.charAt(0)?.toUpperCase() || '?'}
          </div>
          <span className="text-sm font-medium truncate flex-1">{item.username || '—'}</span>
          <span className="text-[10px] text-text-tertiary">{item.role}</span>
        </div>
      )
    }
    return <span className="text-sm truncate">{item.name || item.descr || item.username || '—'}</span>
  }, [bulkResourceType])

  const renderBulkTab = () => (
    <div className="flex flex-col h-full min-h-0">
      {/* Resource type selector + view toggle */}
      <div className="flex items-center gap-2 flex-wrap shrink-0 px-4 md:px-6 pt-3 pb-2">
        {Object.entries(RESOURCE_TYPES).map(([key, config]) => {
          const Icon = config.icon
          return (
            <button
              key={key}
              onClick={() => { setBulkResourceType(key); setStatusFilter(''); setCaFilter(''); setSelectedIds(new Set()) }}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                bulkResourceType === key 
                  ? 'bg-accent-primary text-white shadow-sm' 
                  : 'bg-bg-secondary text-text-secondary hover:bg-bg-tertiary hover:text-text-primary'
              }`}
            >
              <Icon size={16} />
              {t(`common.${key}`, key.charAt(0).toUpperCase() + key.slice(1))}
              <Badge variant="secondary" size="sm">{key === bulkResourceType ? filteredBulkData.length : ''}</Badge>
            </button>
          )
        })}

        {/* View mode toggle */}
        <div className="ml-auto flex items-center bg-bg-secondary rounded-lg p-0.5 border border-border">
          <button
            onClick={() => setBulkViewMode('table')}
            className={cn(
              "p-1.5 rounded-md transition-all",
              bulkViewMode === 'table' ? "bg-accent-primary text-white shadow-sm" : "text-text-secondary hover:text-text-primary"
            )}
            title={t('operations.tableView', 'Table View')}
          >
            <Table size={16} />
          </button>
          <button
            onClick={() => setBulkViewMode('basket')}
            className={cn(
              "p-1.5 rounded-md transition-all",
              bulkViewMode === 'basket' ? "bg-accent-primary text-white shadow-sm" : "text-text-secondary hover:text-text-primary"
            )}
            title={t('operations.basketView', 'Basket View')}
          >
            <ShoppingCart size={16} />
          </button>
        </div>
      </div>

      {/* Content area — table or basket */}
      <div className="flex-1 min-h-0">
        {bulkViewMode === 'table' ? (
          <ResponsiveDataTable
            data={filteredBulkData}
            columns={resourceConfig.columns}
            multiSelect={true}
            selectedIds={selectedIds}
            onSelectionChange={setSelectedIds}
            bulkActions={renderBulkActionButtons()}
            searchable
            searchPlaceholder={t('common.search')}
            searchKeys={['cn', 'descr', 'name', 'subject', 'username', 'email', 'common_name']}
            sortable
            toolbarFilters={bulkToolbarFilters}
            loading={bulkLoading}
            pagination={true}
            defaultPerPage={25}
            emptyIcon={resourceConfig.icon}
            emptyTitle={t('operations.noData', 'No items found')}
            emptyDescription={t('operations.noDataDesc', 'Try adjusting your filters')}
          />
        ) : (
          <div className="h-full px-4 md:px-6 pb-2">
            <TransferPanel
              items={filteredBulkData}
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

  return (
    <ResponsiveLayout
      title={t('operations.title', 'Operations')}
      subtitle={t('operations.subtitle', 'Import, export & bulk actions')}
      icon={Lightning}
      tabs={TABS}
      activeTab={activeTab}
      onTabChange={setActiveTab}
      helpPageKey="operations"
    >
      {activeTab === 'bulk' ? (
        renderContent()
      ) : (
        <div className="p-4 md:p-6">
          {renderContent()}
        </div>
      )}

      {/* Confirm modal for bulk actions (not export/sign — they have their own) */}
      <ConfirmModal
        open={!!bulkAction && bulkAction !== 'export' && bulkAction !== 'sign'}
        onClose={() => setBulkAction(null)}
        onConfirm={executeBulkAction}
        title={t('operations.confirmBulk', 'Confirm Bulk Operation')}
        message={getConfirmMessage()}
        confirmLabel={bulkAction === 'delete' ? t('common.delete') : t('common.confirm', 'Confirm')}
        variant={bulkAction === 'delete' || bulkAction === 'revoke' ? 'danger' : 'primary'}
        loading={bulkProcessing}
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
                className="w-full px-3 py-2 rounded-lg border border-border bg-bg-primary text-text-primary"
              >
                <option value="">{t('common.selectCA', 'Select CA...')}</option>
                {cas.map(ca => (
                  <option key={ca.id} value={ca.id}>{ca.descr || ca.subject}</option>
                ))}
              </select>
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
