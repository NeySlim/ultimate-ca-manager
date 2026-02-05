/**
 * CRL & OCSP Management Page - Migrated to ResponsiveLayout
 * Certificate Revocation Lists and OCSP responder management
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import { 
  FileX, ShieldCheck, ArrowsClockwise, Download, Copy,
  Database, Pulse, Calendar, Hash, XCircle,
  Info as LinkIcon
} from '@phosphor-icons/react'
import * as Switch from '@radix-ui/react-switch'
import {
  ResponsiveLayout,
  ResponsiveDataTable,
  Button, Card, Badge, 
  LoadingSpinner, StatusIndicator, HelpCard,
  CompactSection, CompactGrid, CompactField
} from '../components'
import { casService, crlService, apiClient } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { formatDate } from '../lib/utils'
import { ERRORS, SUCCESS } from '../lib/messages'

// Extended CRL service methods
const crlApi = {
  ...crlService,
  regenerate: (caId) => apiClient.post(`/crl/${caId}/regenerate`),
  toggleAutoRegen: (caId, enabled) => apiClient.post(`/crl/${caId}/auto-regen`, { enabled }),
  getOcspStatus: () => apiClient.get('/ocsp/status'),
  getOcspStats: () => apiClient.get('/ocsp/stats'),
}

export default function CRLOCSPPage() {
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
        crlApi.getAll(),
        crlApi.getOcspStatus(),
        crlApi.getOcspStats()
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
      const response = await crlApi.getForCA(caId)
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
      await crlApi.regenerate(selectedCA.id)
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
    try {
      const result = await crlApi.toggleAutoRegen(ca.id, !ca.cdp_enabled)
      showSuccess(`Auto-regeneration ${result.data.cdp_enabled ? 'enabled' : 'disabled'} for ${ca.descr}`)
      // Update local state
      setCas(prev => prev.map(c => c.id === ca.id ? { ...c, cdp_enabled: result.data.cdp_enabled } : c))
      if (selectedCA?.id === ca.id) {
        setSelectedCA(prev => ({ ...prev, cdp_enabled: result.data.cdp_enabled }))
      }
    } catch (error) {
      showError(error.message || 'Failed to toggle auto-regeneration')
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
    showInfo('Copied to clipboard')
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
    { icon: ShieldCheck, label: 'CAs', value: cas.length },
    { icon: FileX, label: 'CRLs', value: crls.length, variant: 'info' },
    { icon: XCircle, label: 'Revoked', value: totalRevoked, variant: 'danger' },
    { icon: Pulse, label: 'OCSP', value: ocspStatus.running ? 'Online' : 'Offline', variant: ocspStatus.running ? 'success' : 'warning' }
  ], [cas.length, crls.length, totalRevoked, ocspStatus.running])

  // Table columns
  const columns = useMemo(() => [
    {
      key: 'descr',
      label: 'CA Name',
      render: (v, row) => (
        <div className="flex items-center gap-2">
          <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${row.has_crl ? 'icon-bg-emerald' : 'icon-bg-orange'}`}>
            <FileX size={14} weight="duotone" />
          </div>
          <span className="font-medium">{v || row.name}</span>
        </div>
      )
    },
    {
      key: 'has_crl',
      label: 'Status',
      width: '100px',
      render: (v, row) => (
        <Badge variant={v ? 'success' : 'orange'} size="sm" dot pulse={!v}>
          {v ? 'Active' : 'No CRL'}
        </Badge>
      )
    },
    {
      key: 'cdp_enabled',
      label: 'Auto',
      width: '70px',
      render: (v, row) => (
        <Switch.Root
          checked={v}
          onCheckedChange={() => handleToggleAutoRegen(row)}
          disabled={!row.has_private_key || !canWrite('crl')}
          className="w-9 h-5 bg-bg-tertiary rounded-full relative data-[state=checked]:bg-accent-success transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          onClick={(e) => e.stopPropagation()}
        >
          <Switch.Thumb className="block w-4 h-4 bg-white rounded-full shadow-sm transition-transform duration-100 translate-x-0.5 data-[state=checked]:translate-x-[18px]" />
        </Switch.Root>
      )
    },
    {
      key: 'revoked_count',
      label: 'Revoked',
      width: '80px',
      render: (v) => (
        <Badge variant={v > 0 ? 'danger' : 'secondary'} size="sm" dot={v > 0}>
          {v || 0}
        </Badge>
      )
    },
    {
      key: 'crl_updated',
      label: 'Updated',
      width: '120px',
      render: (v) => (
        <span className="text-text-secondary text-xs">
          {v ? formatDate(v, 'short') : '-'}
        </span>
      )
    }
  ], [canWrite, handleToggleAutoRegen])

  // Mobile card render
  const renderMobileCard = useCallback((ca, isSelected) => {
    return (
      <div className={`p-4 ${isSelected ? 'mobile-row-selected' : ''}`}>
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
              ca.has_crl ? 'status-success-bg' : 'status-warning-bg'
            }`}>
              <FileX size={20} className={ca.has_crl ? 'status-success-text' : 'status-warning-text'} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium text-text-primary truncate">{ca.descr || ca.name}</span>
                <Badge variant={ca.has_crl ? 'success' : 'warning'} size="sm" dot>
                  {ca.has_crl ? 'Active' : 'No CRL'}
                </Badge>
              </div>
              <div className="flex items-center gap-2 text-xs text-text-secondary mt-0.5">
                {ca.has_crl ? (
                  <>
                    <span>{ca.revoked_count || 0} revoked</span>
                    <span>•</span>
                    <span>CRL #{ca.crl_number || '-'}</span>
                  </>
                ) : (
                  <span>{ca.has_private_key === false ? 'Read-only (no key)' : 'Not generated'}</span>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }, [])

  // Help content
  const helpContent = (
    <div className="p-4 space-y-4">
      {/* CRL Statistics */}
      <Card className="p-4 space-y-3 bg-gradient-to-br from-accent-primary/5 to-transparent">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Database size={16} className="text-accent-primary" />
          CRL Statistics
        </h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-text-primary">{crls.length}</p>
            <p className="text-xs text-text-secondary">Active CRLs</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-status-danger">{totalRevoked}</p>
            <p className="text-xs text-text-secondary">Revoked Certs</p>
          </div>
        </div>
      </Card>

      {/* OCSP Status */}
      <Card className={`p-4 space-y-3 ${ocspStatus.enabled ? 'stat-card-success' : 'stat-card-warning'}`}>
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Pulse size={16} className="text-accent-primary" />
          OCSP Responder
        </h3>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">Status</span>
            <StatusIndicator status={ocspStatus.enabled && ocspStatus.running ? 'success' : 'warning'}>
              {ocspStatus.enabled ? (ocspStatus.running ? 'Running' : 'Stopped') : 'Disabled'}
            </StatusIndicator>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">Total Requests</span>
            <span className="text-sm font-medium text-text-primary">{ocspStats.total_requests}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">Cache Hit Rate</span>
            <span className="text-sm font-medium text-text-primary">{cacheHitRate}%</span>
          </div>
        </div>
      </Card>

      {/* Help Cards */}
      <div className="space-y-3">
        <HelpCard variant="info" title="About CRLs">
          Certificate Revocation Lists (CRLs) contain serial numbers of revoked certificates. 
          They are periodically published and cached by clients for offline verification.
        </HelpCard>
        
        <HelpCard variant="tip" title="OCSP vs CRL">
          OCSP provides real-time revocation status checks. CRL is a periodic snapshot. 
          Enable both for maximum compatibility with all clients and applications.
        </HelpCard>

        <HelpCard variant="warning" title="Distribution Points">
          Include CDP (CRL Distribution Point) and AIA (Authority Information Access) URLs 
          in your CA settings to enable automatic revocation checking.
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
            <p className="text-xs text-text-secondary">CRL & OCSP Configuration</p>
          </div>
        </div>
        <Badge variant={selectedCRL ? 'success' : 'warning'} size="sm" dot>
          {selectedCRL ? 'Active' : 'No CRL'}
        </Badge>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-3 gap-2">
        <div className="bg-bg-tertiary/40 rounded-lg p-2 text-center">
          <Hash size={14} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-sm font-semibold text-text-primary">{selectedCRL?.crl_number || '-'}</div>
          <div className="text-[10px] text-text-tertiary">CRL #</div>
        </div>
        <div className="bg-bg-tertiary/40 rounded-lg p-2 text-center">
          <XCircle size={14} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-sm font-semibold text-text-primary">{selectedCRL?.revoked_count || 0}</div>
          <div className="text-[10px] text-text-tertiary">Revoked</div>
        </div>
        <div className="bg-bg-tertiary/40 rounded-lg p-2 text-center">
          <Calendar size={14} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-sm font-semibold text-text-primary">{selectedCRL?.updated_at ? formatDate(selectedCRL.updated_at, 'short') : '-'}</div>
          <div className="text-[10px] text-text-tertiary">Updated</div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-2">
        {canWrite('certificates') && selectedCA.has_private_key !== false && (
          <Button 
            size="sm" 
            variant="primary" 
            onClick={handleRegenerateCRL}
            disabled={regenerating}
            className="flex-1"
          >
            <ArrowsClockwise size={14} className={regenerating ? 'animate-spin' : ''} />
            {regenerating ? 'Regenerating...' : 'Regenerate CRL'}
          </Button>
        )}
        {selectedCRL?.crl_pem && (
          <Button size="sm" variant="secondary" onClick={handleDownloadCRL}>
            <Download size={14} />
            Download
          </Button>
        )}
      </div>

      {/* CRL Configuration */}
      <CompactSection title="CRL Configuration" icon={Info}>
        <CompactGrid cols={2}>
          <CompactField label="CA Name" value={selectedCA.descr || selectedCA.name} />
          <CompactField label="Status" value={selectedCRL ? 'Active' : 'Not Generated'} />
          <CompactField label="CRL Number" value={selectedCRL?.crl_number || '-'} />
          <CompactField label="Revoked Count" value={selectedCRL?.revoked_count || 0} />
          <CompactField label="Last Updated" value={selectedCRL?.updated_at ? formatDate(selectedCRL.updated_at) : '-'} />
          <CompactField label="Next Update" value={selectedCRL?.next_update ? formatDate(selectedCRL.next_update) : '-'} />
        </CompactGrid>
      </CompactSection>

      {/* OCSP Configuration */}
      <CompactSection title="OCSP Configuration" icon={Pulse}>
        <CompactGrid cols={2}>
          <CompactField 
            label="Status" 
            value={ocspStatus.enabled ? (ocspStatus.running ? 'Running' : 'Stopped') : 'Disabled'} 
          />
          <CompactField label="Total Requests" value={ocspStats.total_requests} />
          <CompactField label="Cache Hits" value={ocspStats.cache_hits} />
          <CompactField label="Hit Rate" value={`${cacheHitRate}%`} />
        </CompactGrid>
      </CompactSection>

      {/* Distribution Points */}
      <CompactSection title="Distribution Points" icon={LinkIcon}>
        <div className="space-y-3">
          <div>
            <p className="text-xs text-text-secondary mb-1">CDP (CRL Distribution Point)</p>
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
            <p className="text-xs text-text-secondary mb-1">AIA (OCSP Responder)</p>
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
            Include these URLs in CA settings for automatic revocation checking.
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
      title="CRL & OCSP"
      icon={FileX}
      subtitle={`${crls.length} active CRLs`}
      stats={headerStats}
      helpPageKey="crlocsp"
      splitView={true}
      splitEmptyContent={
        <div className="h-full flex flex-col items-center justify-center p-6 text-center">
          <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
            <FileX size={24} className="text-text-tertiary" />
          </div>
          <p className="text-sm text-text-secondary">Select a CA to manage CRLs</p>
        </div>
      }
      slideOverOpen={!!selectedCA}
      onSlideOverClose={() => { setSelectedCA(null); setSelectedCRL(null); }}
      slideOverTitle="CRL Details"
      slideOverContent={detailContent}
      slideOverWidth="md"
    >
      <ResponsiveDataTable
        data={filteredCAs}
        columns={columns}
        keyField="id"
        searchable
        searchPlaceholder="Search CAs..."
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
          title: 'No Certificate Authorities',
          description: 'Create a CA first to manage CRLs'
        }}
      />
    </ResponsiveLayout>
  )
}
