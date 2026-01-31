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
  DetailHeader, DetailSection, DetailGrid, DetailField, DetailContent
} from '../components'
import { casService, crlService, apiClient } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { formatDate } from '../lib/utils'

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
        setSelectedCA(casData[0])
        loadCRLForCA(casData[0].id)
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
          return (
            <FocusItem
              key={ca.id}
              icon={FileX}
              title={ca.descr}
              subtitle={crl ? `Updated ${formatDate(crl.updated_at)}` : 'No CRL'}
              badge={hasRevoked ? (
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
        <DetailContent>
          {/* Detail Header */}
          <DetailHeader
            icon={FileX}
            title={selectedCA.descr}
            subtitle="CRL & OCSP Configuration"
            badge={
              <Badge variant={selectedCRL ? 'success' : 'warning'}>
                {selectedCRL ? 'Active' : 'Not Generated'}
              </Badge>
            }
            stats={[
              { icon: Hash, label: 'CRL Number', value: selectedCRL?.crl_number || '-' },
              { icon: XCircle, label: 'Revoked', value: selectedCRL?.revoked_count || 0 },
              { icon: Calendar, label: 'Updated', value: selectedCRL?.updated_at ? formatDate(selectedCRL.updated_at) : '-' }
            ]}
            actions={[
              { 
                label: regenerating ? 'Regenerating...' : 'Regenerate CRL', 
                icon: ArrowsClockwise, 
                onClick: handleRegenerateCRL,
                disabled: regenerating
              },
              { 
                label: 'Download CRL', 
                icon: Download, 
                onClick: handleDownloadCRL,
                disabled: !selectedCRL?.crl_pem,
                variant: 'secondary'
              }
            ]}
          />

          {/* CRL Configuration Section */}
          <DetailSection title="CRL Configuration">
            <DetailGrid>
              <DetailField label="CA Name" value={selectedCA.descr} />
              <DetailField 
                label="Status" 
                value={
                  <StatusIndicator status={selectedCRL ? 'success' : 'warning'}>
                    {selectedCRL ? 'Active' : 'Not Generated'}
                  </StatusIndicator>
                } 
              />
              <DetailField label="CRL Number" value={selectedCRL?.crl_number || '-'} mono />
              <DetailField label="Revoked Certificates" value={selectedCRL?.revoked_count || 0} />
              <DetailField 
                label="Last Updated" 
                value={selectedCRL?.updated_at ? formatDate(selectedCRL.updated_at) : '-'} 
              />
              <DetailField 
                label="Next Update" 
                value={selectedCRL?.next_update ? formatDate(selectedCRL.next_update) : '-'} 
              />
            </DetailGrid>
          </DetailSection>

          {/* OCSP Configuration Section */}
          <DetailSection title="OCSP Configuration">
            <DetailGrid>
              <DetailField 
                label="OCSP Status" 
                value={
                  <StatusIndicator status={ocspStatus.enabled && ocspStatus.running ? 'success' : 'warning'}>
                    {ocspStatus.enabled ? (ocspStatus.running ? 'Running' : 'Stopped') : 'Disabled'}
                  </StatusIndicator>
                } 
              />
              <DetailField label="Total Requests" value={ocspStats.total_requests} />
              <DetailField label="Cache Hits" value={ocspStats.cache_hits} />
              <DetailField label="Cache Hit Rate" value={`${cacheHitRate}%`} />
            </DetailGrid>
          </DetailSection>

          {/* Distribution Points Section */}
          <DetailSection title="Distribution Points">
            <DetailGrid columns={1}>
              <DetailField 
                label="CRL Distribution Point (CDP)" 
                value={`${window.location.origin}/crl/${selectedCA.refid}.crl`}
                mono
                copyable
                fullWidth
              />
              <DetailField 
                label="OCSP Responder URL (AIA)" 
                value={`${window.location.origin}/ocsp/${selectedCA.refid}`}
                mono
                copyable
                fullWidth
              />
            </DetailGrid>
            <p className="text-xs text-text-secondary mt-3">
              Include these URLs in your CA settings to enable automatic revocation checking in issued certificates.
            </p>
          </DetailSection>
        </DetailContent>
      )}
    </PageLayout>
  )
}
