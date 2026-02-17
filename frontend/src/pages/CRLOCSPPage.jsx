/**
 * CRL & OCSP Management Page - Migrated to ResponsiveLayout
 * Certificate Revocation Lists and OCSP responder management
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { 
  FileX, ShieldCheck, ArrowsClockwise, Download, Copy,
  Database, Pulse, Calendar, Hash, XCircle,
  Info as LinkIcon
} from '@phosphor-icons/react'
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
import { usePermission } from '../hooks'
import { formatDate, cn } from '../lib/utils'
import { ERRORS, SUCCESS } from '../lib/messages'

export default function CRLOCSPPage() {
  const { t } = useTranslation()
  const { showSuccess, showError, showInfo } = useNotification()
  const { canWrite } = usePermission()
  
  const [loading, setLoading] = useState(true)
  const [cas, setCas] = useState([])
  const [crls, setCrls] = useState([])
  const [selectedCA, setSelectedCA] = useState(null)
  const [selectedCRL, setSelectedCRL] = useState(null)
  const [ocspStatus, setOcspStatus] = useState({ enabled: false, running: false })
  const [ocspStats, setOcspStats] = useState({ total_requests: 0, cache_hits: 0 })
  const [regenerating, setRegenerating] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  
  // Pagination state
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)

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
      
      setCas(casRes.data || [])
      setCrls(crlsRes.data || [])
      setOcspStatus(ocspStatusRes.data || { enabled: false, running: false })
      setOcspStats(ocspStatsRes.data || { total_requests: 0, cache_hits: 0 })
    } catch (error) {
      showError(error.message || ERRORS.LOAD_FAILED.CRL)
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
    loadCRLForCA(ca.id)
  }

  const handleRegenerateCRL = async () => {
    if (!selectedCA) return
    
    setRegenerating(true)
    try {
      await crlService.regenerate(selectedCA.id)
      showSuccess(SUCCESS.CRL.GENERATED)
      loadCRLForCA(selectedCA.id)
      loadData()
    } catch (error) {
      showError(error.message || ERRORS.LOAD_FAILED.CRL)
    } finally {
      setRegenerating(false)
    }
  }

  const handleToggleAutoRegen = async (ca) => {
    if (!canWrite('crl')) return
    try {
      const result = await crlService.toggleAutoRegen(ca.id, !ca.cdp_enabled)
      showSuccess(t(result.data.cdp_enabled ? 'crlOcsp.autoRegenEnabled' : 'crlOcsp.autoRegenDisabled', { name: ca.descr }))
      // Update local state
      setCas(prev => prev.map(c => c.id === ca.id ? { ...c, cdp_enabled: result.data.cdp_enabled } : c))
      if (selectedCA?.id === ca.id) {
        setSelectedCA(prev => ({ ...prev, cdp_enabled: result.data.cdp_enabled }))
      }
    } catch (error) {
      showError(error.message || t('crlOcsp.toggleAutoRegenFailed'))
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
    navigator.clipboard.writeText(text)
    showInfo(t('common.copied'))
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
        has_crl: !!crl
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

  // Table columns
  const columns = useMemo(() => [
    {
      key: 'descr',
      header: t('crlOcsp.caName'),
      priority: 1,
      sortable: true,
      render: (v, row) => (
        <div className="flex items-center gap-2">
          <div className={cn(
            "w-7 h-7 rounded-lg flex items-center justify-center shrink-0",
            row.has_crl ? 'icon-bg-emerald' : 'icon-bg-orange'
          )}>
            <FileX size={14} weight="duotone" />
          </div>
          <span className="font-medium truncate">{v || row.name}</span>
        </div>
      ),
      mobileRender: (v, row) => (
        <div className="flex items-center justify-between gap-2 w-full">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <div className={cn(
              "w-7 h-7 rounded-lg flex items-center justify-center shrink-0",
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
      key: 'has_crl',
      header: t('common.status'),
      priority: 2,
      hideOnMobile: true,
      render: (v) => (
        <Badge variant={v ? 'success' : 'orange'} size="sm" dot pulse={!v}>
          {v ? t('common.active') : t('crlOcsp.noCRL')}
        </Badge>
      )
    },
    {
      key: 'cdp_enabled',
      header: t('common.auto'),
      priority: 3,
      hideOnMobile: true,
      render: (v, row) => (
        <div onClick={(e) => e.stopPropagation()}>
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
      key: 'revoked_count',
      header: t('common.revoked'),
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
      header: t('common.updated'),
      priority: 3,
      hideOnMobile: true,
      mono: true,
      render: (v) => (
        <span className="text-text-secondary">
          {v ? formatDate(v, 'short') : '—'}
        </span>
      )
    }
  ], [canWrite, handleToggleAutoRegen, t])

  // Help content
  const helpContent = (
    <div className="p-4 space-y-4">
      {/* CRL Statistics */}
      <Card className="p-4 space-y-3 bg-gradient-to-br from-accent-primary/5 to-transparent">
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
        <div className="bg-bg-tertiary/40 rounded-lg p-2 text-center">
          <Hash size={14} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-sm font-semibold text-text-primary">{selectedCRL?.crl_number || '-'}</div>
          <div className="text-2xs text-text-tertiary">{t('crlOcsp.crlNumber')}</div>
        </div>
        <div className="bg-bg-tertiary/40 rounded-lg p-2 text-center">
          <XCircle size={14} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-sm font-semibold text-text-primary">{selectedCRL?.revoked_count || 0}</div>
          <div className="text-2xs text-text-tertiary">{t('common.revoked')}</div>
        </div>
        <div className="bg-bg-tertiary/40 rounded-lg p-2 text-center">
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
          <Button size="sm" variant="secondary" onClick={handleDownloadCRL}>
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
            value={ocspStatus.enabled ? (ocspStatus.running ? t('common.running') : t('crlOcsp.stopped')) : t('common.disabled')} 
          />
          <CompactField autoIcon="totalRequests" label={t('crlOcsp.totalRequests')} value={ocspStats.total_requests} />
          <CompactField autoIcon="cacheHits" label={t('crlOcsp.cacheHits')} value={ocspStats.cache_hits} />
          <CompactField autoIcon="hitRate" label={t('crlOcsp.hitRate')} value={`${cacheHitRate}%`} />
        </CompactGrid>
      </CompactSection>

      {/* Distribution Points */}
      <CompactSection title={t('crlOcsp.cdpNote')} icon={LinkIcon}>
        <div className="space-y-3">
          <div>
            <p className="text-xs text-text-secondary mb-1">{t('crlOcsp.cdp')}</p>
            <div className="flex items-center gap-2">
              <code className="flex-1 text-xs font-mono text-text-primary bg-bg-tertiary p-2 rounded break-all">
                {`${window.location.origin}/crl/${selectedCA.refid}.crl`}
              </code>
              <Button size="sm" variant="ghost" onClick={() => copyToClipboard(`${window.location.origin}/crl/${selectedCA.refid}.crl`)}>
                <Copy size={14} />
              </Button>
            </div>
          </div>
          <div>
            <p className="text-xs text-text-secondary mb-1">{t('crlOcsp.aia')}</p>
            <div className="flex items-center gap-2">
              <code className="flex-1 text-xs font-mono text-text-primary bg-bg-tertiary p-2 rounded break-all">
                {`${window.location.origin}/ocsp/${selectedCA.refid}`}
              </code>
              <Button size="sm" variant="ghost" onClick={() => copyToClipboard(`${window.location.origin}/ocsp/${selectedCA.refid}`)}>
                <Copy size={14} />
              </Button>
            </div>
          </div>
          <p className="text-xs text-text-tertiary">
            {t('crlOcsp.includeURLsNote')}
          </p>
        </div>
      </CompactSection>
    </div>
  )

  // Header actions
  const headerActions = (
    <>
      <Button variant="secondary" size="sm" onClick={loadData} className="hidden md:inline-flex">
        <ArrowsClockwise size={14} />
      </Button>
      <Button variant="secondary" size="lg" onClick={loadData} className="md:hidden h-11 w-11 p-0">
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
            <Button variant="secondary" size="sm" onClick={loadData} className="hidden md:inline-flex">
              <ArrowsClockwise size={14} />
            </Button>
            <Button variant="secondary" size="lg" onClick={loadData} className="md:hidden h-11 w-11 p-0">
              <ArrowsClockwise size={22} />
            </Button>
          </>
        }
        selectedId={selectedCA?.id}
        onRowClick={handleSelectCA}
        sortable
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
