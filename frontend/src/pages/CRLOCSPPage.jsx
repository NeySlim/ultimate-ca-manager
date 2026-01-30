/**
 * CRL & OCSP Management Page
 * Certificate Revocation Lists and OCSP responder management
 */
import { useState, useEffect } from 'react'
import { 
  FileX, ShieldCheck, ArrowsClockwise, Download, Globe, Clock,
  CheckCircle, XCircle, Info, Warning, Database, Activity
} from '@phosphor-icons/react'
import {
  ExplorerPanel, DetailsPanel, Button, Card, Badge, 
  Table, LoadingSpinner, EmptyState, StatusIndicator, HelpCard
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
  const [activeTab, setActiveTab] = useState('crl')
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

  const crlColumns = [
    { key: 'ca_name', label: 'CA' },
    { 
      key: 'revoked_count', 
      label: 'Revoked',
      render: (val) => <Badge variant="secondary">{val || 0}</Badge>
    },
    { 
      key: 'updated_at', 
      label: 'Last Updated',
      render: (val) => val ? formatDate(val) : '-'
    },
    { 
      key: 'next_update', 
      label: 'Next Update',
      render: (val) => val ? formatDate(val) : '-'
    },
  ]

  // Sidebar content
  const sidebarContent = (
    <div className="space-y-4">
      {/* Stats */}
      <div className="space-y-2">
        <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wide">Overview</h3>
        <Card className="p-3 space-y-2 bg-gradient-to-br from-accent-primary/5 to-transparent">
          <div className="flex items-center justify-between text-xs">
            <span className="text-text-secondary">CAs with CRL</span>
            <span className="text-text-primary font-medium">{crls.length}</span>
          </div>
          <div className="flex items-center justify-between text-xs">
            <span className="text-text-secondary">Total Revoked</span>
            <span className="text-text-primary font-medium">
              {crls.reduce((sum, crl) => sum + (crl.revoked_count || 0), 0)}
            </span>
          </div>
        </Card>
      </div>

      {/* OCSP Status */}
      <div className="space-y-2">
        <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wide">OCSP Status</h3>
        <Card className="p-3 space-y-2 bg-gradient-to-br from-emerald-500/5 to-transparent border-emerald-500/20">
          <div className="flex items-center justify-between text-xs">
            <span className="text-text-secondary">Service</span>
            <StatusIndicator status={ocspStatus.enabled ? 'success' : 'warning'} size="sm">
              {ocspStatus.enabled ? 'Enabled' : 'Disabled'}
            </StatusIndicator>
          </div>
          <div className="flex items-center justify-between text-xs">
            <span className="text-text-secondary">Status</span>
            <StatusIndicator status={ocspStatus.running ? 'success' : 'error'} size="sm">
              {ocspStatus.running ? 'Running' : 'Stopped'}
            </StatusIndicator>
          </div>
          <div className="flex items-center justify-between text-xs">
            <span className="text-text-secondary">Requests</span>
            <span className="text-text-primary font-medium">{ocspStats.total_requests}</span>
          </div>
        </Card>
      </div>

      {/* Quick Actions */}
      <div className="space-y-2">
        <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wide">Actions</h3>
        <div className="space-y-1">
          <Button 
            variant="ghost" 
            size="sm" 
            className="w-full justify-start text-xs"
            onClick={() => loadData()}
          >
            <ArrowsClockwise size={14} />
            Refresh Status
          </Button>
        </div>
      </div>

      {/* Help */}
      <HelpCard variant="info" className="text-xs">
        <p className="font-medium mb-1">CRL Distribution</p>
        <p className="text-text-secondary">
          CRLs are automatically published at /crl/[ca-refid].crl
        </p>
      </HelpCard>
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
    <div className="flex h-full">
      {/* Explorer Panel - CA List */}
      <ExplorerPanel 
        title="Certificate Authorities"
        width="280px"
        sidebarContent={sidebarContent}
      >
        <div className="space-y-1">
          {cas.length === 0 ? (
            <EmptyState 
              icon={FileX}
              title="No CAs"
              description="Create a CA first"
            />
          ) : (
            cas.map((ca) => {
              const crl = crls.find(c => c.caref === ca.refid)
              return (
                <div
                  key={ca.id}
                  onClick={() => handleSelectCA(ca)}
                  className={`
                    p-2 rounded-md cursor-pointer transition-colors
                    ${selectedCA?.id === ca.id 
                      ? 'bg-accent-primary/10 border border-accent-primary/30' 
                      : 'hover:bg-bg-tertiary border border-transparent'
                    }
                  `}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-text-primary truncate">
                      {ca.descr}
                    </span>
                    {crl && (
                      <Badge variant="secondary" size="sm">
                        {crl.revoked_count || 0}
                      </Badge>
                    )}
                  </div>
                  <div className="text-xs text-text-secondary mt-0.5">
                    {crl ? `Updated ${formatDate(crl.updated_at)}` : 'No CRL'}
                  </div>
                </div>
              )
            })
          )}
        </div>
      </ExplorerPanel>

      {/* Details Panel */}
      <DetailsPanel title={selectedCA ? `CRL: ${selectedCA.descr}` : 'CRL Details'}>
        {!selectedCA ? (
          <EmptyState 
            icon={FileX}
            title="Select a CA"
            description="Choose a CA to view its CRL"
          />
        ) : (
          <div className="p-4 space-y-6">
            {/* CRL Info */}
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-4">CRL Information</h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-xs text-text-secondary uppercase mb-1">CA Name</p>
                  <p className="text-sm text-text-primary">{selectedCA.descr}</p>
                </div>
                <div>
                  <p className="text-xs text-text-secondary uppercase mb-1">Status</p>
                  <StatusIndicator status={selectedCRL ? 'success' : 'warning'}>
                    {selectedCRL ? 'Active' : 'Not Generated'}
                  </StatusIndicator>
                </div>
                <div>
                  <p className="text-xs text-text-secondary uppercase mb-1">Revoked Certificates</p>
                  <p className="text-sm text-text-primary">{selectedCRL?.revoked_count || 0}</p>
                </div>
                <div>
                  <p className="text-xs text-text-secondary uppercase mb-1">CRL Number</p>
                  <p className="text-sm text-text-primary font-mono">{selectedCRL?.crl_number || '-'}</p>
                </div>
                <div>
                  <p className="text-xs text-text-secondary uppercase mb-1">Last Updated</p>
                  <p className="text-sm text-text-primary">
                    {selectedCRL?.updated_at ? formatDate(selectedCRL.updated_at) : '-'}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-secondary uppercase mb-1">Next Update</p>
                  <p className="text-sm text-text-primary">
                    {selectedCRL?.next_update ? formatDate(selectedCRL.next_update) : '-'}
                  </p>
                </div>
              </div>
            </div>

            {/* Distribution Points */}
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-4">Distribution Points</h3>
              <Card className="p-3 bg-bg-tertiary/50">
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <Globe size={14} className="text-accent-primary" />
                    <code className="text-xs text-text-primary bg-bg-secondary px-2 py-1 rounded flex-1">
                      {window.location.origin}/crl/{selectedCA.refid}.crl
                    </code>
                  </div>
                  <p className="text-xs text-text-secondary">
                    This URL can be used as the CDP in issued certificates
                  </p>
                </div>
              </Card>
            </div>

            {/* Actions */}
            <div className="flex gap-2 pt-4 border-t border-border">
              <Button 
                onClick={handleRegenerateCRL}
                disabled={regenerating}
              >
                <ArrowsClockwise size={16} className={regenerating ? 'animate-spin' : ''} />
                {regenerating ? 'Regenerating...' : 'Regenerate CRL'}
              </Button>
              <Button 
                variant="secondary"
                onClick={handleDownloadCRL}
                disabled={!selectedCRL?.crl_pem}
              >
                <Download size={16} />
                Download CRL
              </Button>
            </div>
          </div>
        )}
      </DetailsPanel>
    </div>
  )
}
