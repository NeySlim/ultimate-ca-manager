/**
 * CRL & OCSP Management Page
 * Certificate Revocation Lists and OCSP responder management
 */
import { useState, useEffect } from 'react'
import { 
  FileX, ShieldCheck, ArrowsClockwise, Download, Globe,
  Database, Pulse, Calendar, Hash, CheckCircle, XCircle
} from '@phosphor-icons/react'
import {
  PageLayout, FocusItem, Button, Card, Badge, 
  LoadingSpinner, EmptyState, StatusIndicator, HelpCard,
  CompactSection, CompactGrid, CompactField, CompactStats, CompactHeader
} from '../components'
import { casService, crlService, apiClient } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { formatDate, cn } from '../lib/utils'

// Extended CRL service methods
const crlApi = {
  ...crlService,
  regenerate: (caId) => apiClient.post(`/crl/${caId}/regenerate`),
  getOcspStatus: () => apiClient.get('/ocsp/status'),
  getOcspStats: () => apiClient.get('/ocsp/stats'),
}

export default function CRLOCSPPage() {
  const { showSuccess, showError } = useNotification()
  const { canWrite } = usePermission()
  
  const [loading, setLoading] = useState(true)
  const [cas, setCas] = useState([])
  const [crls, setCrls] = useState([])
  const [selectedCA, setSelectedCA] = useState(null)
  const [selectedCRL, setSelectedCRL] = useState(null)
  const [ocspStatus, setOcspStatus] = useState({ enabled: false, running: false })
  const [ocspStats, setOcspStats] = useState({ total_requests: 0, cache_hits: 0 })
  const [regenerating, setRegenerating] = useState(false)

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
      
      const casData = casRes.data || []
      setCas(casData)
      setCrls(crlsRes.data || [])
      setOcspStatus(ocspStatusRes.data || { enabled: false, running: false })
      setOcspStats(ocspStatsRes.data || { total_requests: 0, cache_hits: 0 })
      
      if (casData.length > 0 && !selectedCA) {
        // Prefer CA with a CRL, fallback to first CA
        const crlsData = crlsRes.data || []
        const caWithCrl = casData.find(ca => 
          crlsData.some(crl => crl.ca_id === ca.id || crl.caref === ca.refid)
        )
        const initialCA = caWithCrl || casData[0]
        setSelectedCA(initialCA)
        loadCRLForCA(initialCA.id)
      }
    } catch (error) {
      showError(error.message || 'Failed to load CRL/OCSP data')
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
      showSuccess('CRL regenerated successfully')
      loadCRLForCA(selectedCA.id)
      loadData()
    } catch (error) {
      showError(error.message || 'Failed to regenerate CRL')
    } finally {
      setRegenerating(false)
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

  // Calculate stats
  const totalRevoked = crls.reduce((sum, crl) => sum + (crl.revoked_count || 0), 0)
  const cacheHitRate = ocspStats.total_requests > 0 
    ? Math.round((ocspStats.cache_hits / ocspStats.total_requests) * 100) 
    : 0

  // Help content for modal
  const helpContent = (
    <div className="space-y-4">
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
            <p className="text-2xl font-bold text-status-error">{totalRevoked}</p>
            <p className="text-xs text-text-secondary">Revoked Certs</p>
          </div>
        </div>
      </Card>

      {/* OCSP Status */}
      <Card className={`p-4 space-y-3 bg-gradient-to-br ${ocspStatus.enabled ? 'from-emerald-500/10' : 'from-amber-500/10'}`}>
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

  // Focus panel content (CA list)
  const focusContent = (
    <div className="p-2 space-y-1.5">
      {cas.length === 0 ? (
        <EmptyState 
          icon={FileX}
          title="No CAs"
          description="Create a CA first"
        />
      ) : (
        cas.map((ca) => {
          const crl = crls.find(c => c.caref === ca.refid)
          const isSelected = selectedCA?.id === ca.id
          const hasRevoked = crl && (crl.revoked_count || 0) > 0
          const hasKey = ca.has_private_key !== false
          return (
            <FocusItem
              key={ca.id}
              icon={FileX}
              title={ca.descr}
              subtitle={!hasKey ? 'No private key' : (crl ? `Updated ${formatDate(crl.updated_at)}` : 'No CRL')}
              badge={!hasKey ? (
                <Badge variant="secondary" size="sm">Read-only</Badge>
              ) : hasRevoked ? (
                <Badge variant="danger" size="sm">{crl.revoked_count}</Badge>
              ) : crl ? (
                <Badge variant="success" size="sm">0</Badge>
              ) : null}
              selected={isSelected}
              onClick={() => handleSelectCA(ca)}
            />
          )
        })
      )}
    </div>
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner />
      </div>
    )
  }

  return (
    <PageLayout
      title="CRL & OCSP"
      focusTitle="Certificate Authorities"
      focusContent={focusContent}
      focusFooter={`${cas.length} CA(s)`}
      helpContent={helpContent}
      
    >
      {/* Main Content */}
      {!selectedCA ? (
        <div className="flex items-center justify-center h-full">
          <EmptyState 
            icon={FileX}
            title="Select a CA"
            description="Choose a CA to view its CRL"
          />
        </div>
      ) : (
        <div className="p-3 space-y-3">
          {/* Header */}
          <CompactHeader
            icon={FileX}
            iconClass={selectedCRL ? "bg-status-success/20" : "bg-status-warning/20"}
            title={selectedCA.descr}
            subtitle="CRL & OCSP Configuration"
            badge={
              <Badge variant={selectedCRL ? 'success' : 'warning'} size="sm">
                {selectedCRL ? 'Active' : 'Not Generated'}
              </Badge>
            }
          />

          {/* Stats */}
          <CompactStats stats={[
            { icon: Hash, value: `#${selectedCRL?.crl_number || '-'}` },
            { icon: XCircle, value: `${selectedCRL?.revoked_count || 0} revoked` },
            { icon: Calendar, value: selectedCRL?.updated_at ? formatDate(selectedCRL.updated_at, 'short') : '-' }
          ]} />

          {/* Actions */}
          <div className="flex gap-2">
            <Button 
              size="sm" 
              variant="secondary" 
              className="flex-1"
              onClick={handleRegenerateCRL}
              disabled={regenerating || selectedCA.has_private_key === false}
            >
              <ArrowsClockwise size={14} className={regenerating ? 'animate-spin' : ''} />
              {regenerating ? 'Regenerating...' : (selectedCA.has_private_key === false ? 'No Key' : 'Regenerate')}
            </Button>
            <Button 
              size="sm" 
              variant="secondary"
              onClick={handleDownloadCRL}
              disabled={!selectedCRL?.crl_pem}
            >
              <Download size={14} />
            </Button>
          </div>

          {/* CRL Config */}
          <CompactSection title="CRL Configuration">
            <CompactGrid>
              <CompactField label="CA" value={selectedCA.descr} />
              <div className="text-xs">
                <span className="text-text-tertiary">Status:</span>
                <StatusIndicator status={selectedCRL ? 'success' : 'warning'} className="ml-1 inline-flex">
                  {selectedCRL ? 'Active' : 'Not Generated'}
                </StatusIndicator>
              </div>
              <CompactField label="CRL #" value={selectedCRL?.crl_number || '-'} />
              <CompactField label="Revoked" value={selectedCRL ? (selectedCRL.revoked_count || 0) : '-'} />
              <CompactField label="Updated" value={selectedCRL?.updated_at ? formatDate(selectedCRL.updated_at, 'short') : '-'} />
              <CompactField label="Next Update" value={selectedCRL?.next_update ? formatDate(selectedCRL.next_update, 'short') : '-'} />
            </CompactGrid>
          </CompactSection>

          {/* OCSP Config */}
          <CompactSection title="OCSP Configuration">
            <CompactGrid>
              <div className="text-xs">
                <span className="text-text-tertiary">Status:</span>
                <StatusIndicator status={ocspStatus.enabled && ocspStatus.running ? 'success' : 'warning'} className="ml-1 inline-flex">
                  {ocspStatus.enabled ? (ocspStatus.running ? 'Running' : 'Stopped') : 'Disabled'}
                </StatusIndicator>
              </div>
              <CompactField label="Requests" value={ocspStats.total_requests} />
              <CompactField label="Cache Hits" value={ocspStats.cache_hits} />
              <CompactField label="Hit Rate" value={`${cacheHitRate}%`} />
            </CompactGrid>
          </CompactSection>

          {/* Distribution Points */}
          <CompactSection title="Distribution Points">
            <div className="space-y-2">
              <div className="text-xs">
                <span className="text-text-tertiary block mb-0.5">CDP (CRL):</span>
                <p className="font-mono text-[10px] text-text-secondary break-all bg-bg-tertiary/50 p-1.5 rounded">
                  {`${window.location.origin}/crl/${selectedCA.refid}.crl`}
                </p>
              </div>
              <div className="text-xs">
                <span className="text-text-tertiary block mb-0.5">AIA (OCSP):</span>
                <p className="font-mono text-[10px] text-text-secondary break-all bg-bg-tertiary/50 p-1.5 rounded">
                  {`${window.location.origin}/ocsp/${selectedCA.refid}`}
                </p>
              </div>
              <p className="text-[10px] text-text-tertiary mt-2">
                Include these URLs in CA settings for automatic revocation checking.
              </p>
            </div>
          </CompactSection>
        </div>
      )}
    </PageLayout>
  )
}
