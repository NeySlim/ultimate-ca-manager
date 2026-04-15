/**
 * CRL & OCSP Management Page - Migrated to ResponsiveLayout
 * Certificate Revocation Lists and OCSP responder management
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { 
  FileX, ShieldCheck, ArrowsClockwise, Download, Copy,
  Database, Pulse, Calendar, Hash, XCircle,
  Info as LinkIcon, TreeStructure, Link as LinkChain,
  Plus, Trash, Certificate as CertificateIcon
} from '@phosphor-icons/react'
import { Tooltip } from '../components'
import {
  ResponsiveLayout,
  ResponsiveDataTable,
  Button, Card, Badge, 
  LoadingSpinner, StatusIndicator, HelpCard,
  CompactSection, CompactGrid, CompactField
} from '../components'
import { ToggleSwitch } from '../components/ui/ToggleSwitch'
import { casService, crlService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useClipboard } from '../hooks'
import { formatDate, cn } from '../lib/utils'
export default function CRLOCSPPage() {
  const { t } = useTranslation()
  const { showSuccess, showError, showInfo } = useNotification()
  const { canWrite } = usePermission()
  const { copy: clipboardCopy } = useClipboard()
  
  const [loading, setLoading] = useState(true)
  const [cas, setCas] = useState([])
  const [crls, setCrls] = useState([])
  const [selectedCA, setSelectedCA] = useState(null)
  const [selectedCRL, setSelectedCRL] = useState(null)
  const [ocspStatus, setOcspStatus] = useState({ enabled: false, running: false })
  const [ocspStats, setOcspStats] = useState({ total_requests: 0, cache_hits: 0 })
  const [regenerating, setRegenerating] = useState(false)
  const [deltaRegenerating, setDeltaRegenerating] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  
  // Pagination state
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)

  // URL editing state
  const [newUrlField, setNewUrlField] = useState({ type: null, value: '' })
  const [savingUrls, setSavingUrls] = useState(false)

  // Delegated OCSP responder state
  const [ocspResponder, setOcspResponder] = useState(null)
  const [eligibleResponders, setEligibleResponders] = useState([])
  const [loadingResponder, setLoadingResponder] = useState(false)
  const [eligibleLoaded, setEligibleLoaded] = useState(false)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [casRes, crlsRes, ocspStatusRes, ocspStatsRes] = await Promise.all([
        casService.getAll(),
        crlService.getAll(),
        crlService.getOcspStatus(),
        crlService.getOcspStats()
      ])
      
      const casData = casRes.data || []
      setCas(casData)
      setCrls(crlsRes.data || [])
      setOcspStatus(ocspStatusRes.data || { enabled: false, running: false })
      setOcspStats(ocspStatsRes.data || { total_requests: 0, cache_hits: 0 })
      
      // Re-select the current CA to sync updated data
      if (selectedCA) {
        const updated = casData.find(c => c.id === selectedCA.id)
        if (updated) setSelectedCA(updated)
      }
    } catch (error) {
      showError(error.message || t('messages.errors.loadFailed.crl'))
    } finally {
      setLoading(false)
    }
  }

  const loadCRLForCA = async (caId) => {
    try {
      const response = await crlService.getForCA(caId)
      setSelectedCRL(response.data || null)
    } catch (error) {
      setSelectedCRL(null)
    }
  }

  const handleSelectCA = (ca) => {
    setSelectedCA(ca)
    setOcspResponder(null)
    setEligibleResponders([])
    setEligibleLoaded(false)
    loadCRLForCA(ca.id)
    crlService.getOcspResponder(ca.id).then(res => {
      setOcspResponder(res.data?.responder || null)
    }).catch(() => setOcspResponder(null))
  }

  const handleAssignResponder = async (certId) => {
    try {
      await crlService.setOcspResponder(selectedCA.id, certId)
      showSuccess(t('crlOcsp.delegatedResponderSet'))
      const res = await crlService.getOcspResponder(selectedCA.id)
      setOcspResponder(res.data?.responder || null)
    } catch (error) {
      showError(error.message || t('crlOcsp.delegatedResponderFailed'))
    }
  }

  const handleRemoveResponder = async () => {
    try {
      await crlService.removeOcspResponder(selectedCA.id)
      showSuccess(t('crlOcsp.delegatedResponderRemoved'))
      setOcspResponder(null)
    } catch (error) {
      showError(error.message || t('crlOcsp.delegatedResponderRemoveFailed'))
    }
  }

  const handleLoadEligible = async () => {
    setLoadingResponder(true)
    try {
      const res = await crlService.getEligibleOcspResponders(selectedCA.id)
      setEligibleResponders(res.data || [])
      setEligibleLoaded(true)
    } catch {
      setEligibleResponders([])
      setEligibleLoaded(true)
    } finally {
      setLoadingResponder(false)
    }
  }

  const handleRegenerateCRL = async () => {
    if (!selectedCA) return
    
    setRegenerating(true)
    try {
      await crlService.regenerate(selectedCA.id)
      showSuccess(t('messages.success.crl.generated'))
      loadCRLForCA(selectedCA.id)
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.loadFailed.crl'))
    } finally {
      setRegenerating(false)
    }
  }

  const handleToggleAutoRegen = async (ca) => {
    if (!canWrite('crl')) return
    try {
      const result = await crlService.toggleAutoRegen(ca.id, !ca.cdp_enabled)
      const updated = result.data || result
      showSuccess(t(updated.cdp_enabled ? 'crlOcsp.autoRegenEnabled' : 'crlOcsp.autoRegenDisabled', { name: ca.descr }))
      setCas(prev => prev.map(c => c.id === ca.id ? { ...c, ...updated } : c))
      if (selectedCA?.id === ca.id) {
        setSelectedCA(prev => ({ ...prev, ...updated }))
      }
    } catch (error) {
      showError(error.message || t('crlOcsp.toggleAutoRegenFailed'))
    }
  }

  const handleToggleDeltaCRL = async (ca) => {
    if (!canWrite('crl')) return
    try {
      const newEnabled = !ca.delta_crl_enabled
      await crlService.configureDelta(ca.id, { enabled: newEnabled })
      showSuccess(t(newEnabled ? 'crlOcsp.deltaCrlEnabled' : 'crlOcsp.deltaCrlDisabled'))
      loadData()
    } catch (error) {
      showError(error.message || t('crlOcsp.deltaCrlToggleFailed'))
    }
  }

  const handleGenerateDelta = async (ca) => {
    if (!canWrite('crl')) return
    try {
      setDeltaRegenerating(true)
      await crlService.generateDelta(ca.id)
      showSuccess(t('crlOcsp.deltaCrlGenerated'))
      loadData()
    } catch (error) {
      showError(error.message || t('crlOcsp.deltaCrlGenerateFailed'))
    } finally {
      setDeltaRegenerating(false)
    }
  }

  const handleDeltaIntervalChange = async (ca, interval) => {
    if (!canWrite('crl')) return
    try {
      await crlService.configureDelta(ca.id, { interval: parseInt(interval) })
      showSuccess(t('crlOcsp.deltaIntervalUpdated'))
      loadData()
    } catch (error) {
      showError(error.message || t('crlOcsp.deltaIntervalFailed'))
    }
  }

  const handleToggleOcsp = async (ca) => {
    if (!canWrite('crl')) return
    try {
      const newVal = !ca.ocsp_enabled
      const result = await casService.update(ca.id, { ocsp_enabled: newVal })
      const updated = result.data || result
      showSuccess(t(newVal ? 'crlOcsp.ocspEnabled' : 'crlOcsp.ocspDisabled', { name: ca.descr }))
      setCas(prev => prev.map(c => c.id === ca.id ? { ...c, ...updated } : c))
      if (selectedCA?.id === ca.id) {
        setSelectedCA(prev => ({ ...prev, ...updated }))
      }
      loadData()
    } catch (error) {
      showError(error.message || t('crlOcsp.toggleOcspFailed'))
    }
  }

  const handleToggleAiaIssuers = async (ca) => {
    if (!canWrite('crl')) return
    try {
      const newVal = !ca.aia_ca_issuers_enabled
      const result = await casService.update(ca.id, { aia_ca_issuers_enabled: newVal })
      const updated = result.data || result
      showSuccess(t(newVal ? 'crlOcsp.aiaIssuersEnabled' : 'crlOcsp.aiaIssuersDisabled', { name: ca.descr }))
      setCas(prev => prev.map(c => c.id === ca.id ? { ...c, ...updated } : c))
      if (selectedCA?.id === ca.id) {
        setSelectedCA(prev => ({ ...prev, ...updated }))
      }
      loadData()
    } catch (error) {
      showError(error.message || t('crlOcsp.toggleAiaFailed'))
    }
  }

  const handleDownloadCRL = () => {
    if (!selectedCRL?.crl_pem) return
    
    const blob = new Blob([selectedCRL.crl_pem], { type: 'application/x-pem-file' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${selectedCA?.descr || 'crl'}.crl`
    a.click()
    URL.revokeObjectURL(url)
  }

  const copyToClipboard = (text) => {
    clipboardCopy(text)
    showSuccess(t('common.copied'))
  }

  // URL management (multi-URL support)
  const handleAddUrl = async (urlType) => {
    const url = newUrlField.value.trim()
    if (!url || !selectedCA) return
    setSavingUrls(true)
    try {
      const fieldMap = { cdp: 'cdp_urls', ocsp: 'ocsp_urls', aia: 'aia_ca_issuers_urls' }
      const currentMap = { cdp: selectedCA.cdp_urls || [], ocsp: selectedCA.ocsp_urls || [], aia: selectedCA.aia_ca_issuers_urls || [] }
      const updated = [...currentMap[urlType], url]
      await casService.update(selectedCA.id, { [fieldMap[urlType]]: updated })
      setNewUrlField({ type: null, value: '' })
      showSuccess(t('common.saved'))
      await loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.saveFailed'))
    } finally {
      setSavingUrls(false)
    }
  }

  const handleRemoveUrl = async (urlType, index) => {
    if (!selectedCA) return
    setSavingUrls(true)
    try {
      const fieldMap = { cdp: 'cdp_urls', ocsp: 'ocsp_urls', aia: 'aia_ca_issuers_urls' }
      const currentMap = { cdp: selectedCA.cdp_urls || [], ocsp: selectedCA.ocsp_urls || [], aia: selectedCA.aia_ca_issuers_urls || [] }
      const updated = currentMap[urlType].filter((_, i) => i !== index)
      await casService.update(selectedCA.id, { [fieldMap[urlType]]: updated })
      showSuccess(t('common.saved'))
      await loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.saveFailed'))
    } finally {
      setSavingUrls(false)
    }
  }

  const handleCpsUpdate = async (field, value) => {
    if (!selectedCA) return
    setSavingUrls(true)
    try {
      await casService.update(selectedCA.id, { [field]: value })
      showSuccess(t('common.saved'))
      await loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.saveFailed'))
    } finally {
      setSavingUrls(false)
    }
  }

  // Calculate stats
  const totalRevoked = crls.reduce((sum, crl) => sum + (crl.revoked_count || 0), 0)
  const cacheHitRate = ocspStats.total_requests > 0 
    ? Math.round((ocspStats.cache_hits / ocspStats.total_requests) * 100) 
    : 0

  // Merge CAs with CRL info
  const casWithCRL = useMemo(() => {
    return cas.map(ca => {
      const crl = crls.find(c => c.ca_id === ca.id || c.caref === ca.refid)
      return {
        ...ca,
        crl_number: crl?.crl_number,
        revoked_count: crl?.revoked_count || 0,
        crl_updated: crl?.updated_at,
        crl_next_update: crl?.next_update,
        has_crl: !!crl,
        delta_crl: crl?.delta_crl || null
      }
    })
  }, [cas, crls])

  // Filter CAs
  const filteredCAs = useMemo(() => {
    if (!searchQuery) return casWithCRL
    return casWithCRL.filter(ca => 
      ca.descr?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      ca.name?.toLowerCase().includes(searchQuery.toLowerCase())
    )
  }, [casWithCRL, searchQuery])

  // Header stats
  const headerStats = useMemo(() => [
    { icon: ShieldCheck, label: t('common.cas'), value: cas.length },
    { icon: FileX, label: t('crlOcsp.crl'), value: crls.length, variant: 'info' },
    { icon: XCircle, label: t('common.revoked'), value: totalRevoked, variant: 'danger' },
    { icon: Pulse, label: t('common.ocspResponder'), value: ocspStatus.running ? t('common.online') : t('common.offline'), variant: ocspStatus.running ? 'success' : 'warning' }
  ], [cas.length, crls.length, totalRevoked, ocspStatus.running, t])

  // Icon-only header with tooltip (language-independent, compact)
  const iconHeader = (icon, label) => (
    <Tooltip content={label} side="top">
      <span className="inline-flex items-center justify-center cursor-help">
        {icon}
      </span>
    </Tooltip>
  )

  // Table columns — compact icon headers for toggles, merged updates column
  const columns = useMemo(() => [
    {
      key: 'descr',
      header: t('crlOcsp.caName'),
      priority: 1,
      sortable: true,
      render: (v, row) => (
        <div className="flex items-center gap-2">
          <div className={cn(
            "w-6 h-6 rounded-lg flex items-center justify-center shrink-0",
            row.has_crl ? 'icon-bg-emerald' : 'icon-bg-orange'
          )}>
            <FileX size={14} weight="duotone" />
          </div>
          <span className="font-medium truncate">{v || row.name}</span>
          {!row.has_crl && (
            <Badge variant="orange" size="sm" className="shrink-0">
              {t('crlOcsp.noCRL')}
            </Badge>
          )}
        </div>
      ),
      mobileRender: (v, row) => (
        <div className="flex items-center justify-between gap-2 w-full">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <div className={cn(
              "w-6 h-6 rounded-lg flex items-center justify-center shrink-0",
              row.has_crl ? 'icon-bg-emerald' : 'icon-bg-orange'
            )}>
              <FileX size={14} weight="duotone" />
            </div>
            <span className="font-medium truncate">{v || row.name}</span>
          </div>
          <Badge variant={row.has_crl ? 'success' : 'orange'} size="sm" dot pulse={!row.has_crl}>
            {row.has_crl ? t('common.active') : t('crlOcsp.noCRL')}
          </Badge>
        </div>
      )
    },
    {
      key: 'cdp_enabled',
      header: iconHeader(<ArrowsClockwise size={14} weight="duotone" className="text-text-tertiary" />, t('crlOcsp.autoRegen')),
      width: '48px',
      compact: true,
      priority: 3,
      hideOnMobile: true,
      sortable: false,
      render: (v, row) => (
        <div onClick={(e) => e.stopPropagation()} className="flex justify-center">
          <ToggleSwitch
            checked={v}
            onChange={() => handleToggleAutoRegen(row)}
            disabled={!row.has_private_key || !canWrite('crl')}
            size="sm"
          />
        </div>
      )
    },
    {
      key: 'delta_crl_enabled',
      header: iconHeader(<TreeStructure size={14} weight="duotone" className="text-text-tertiary" />, t('crlOcsp.deltaCrl')),
      width: '48px',
      compact: true,
      priority: 4,
      hideOnMobile: true,
      sortable: false,
      render: (v, row) => (
        <div onClick={(e) => e.stopPropagation()} className="flex justify-center">
          <ToggleSwitch
            checked={v || false}
            onChange={() => handleToggleDeltaCRL(row)}
            disabled={!row.has_private_key || !row.cdp_enabled || !canWrite('crl')}
            size="sm"
          />
        </div>
      )
    },
    {
      key: 'ocsp_enabled',
      header: iconHeader(<Pulse size={14} weight="duotone" className="text-text-tertiary" />, 'OCSP'),
      width: '48px',
      compact: true,
      priority: 3,
      hideOnMobile: true,
      sortable: false,
      render: (v, row) => (
        <div onClick={(e) => e.stopPropagation()} className="flex justify-center">
          <ToggleSwitch
            checked={v}
            onChange={() => handleToggleOcsp(row)}
            disabled={!row.has_private_key || !canWrite('crl')}
            size="sm"
          />
        </div>
      )
    },
    {
      key: 'aia_ca_issuers_enabled',
      header: iconHeader(<LinkChain size={14} weight="duotone" className="text-text-tertiary" />, t('crlOcsp.aiaIssuers')),
      width: '48px',
      compact: true,
      priority: 5,
      hideOnMobile: true,
      sortable: false,
      render: (v, row) => (
        <div onClick={(e) => e.stopPropagation()} className="flex justify-center">
          <ToggleSwitch
            checked={v || false}
            onChange={() => handleToggleAiaIssuers(row)}
            disabled={!row.has_private_key || !canWrite('crl')}
            size="sm"
          />
        </div>
      )
    },
    {
      key: 'cps_enabled',
      header: iconHeader(<CertificateIcon size={14} weight="duotone" className="text-text-tertiary" />, 'CPS'),
      width: '48px',
      compact: true,
      priority: 6,
      hideOnMobile: true,
      sortable: false,
      render: (v) => (
        <div className="flex justify-center">
          <StatusIndicator status={v ? 'active' : 'inactive'} size="sm" showLabel={false} />
        </div>
      )
    },
    {
      key: 'revoked_count',
      header: t('common.revoked'),
      width: '80px',
      priority: 2,
      render: (v) => (
        <Badge variant={v > 0 ? 'danger' : 'secondary'} size="sm" dot={v > 0}>
          {v || 0}
        </Badge>
      ),
      mobileRender: (v) => (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-text-tertiary">{t('common.revoked')}:</span>
          <Badge variant={v > 0 ? 'danger' : 'secondary'} size="sm" dot={v > 0}>
            {v || 0}
          </Badge>
        </div>
      )
    },
    {
      key: 'crl_updated',
      header: t('crlOcsp.updates'),
      priority: 3,
      hideOnMobile: true,
      size: 2,
      render: (v, row) => {
        const nextUpdate = row.crl_next_update
        const isExpired = nextUpdate && new Date(nextUpdate) < new Date()
        return (
          <div className="flex flex-col gap-0.5 text-xs leading-tight">
            <span className="text-text-secondary">
              {v ? formatDate(v, 'short') : '—'}
            </span>
            {nextUpdate && (
              <span className={cn(
                'text-2xs',
                isExpired ? 'text-red-500 font-medium' : 'text-text-tertiary'
              )}>
                → {formatDate(nextUpdate, 'short')}
              </span>
            )}
          </div>
        )
      }
    }
  ], [canWrite, handleToggleAutoRegen, handleToggleDeltaCRL, handleToggleOcsp, handleToggleAiaIssuers, t])

  // Help content
  const helpContent = (
    <div className="p-4 space-y-4">
      {/* CRL Statistics */}
      <Card className="p-4 space-y-3 bg-gradient-to-br from-accent-primary-op5 to-transparent">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Database size={16} className="text-accent-primary" />
          {t('crlOcsp.crlStatistics')}
        </h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-text-primary">{crls.length}</p>
            <p className="text-xs text-text-secondary">{t('crlOcsp.activeCRLs')}</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-status-danger">{totalRevoked}</p>
            <p className="text-xs text-text-secondary">{t('crlOcsp.revokedCerts')}</p>
          </div>
        </div>
      </Card>

      {/* OCSP Status */}
      <Card className={`p-4 space-y-3 ${ocspStatus.enabled ? 'stat-card-success' : 'stat-card-warning'}`}>
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Pulse size={16} className="text-accent-primary" />
          {t('common.ocspResponder')}
        </h3>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">{t('common.status')}</span>
            <StatusIndicator status={ocspStatus.enabled && ocspStatus.running ? 'success' : 'warning'}>
              {ocspStatus.enabled ? (ocspStatus.running ? t('common.running') : t('crlOcsp.stopped')) : t('common.disabled')}
            </StatusIndicator>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">{t('crlOcsp.totalRequests')}</span>
            <span className="text-sm font-medium text-text-primary">{ocspStats.total_requests}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">{t('crlOcsp.cacheHitRate')}</span>
            <span className="text-sm font-medium text-text-primary">{cacheHitRate}%</span>
          </div>
        </div>
      </Card>

      {/* Help Cards */}
      <div className="space-y-3">
        <HelpCard variant="info" title={t('common.aboutCRLs')}>
          {t('crlOcsp.crlDescription')}
        </HelpCard>
        
        <HelpCard variant="tip" title={t('crlOcsp.ocspVsCRL')}>
          {t('crlOcsp.ocspVsCRLDescription')}
        </HelpCard>

        <HelpCard variant="warning" title={t('crlOcsp.cdpNote')}>
          {t('crlOcsp.cdpNoteDescription')}
        </HelpCard>
      </div>
    </div>
  )

  // Detail slide-over content
  const detailContent = selectedCA && (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 pb-3 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg status-primary-bg flex items-center justify-center">
            <FileX size={20} className="text-accent-primary" weight="duotone" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-text-primary">{selectedCA.descr || selectedCA.name}</h3>
            <p className="text-xs text-text-secondary">{t('crlOcsp.crlDetails')}</p>
          </div>
        </div>
        <Badge variant={selectedCRL ? 'success' : 'warning'} size="sm" dot>
          {selectedCRL ? t('common.active') : t('crlOcsp.noCRL')}
        </Badge>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-3 gap-2">
        <div className="bg-tertiary-op40 rounded-lg p-2 text-center">
          <Hash size={14} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-sm font-semibold text-text-primary">{selectedCRL?.crl_number || '-'}</div>
          <div className="text-2xs text-text-tertiary">{t('crlOcsp.crlNumber')}</div>
        </div>
        <div className="bg-tertiary-op40 rounded-lg p-2 text-center">
          <XCircle size={14} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-sm font-semibold text-text-primary">{selectedCRL?.revoked_count || 0}</div>
          <div className="text-2xs text-text-tertiary">{t('common.revoked')}</div>
        </div>
        <div className="bg-tertiary-op40 rounded-lg p-2 text-center">
          <Calendar size={14} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-sm font-semibold text-text-primary">{selectedCRL?.updated_at ? formatDate(selectedCRL.updated_at, 'short') : '-'}</div>
          <div className="text-2xs text-text-tertiary">{t('common.updated')}</div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-2">
        {canWrite('crl') && selectedCA.has_private_key !== false && (
          <Button 
            size="sm" 
            variant="primary" 
            onClick={handleRegenerateCRL}
            disabled={regenerating}
            className="flex-1"
          >
            <ArrowsClockwise size={14} className={regenerating ? 'animate-spin' : ''} />
            {regenerating ? t('crlOcsp.regenerating') : t('crlOcsp.regenerateCRL')}
          </Button>
        )}
        {selectedCRL?.crl_pem && (
          <Button type="button" size="sm" variant="secondary" onClick={handleDownloadCRL}>
            <Download size={14} />
            {t('common.download')}
          </Button>
        )}
      </div>

      {/* CRL Configuration */}
      <CompactSection title={t('crlOcsp.crlConfig')} icon={LinkIcon}>
        <CompactGrid cols={2}>
          <CompactField autoIcon="caName" label={t('crlOcsp.caName')} value={selectedCA.descr || selectedCA.name} />
          <CompactField autoIcon="status" label={t('common.status')} value={selectedCRL ? t('common.active') : t('crlOcsp.noCRL')} />
          <CompactField autoIcon="crlNumber" label={t('crlOcsp.crlNumber')} value={selectedCRL?.crl_number || '-'} />
          <CompactField autoIcon="revokedCount" label={t('crlOcsp.revokedCount')} value={selectedCRL?.revoked_count || 0} />
          <CompactField autoIcon="lastUpdate" label={t('common.lastUpdate')} value={selectedCRL?.updated_at ? formatDate(selectedCRL.updated_at) : '-'} />
          <CompactField autoIcon="nextUpdate" label={t('crlOcsp.nextUpdate')} value={selectedCRL?.next_update ? formatDate(selectedCRL.next_update) : '-'} />
        </CompactGrid>
      </CompactSection>

      {/* OCSP Configuration */}
      <CompactSection title={t('crlOcsp.ocspConfig')} icon={Pulse}>
        <CompactGrid cols={2}>
          <CompactField 
            autoIcon="status" label={t('common.status')} 
            value={selectedCA.ocsp_enabled ? t('common.enabled') : t('common.disabled')} 
          />
          {selectedCA.ocsp_enabled && (selectedCA.ocsp_urls || []).length > 0 && (
            <CompactField autoIcon="url" label="OCSP URL" value={(selectedCA.ocsp_urls || [])[0]} mono />
          )}
          <CompactField autoIcon="totalRequests" label={t('crlOcsp.totalRequests')} value={ocspStats.total_requests} />
          <CompactField autoIcon="cacheHits" label={t('crlOcsp.cacheHits')} value={ocspStats.cache_hits} />
        </CompactGrid>
      </CompactSection>

      {/* Delegated OCSP Responder */}
      <CompactSection title={t('crlOcsp.delegatedResponder')} icon={ShieldCheck}>
        <p className="text-xs text-text-tertiary mb-3">
          {t('crlOcsp.delegatedResponderDescription')}
        </p>
        {ocspResponder ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2 p-2 rounded-md bg-bg-tertiary border border-border">
              <CertificateIcon size={16} className="text-accent-primary shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-text-primary truncate">{ocspResponder.common_name}</div>
                <div className="text-xs text-text-tertiary">
                  SN: {ocspResponder.serial_number} · {t('common.expires')}: {formatDate(ocspResponder.valid_to)}
                </div>
              </div>
              {canWrite('cas') && (
                <Button type="button" variant="danger" size="xs" onClick={handleRemoveResponder}>
                  <Trash size={14} />
                </Button>
              )}
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            <p className="text-xs text-text-tertiary italic">{t('crlOcsp.delegatedResponderNone')}</p>
            {canWrite('cas') && (
              <div className="space-y-2">
                {!eligibleLoaded ? (
                  <Button type="button" variant="secondary" size="sm" onClick={handleLoadEligible} disabled={loadingResponder}>
                    {t('crlOcsp.selectResponder')}
                  </Button>
                ) : eligibleResponders.length > 0 ? (
                  <select
                    className="w-full rounded-md border border-border bg-bg-primary text-text-primary text-sm p-2"
                    onChange={(e) => e.target.value && handleAssignResponder(parseInt(e.target.value))}
                    defaultValue=""
                  >
                    <option value="" disabled>{t('crlOcsp.selectResponder')}</option>
                    {eligibleResponders.map(cert => (
                      <option key={cert.id} value={cert.id}>
                        {cert.common_name} (SN: {cert.serial_number})
                      </option>
                    ))}
                  </select>
                ) : (
                  <p className="text-xs text-text-tertiary italic">{t('crlOcsp.noEligibleResponders')}</p>
                )}
              </div>
            )}
          </div>
        )}
      </CompactSection>

      {/* AIA CA Issuers Configuration */}
      <CompactSection title={t('crlOcsp.aiaIssuersConfig')} icon={LinkIcon}>
        <CompactGrid cols={2}>
          <CompactField 
            autoIcon="status" label={t('common.status')} 
            value={selectedCA.aia_ca_issuers_enabled ? t('common.enabled') : t('common.disabled')} 
          />
          {selectedCA.aia_ca_issuers_enabled && (selectedCA.aia_ca_issuers_urls || []).length > 0 && (
            <CompactField autoIcon="url" label={t('crlOcsp.aiaIssuersUrl')} value={(selectedCA.aia_ca_issuers_urls || [])[0]} mono />
          )}
        </CompactGrid>
      </CompactSection>

      {/* Distribution Points */}
      <CompactSection title={t('crlOcsp.cdpNote')} icon={LinkIcon}>
        <div className="space-y-3">
          {/* CDP URLs */}
          <div>
            <p className="text-xs font-medium text-text-secondary mb-1">{t('crlOcsp.cdp')}</p>
            {(selectedCA.cdp_urls || []).length > 0 ? (
              <div className="space-y-1">
                {(selectedCA.cdp_urls || []).map((url, idx) => (
                  <div key={idx} className="flex items-center gap-1">
                    <code className="flex-1 text-xs font-mono text-text-primary bg-bg-tertiary px-2 py-1.5 rounded break-all">
                      {url}
                    </code>
                    <Button type="button" size="sm" variant="ghost" onClick={() => copyToClipboard(url)} aria-label={t('common.copy')}>
                      <Copy size={14} />
                    </Button>
                    {canWrite('crl') && (
                      <Button type="button" size="sm" variant="ghost" className="text-red-500 hover:text-red-600" onClick={() => handleRemoveUrl('cdp', idx)} disabled={savingUrls} aria-label={t('common.remove')}>
                        <Trash size={14} />
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            ) : selectedCA.cdp_enabled ? (
              <p className="text-xs text-text-tertiary italic">{t('crlOcsp.urlNotConfigured')}</p>
            ) : null}
            {canWrite('crl') && selectedCA.cdp_enabled && (
              newUrlField.type === 'cdp' ? (
                <div className="flex items-center gap-1 mt-1">
                  <input
                    type="url"
                    className="flex-1 text-xs font-mono bg-bg-tertiary border border-border rounded px-2 py-1.5 text-text-primary"
                    placeholder="http://cdp.example.com/crl.pem"
                    value={newUrlField.value}
                    onChange={(e) => setNewUrlField({ type: 'cdp', value: e.target.value })}
                    onKeyDown={(e) => e.key === 'Enter' && handleAddUrl('cdp')}
                    autoFocus
                  />
                  <Button type="button" size="sm" onClick={() => handleAddUrl('cdp')} disabled={savingUrls || !newUrlField.value.trim()}>
                    <Plus size={14} />
                  </Button>
                  <Button type="button" size="sm" variant="ghost" onClick={() => setNewUrlField({ type: null, value: '' })}>
                    <XCircle size={14} />
                  </Button>
                </div>
              ) : (
                <Button type="button" size="sm" variant="ghost" className="mt-1 text-xs" onClick={() => setNewUrlField({ type: 'cdp', value: '' })}>
                  <Plus size={12} className="mr-1" /> {t('crlOcsp.addUrl')}
                </Button>
              )
            )}
          </div>

          {/* OCSP URLs */}
          <div>
            <p className="text-xs font-medium text-text-secondary mb-1">OCSP</p>
            {(selectedCA.ocsp_urls || []).length > 0 ? (
              <div className="space-y-1">
                {(selectedCA.ocsp_urls || []).map((url, idx) => (
                  <div key={idx} className="flex items-center gap-1">
                    <code className="flex-1 text-xs font-mono text-text-primary bg-bg-tertiary px-2 py-1.5 rounded break-all">
                      {url}
                    </code>
                    <Button type="button" size="sm" variant="ghost" onClick={() => copyToClipboard(url)} aria-label={t('common.copy')}>
                      <Copy size={14} />
                    </Button>
                    {canWrite('crl') && (
                      <Button type="button" size="sm" variant="ghost" className="text-red-500 hover:text-red-600" onClick={() => handleRemoveUrl('ocsp', idx)} disabled={savingUrls} aria-label={t('common.remove')}>
                        <Trash size={14} />
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            ) : selectedCA.ocsp_enabled ? (
              <p className="text-xs text-text-tertiary italic">{t('crlOcsp.urlNotConfigured')}</p>
            ) : null}
            {canWrite('crl') && selectedCA.ocsp_enabled && (
              newUrlField.type === 'ocsp' ? (
                <div className="flex items-center gap-1 mt-1">
                  <input
                    type="url"
                    className="flex-1 text-xs font-mono bg-bg-tertiary border border-border rounded px-2 py-1.5 text-text-primary"
                    placeholder="http://ocsp.example.com/"
                    value={newUrlField.value}
                    onChange={(e) => setNewUrlField({ type: 'ocsp', value: e.target.value })}
                    onKeyDown={(e) => e.key === 'Enter' && handleAddUrl('ocsp')}
                    autoFocus
                  />
                  <Button type="button" size="sm" onClick={() => handleAddUrl('ocsp')} disabled={savingUrls || !newUrlField.value.trim()}>
                    <Plus size={14} />
                  </Button>
                  <Button type="button" size="sm" variant="ghost" onClick={() => setNewUrlField({ type: null, value: '' })}>
                    <XCircle size={14} />
                  </Button>
                </div>
              ) : (
                <Button type="button" size="sm" variant="ghost" className="mt-1 text-xs" onClick={() => setNewUrlField({ type: 'ocsp', value: '' })}>
                  <Plus size={12} className="mr-1" /> {t('crlOcsp.addUrl')}
                </Button>
              )
            )}
          </div>

          {/* AIA CA Issuers URLs */}
          <div>
            <p className="text-xs font-medium text-text-secondary mb-1">{t('crlOcsp.aiaIssuers')}</p>
            {(selectedCA.aia_ca_issuers_urls || []).length > 0 ? (
              <div className="space-y-1">
                {(selectedCA.aia_ca_issuers_urls || []).map((url, idx) => (
                  <div key={idx} className="flex items-center gap-1">
                    <code className="flex-1 text-xs font-mono text-text-primary bg-bg-tertiary px-2 py-1.5 rounded break-all">
                      {url}
                    </code>
                    <Button type="button" size="sm" variant="ghost" onClick={() => copyToClipboard(url)} aria-label={t('common.copy')}>
                      <Copy size={14} />
                    </Button>
                    {canWrite('crl') && (
                      <Button type="button" size="sm" variant="ghost" className="text-red-500 hover:text-red-600" onClick={() => handleRemoveUrl('aia', idx)} disabled={savingUrls} aria-label={t('common.remove')}>
                        <Trash size={14} />
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            ) : selectedCA.aia_ca_issuers_enabled ? (
              <p className="text-xs text-text-tertiary italic">{t('crlOcsp.urlNotConfigured')}</p>
            ) : null}
            {canWrite('crl') && selectedCA.aia_ca_issuers_enabled && (
              newUrlField.type === 'aia' ? (
                <div className="flex items-center gap-1 mt-1">
                  <input
                    type="url"
                    className="flex-1 text-xs font-mono bg-bg-tertiary border border-border rounded px-2 py-1.5 text-text-primary"
                    placeholder="http://ca.example.com/ca.cer"
                    value={newUrlField.value}
                    onChange={(e) => setNewUrlField({ type: 'aia', value: e.target.value })}
                    onKeyDown={(e) => e.key === 'Enter' && handleAddUrl('aia')}
                    autoFocus
                  />
                  <Button type="button" size="sm" onClick={() => handleAddUrl('aia')} disabled={savingUrls || !newUrlField.value.trim()}>
                    <Plus size={14} />
                  </Button>
                  <Button type="button" size="sm" variant="ghost" onClick={() => setNewUrlField({ type: null, value: '' })}>
                    <XCircle size={14} />
                  </Button>
                </div>
              ) : (
                <Button type="button" size="sm" variant="ghost" className="mt-1 text-xs" onClick={() => setNewUrlField({ type: 'aia', value: '' })}>
                  <Plus size={12} className="mr-1" /> {t('crlOcsp.addUrl')}
                </Button>
              )
            )}
          </div>

          <p className="text-xs text-text-tertiary">
            {t('crlOcsp.includeURLsNote')}
          </p>
        </div>
      </CompactSection>

      {/* Certificate Policies / CPS */}
      <CompactSection title={t('crlOcsp.cpsTitle')} icon={CertificateIcon}>
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-primary">{t('crlOcsp.cpsEnabled')}</span>
            {canWrite('crl') ? (
              <ToggleSwitch
                checked={selectedCA.cps_enabled || false}
                onChange={(val) => handleCpsUpdate('cps_enabled', val)}
                disabled={savingUrls}
              />
            ) : (
              <Badge variant={selectedCA.cps_enabled ? 'success' : 'secondary'}>
                {selectedCA.cps_enabled ? t('common.enabled') : t('common.disabled')}
              </Badge>
            )}
          </div>
          {selectedCA.cps_enabled && (
            <>
              <div>
                <label className="text-xs text-text-secondary mb-1 block">{t('crlOcsp.cpsUri')}</label>
                <div className="flex items-center gap-1">
                  <input
                    type="url"
                    className="flex-1 text-xs font-mono bg-bg-tertiary border border-border rounded px-2 py-1.5 text-text-primary"
                    placeholder="http://ca.example.com/cps.pdf"
                    value={selectedCA.cps_uri || ''}
                    onChange={(e) => setSelectedCA({ ...selectedCA, cps_uri: e.target.value })}
                    onBlur={(e) => {
                      if (e.target.value !== (cas.find(c => c.id === selectedCA.id)?.cps_uri || '')) {
                        handleCpsUpdate('cps_uri', e.target.value)
                      }
                    }}
                    disabled={!canWrite('crl')}
                  />
                  {selectedCA.cps_uri && (
                    <Button type="button" size="sm" variant="ghost" onClick={() => copyToClipboard(selectedCA.cps_uri)} aria-label={t('common.copy')}>
                      <Copy size={14} />
                    </Button>
                  )}
                </div>
              </div>
              <div>
                <label className="text-xs text-text-secondary mb-1 block">{t('crlOcsp.cpsOid')}</label>
                <input
                  type="text"
                  className="w-full text-xs font-mono bg-bg-tertiary border border-border rounded px-2 py-1.5 text-text-primary"
                  placeholder="2.5.29.32.0"
                  value={selectedCA.cps_oid || '2.5.29.32.0'}
                  onChange={(e) => setSelectedCA({ ...selectedCA, cps_oid: e.target.value })}
                  onBlur={(e) => {
                    if (e.target.value !== (cas.find(c => c.id === selectedCA.id)?.cps_oid || '2.5.29.32.0')) {
                      handleCpsUpdate('cps_oid', e.target.value || '2.5.29.32.0')
                    }
                  }}
                  disabled={!canWrite('crl')}
                />
                <p className="text-xs text-text-tertiary mt-1">{t('crlOcsp.cpsOidNote')}</p>
              </div>
            </>
          )}
        </div>
      </CompactSection>

      {/* Delta CRL Section */}
      {selectedCA?.cdp_enabled && selectedCA?.delta_crl_enabled && (
        <div className="space-y-3 border-t border-border pt-4 mt-4">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-medium text-text-primary">{t('crlOcsp.deltaCrlTitle')}</h4>
            {canWrite('crl') && (
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() => handleGenerateDelta(selectedCA)}
                disabled={deltaRegenerating}
              >
                <ArrowsClockwise size={14} className={deltaRegenerating ? 'animate-spin' : ''} />
                {deltaRegenerating ? t('common.generating') : t('crlOcsp.generateDelta')}
              </Button>
            )}
          </div>
          
          {selectedCA?.delta_crl && (
            <CompactGrid cols={2}>
              <CompactField autoIcon="crlNumber" label={t('crlOcsp.deltaCrlNumber')} value={`#${selectedCA.delta_crl.crl_number}`} />
              <CompactField autoIcon="crlNumber" label={t('crlOcsp.baseCrlNumber')} value={`#${selectedCA.delta_crl.base_crl_number}`} />
              <CompactField autoIcon="revokedCount" label={t('crlOcsp.deltaEntries')} value={selectedCA.delta_crl.revoked_count} />
              <CompactField autoIcon="nextUpdate" label={t('crlOcsp.deltaNextUpdate')} value={selectedCA.delta_crl.next_update ? formatDate(selectedCA.delta_crl.next_update) : '-'} />
            </CompactGrid>
          )}
          
          <div className="flex items-center gap-2">
            <label htmlFor="delta-interval" className="text-xs text-text-secondary">{t('crlOcsp.deltaInterval')}</label>
            <select
              id="delta-interval"
              className="text-xs bg-bg-tertiary border border-border rounded px-2 py-1 text-text-primary"
              value={selectedCA?.delta_crl_interval || 4}
              onChange={(e) => handleDeltaIntervalChange(selectedCA, e.target.value)}
            >
              <option value="1">1h</option>
              <option value="2">2h</option>
              <option value="4">4h</option>
              <option value="8">8h</option>
              <option value="12">12h</option>
              <option value="24">24h</option>
            </select>
          </div>
        </div>
      )}
    </div>
  )

  // Header actions
  const headerActions = (
    <>
      <Button type="button" variant="secondary" size="sm" onClick={loadData} className="hidden md:inline-flex">
        <ArrowsClockwise size={14} />
      </Button>
      <Button type="button" variant="secondary" size="lg" onClick={loadData} className="md:hidden h-11 w-11 p-0">
        <ArrowsClockwise size={22} />
      </Button>
    </>
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner />
      </div>
    )
  }

  return (
    <ResponsiveLayout
      title={t('common.crlOcsp')}
      icon={FileX}
      subtitle={t('crlOcsp.subtitle', { count: crls.length })}
      stats={headerStats}
      helpPageKey="crlocsp"
      splitView={true}
      splitEmptyContent={
        <div className="h-full flex flex-col items-center justify-center p-6 text-center">
          <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
            <FileX size={24} className="text-text-tertiary" />
          </div>
          <p className="text-sm text-text-secondary">{t('crlOcsp.selectCA')}</p>
        </div>
      }
      slideOverOpen={!!selectedCA}
      onSlideOverClose={() => { setSelectedCA(null); setSelectedCRL(null); }}
      slideOverTitle={t('crlOcsp.crlDetails')}
      slideOverContent={detailContent}
      slideOverWidth="md"
    >
      <ResponsiveDataTable
        data={filteredCAs}
        columns={columns}
        keyField="id"
        searchable
        searchPlaceholder={t('common.searchPlaceholder')}
        searchKeys={['name', 'common_name', 'cn']}
        toolbarActions={
          <>
            <Button type="button" variant="secondary" size="sm" onClick={loadData} className="hidden md:inline-flex">
              <ArrowsClockwise size={14} />
            </Button>
            <Button type="button" variant="secondary" size="lg" onClick={loadData} className="md:hidden h-11 w-11 p-0">
              <ArrowsClockwise size={22} />
            </Button>
          </>
        }
        selectedId={selectedCA?.id}
        onRowClick={handleSelectCA}
        sortable
        densityStorageKey="ucm-crlocsp-density"
        pagination={{
          page,
          total: filteredCAs.length,
          perPage,
          onChange: setPage,
          onPerPageChange: (v) => { setPerPage(v); setPage(1) }
        }}
        emptyState={{
          icon: FileX,
          title: t('common.noCA'),
          description: t('crlOcsp.createCAFirst')
        }}
      />
    </ResponsiveLayout>
  )
}
