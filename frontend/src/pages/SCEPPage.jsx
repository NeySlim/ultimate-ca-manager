/**
 * SCEP Management Page - Migrated to ResponsiveLayout
 * Simple Certificate Enrollment Protocol configuration and request management
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import { 
  Robot, Gear, CheckCircle, XCircle, Clock, Copy, ArrowsClockwise, 
  Eye, ShieldCheck, Plugs, Key, Warning, Info, FileText, Globe, Database, 
  ListBullets, Question
} from '@phosphor-icons/react'
import {
  ResponsiveLayout,
  ResponsiveDataTable,
  Button, Input, Select, Card,
  Badge, LoadingSpinner, Modal, Textarea, EmptyState, StatusIndicator, HelpCard,
  DetailHeader, DetailSection, DetailGrid, DetailField, DetailContent
} from '../components'
import { scepService, casService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { formatDate } from '../lib/utils'

export default function SCEPPage() {
  const { showSuccess, showError, showInfo } = useNotification()
  const { hasPermission } = usePermission()
  
  const [loading, setLoading] = useState(true)
  const [config, setConfig] = useState({})
  const [requests, setRequests] = useState([])
  const [cas, setCas] = useState([])
  const [stats, setStats] = useState({ pending: 0, approved: 0, rejected: 0, total: 0 })
  const [selectedRequest, setSelectedRequest] = useState(null)
  const [activeTab, setActiveTab] = useState('requests')
  const [saving, setSaving] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  
  // Modal states
  const [showRejectModal, setShowRejectModal] = useState(false)
  const [rejectReason, setRejectReason] = useState('')
  const [showHelp, setShowHelp] = useState(false)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [configRes, requestsRes, casRes, statsRes] = await Promise.all([
        scepService.getConfig(),
        scepService.getRequests(),
        casService.getAll(),
        scepService.getStats()
      ])
      setConfig(configRes.data || {})
      setRequests(requestsRes.data || [])
      setStats(statsRes.data || { pending: 0, approved: 0, rejected: 0, total: 0 })
      
      // Load challenge passwords for each CA
      const casData = casRes.data || []
      const casWithChallenges = await Promise.all(
        casData.map(async (ca) => {
          try {
            const challengeRes = await scepService.getChallenge(ca.id)
            return { ...ca, scep_challenge: challengeRes.data?.challenge }
          } catch {
            return { ...ca, scep_challenge: null }
          }
        })
      )
      setCas(casWithChallenges)
    } catch (error) {
      showError('Failed to load SCEP data')
    } finally {
      setLoading(false)
    }
  }

  const handleSaveConfig = async () => {
    setSaving(true)
    try {
      await scepService.updateConfig(config)
      showSuccess('SCEP configuration saved')
    } catch (error) {
      showError(error.message || 'Failed to save configuration')
    } finally {
      setSaving(false)
    }
  }

  const handleApprove = async (req) => {
    try {
      await scepService.approveRequest(req.id)
      showSuccess('Request approved - Certificate issued')
      loadData()
    } catch (error) {
      showError(error.message || 'Failed to approve request')
    }
  }

  const handleReject = async () => {
    if (!selectedRequest) return
    try {
      await scepService.rejectRequest(selectedRequest.id, rejectReason)
      showSuccess('Request rejected')
      setShowRejectModal(false)
      setRejectReason('')
      setSelectedRequest(null)
      loadData()
    } catch (error) {
      showError(error.message || 'Failed to reject request')
    }
  }

  const handleRegenerateChallenge = async (caId) => {
    try {
      await scepService.regenerateChallenge(caId)
      showSuccess('Challenge password regenerated')
      loadData()
    } catch (error) {
      showError(error.message || 'Failed to regenerate challenge')
    }
  }

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text)
    showInfo('Copied to clipboard')
  }

  const getStatusBadge = (status) => {
    const variants = {
      pending: 'warning',
      approved: 'success',
      rejected: 'danger',
      issued: 'info'
    }
    return <Badge variant={variants[status] || 'default'}>{status}</Badge>
  }

  // Tabs config
  const tabs = useMemo(() => [
    { id: 'requests', label: 'Requests', badge: stats.pending > 0 ? stats.pending : null },
    { id: 'config', label: 'Configuration' },
    { id: 'challenge', label: 'Challenges' },
    { id: 'info', label: 'Info' }
  ], [stats.pending])

  // Stats for header
  const headerStats = useMemo(() => [
    { icon: Clock, label: 'Pending', value: stats.pending, variant: stats.pending > 0 ? 'warning' : 'default' },
    { icon: CheckCircle, label: 'Approved', value: stats.approved, variant: 'success' },
    { icon: XCircle, label: 'Rejected', value: stats.rejected, variant: 'danger' },
    { icon: ListBullets, label: 'Total', value: stats.total }
  ], [stats])

  // Request table columns
  const requestColumns = useMemo(() => [
    { key: 'id', label: 'ID', width: '60px' },
    { 
      key: 'transaction_id', 
      label: 'Transaction ID', 
      render: (v) => (
        <code className="text-xs bg-bg-tertiary px-1.5 py-0.5 rounded">{v?.slice(0, 16)}...</code>
      )
    },
    { key: 'subject', label: 'Subject', render: (v) => v || <span className="text-text-tertiary">-</span> },
    { key: 'status', label: 'Status', render: (v) => getStatusBadge(v) },
    { key: 'created_at', label: 'Requested', render: (v) => formatDate(v) }
  ], [])

  // Mobile card render for requests
  const renderMobileCard = useCallback((req, isSelected) => (
    <div className={`p-4 ${isSelected ? 'mobile-row-selected' : ''}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-text-primary truncate">
              {req.subject || `Request #${req.id}`}
            </span>
            {getStatusBadge(req.status)}
          </div>
          <div className="text-xs text-text-secondary mt-1">
            <code className="bg-bg-tertiary px-1 py-0.5 rounded">{req.transaction_id?.slice(0, 20)}...</code>
          </div>
          <div className="text-xs text-text-tertiary mt-1">
            {formatDate(req.created_at)}
          </div>
        </div>
        {req.status === 'pending' && hasPermission('write:scep') && (
          <div className="flex gap-1">
            <Button size="sm" variant="success" onClick={(e) => { e.stopPropagation(); handleApprove(req); }}>
              <CheckCircle size={14} />
            </Button>
            <Button size="sm" variant="danger" onClick={(e) => { e.stopPropagation(); setSelectedRequest(req); setShowRejectModal(true); }}>
              <XCircle size={14} />
            </Button>
          </div>
        )}
      </div>
    </div>
  ), [hasPermission])

  // Help content
  const helpContent = (
    <div className="p-4 space-y-4">
      {/* SCEP Statistics */}
      <Card className="p-4 space-y-3 bg-gradient-to-br from-accent-primary/5 to-transparent">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Database size={16} className="text-accent-primary" />
          SCEP Statistics
        </h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold status-warning-text">{stats.pending}</p>
            <p className="text-xs text-text-secondary">Pending</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold status-success-text">{stats.approved}</p>
            <p className="text-xs text-text-secondary">Approved</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-status-error">{stats.rejected}</p>
            <p className="text-xs text-text-secondary">Rejected</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-text-primary">{stats.total}</p>
            <p className="text-xs text-text-secondary">Total</p>
          </div>
        </div>
      </Card>

      {/* Help Cards */}
      <div className="space-y-3">
        <HelpCard variant="info" title="About SCEP">
          Simple Certificate Enrollment Protocol (SCEP) enables automated certificate enrollment 
          for devices like MDM-managed devices, network equipment, and IoT devices.
        </HelpCard>
        
        <HelpCard variant="tip" title="MDM Integration">
          Compatible with Microsoft Intune, Jamf Pro, VMware Workspace ONE, and other MDM solutions. 
          Configure the SCEP URL and challenge password in your MDM profile.
        </HelpCard>

        <HelpCard variant="warning" title="Challenge Security">
          Challenge passwords should be securely distributed. Consider using auto-approve only 
          in trusted environments with proper network segmentation.
        </HelpCard>
      </div>
    </div>
  )

  // Request details slide-over content
  const requestDetailContent = selectedRequest && !showRejectModal && (
    <DetailContent className="p-0">
      <DetailHeader
        icon={Robot}
        title={`Request #${selectedRequest.id}`}
        subtitle={selectedRequest.subject || 'SCEP Enrollment Request'}
        badge={getStatusBadge(selectedRequest.status)}
        stats={[
          { icon: Clock, label: 'Requested:', value: formatDate(selectedRequest.created_at) }
        ]}
        actions={selectedRequest.status === 'pending' && hasPermission('write:scep') ? [
          { label: 'Approve', icon: CheckCircle, variant: 'success', onClick: () => handleApprove(selectedRequest) },
          { label: 'Reject', icon: XCircle, variant: 'danger', onClick: () => setShowRejectModal(true) }
        ] : []}
      />

      <DetailSection title="Request Details">
        <DetailGrid>
          <DetailField label="Transaction ID" value={selectedRequest.transaction_id} mono copyable />
          <DetailField label="Subject" value={selectedRequest.subject || '-'} />
          <DetailField label="Status" value={selectedRequest.status} />
          <DetailField label="Created" value={formatDate(selectedRequest.created_at)} />
        </DetailGrid>
      </DetailSection>

      {selectedRequest.csr_pem && (
        <DetailSection title="CSR Content">
          <DetailField label="CSR PEM" value={selectedRequest.csr_pem} mono fullWidth copyable />
        </DetailSection>
      )}
    </DetailContent>
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
      <div className="flex items-center justify-center h-full w-full">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return (
    <>
      <ResponsiveLayout
        title="SCEP Protocol"
        icon={Robot}
        subtitle={config.enabled ? 'Enabled' : 'Disabled'}
        tabs={tabs}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        stats={activeTab === 'requests' ? headerStats : undefined}
        helpContent={helpContent}
        actions={headerActions}
        slideOverOpen={!!selectedRequest && !showRejectModal}
        onSlideOverClose={() => setSelectedRequest(null)}
        slideOverTitle="Request Details"
        slideOverContent={requestDetailContent}
        slideOverWidth="md"
      >
        {/* Requests Tab */}
        {activeTab === 'requests' && (
          <ResponsiveDataTable
            data={requests}
            columns={requestColumns}
            keyField="id"
            searchValue={searchQuery}
            onSearchChange={setSearchQuery}
            searchPlaceholder="Search requests..."
            selectedId={selectedRequest?.id}
            onRowClick={setSelectedRequest}
            renderMobileCard={renderMobileCard}
            emptyState={{
              icon: Robot,
              title: 'No SCEP requests',
              description: 'Enrollment requests will appear here when devices request certificates via SCEP protocol'
            }}
            rowActions={(row) => row.status === 'pending' && hasPermission('write:scep') ? [
              { icon: CheckCircle, label: 'Approve', onClick: () => handleApprove(row), variant: 'success' },
              { icon: XCircle, label: 'Reject', onClick: () => { setSelectedRequest(row); setShowRejectModal(true); }, variant: 'danger' }
            ] : []}
          />
        )}

        {/* Configuration Tab */}
        {activeTab === 'config' && (
          <div className="p-4 md:p-6 max-w-3xl mx-auto space-y-6">
            <Card className="p-4">
              <div className="flex items-start gap-4">
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${
                  config.enabled ? 'status-success-bg' : 'bg-bg-tertiary'
                }`}>
                  <Plugs size={24} className={config.enabled ? 'status-success-text' : 'text-text-tertiary'} weight="duotone" />
                </div>
                <div className="flex-1">
                  <label className="flex items-center gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={config.enabled || false}
                      onChange={(e) => setConfig({ ...config, enabled: e.target.checked })}
                      className="w-5 h-5 rounded border-border bg-bg-tertiary accent-accent-primary"
                    />
                    <div>
                      <p className="text-sm text-text-primary font-semibold">Enable SCEP Server</p>
                      <p className="text-xs text-text-secondary">Allow devices to enroll certificates via SCEP protocol</p>
                    </div>
                  </label>
                </div>
              </div>
            </Card>

            <Card className="p-4 space-y-4">
              <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <Gear size={16} />
                Server Settings
              </h3>
              
              <Input
                label="SCEP Endpoint URL"
                value={`${window.location.origin}/scep/pkiclient.exe`}
                readOnly
                helperText="Use this URL in client configuration"
                className="bg-bg-tertiary"
              />

              <Select
                label="Issuing CA"
                placeholder="Select a CA..."
                options={cas.map(ca => ({ value: ca.id.toString(), label: ca.name || ca.subject }))}
                value={config.ca_id?.toString() || ''}
                onChange={(val) => setConfig({ ...config, ca_id: parseInt(val) })}
                disabled={!config.enabled}
              />

              <Input
                label="CA Identifier"
                value={config.ca_ident || 'ucm-ca'}
                onChange={(e) => setConfig({ ...config, ca_ident: e.target.value })}
                helperText="Identifier sent to clients during GetCACaps"
                disabled={!config.enabled}
              />
            </Card>

            <Card className="p-4 space-y-4">
              <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <ShieldCheck size={16} />
                Security Settings
              </h3>
              
              <div className="p-3 bg-bg-tertiary rounded-lg">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config.auto_approve || false}
                    onChange={(e) => setConfig({ ...config, auto_approve: e.target.checked })}
                    className="w-5 h-5 rounded border-border bg-bg-secondary accent-accent-primary"
                    disabled={!config.enabled}
                  />
                  <div>
                    <p className="text-sm text-text-primary font-medium">Auto-approve requests</p>
                    <p className="text-xs text-text-secondary">Automatically approve valid SCEP requests</p>
                  </div>
                </label>
                {config.auto_approve && (
                  <div className="mt-2 flex items-start gap-2 status-warning-text text-xs">
                    <Warning size={14} className="flex-shrink-0 mt-0.5" />
                    <span>Auto-approve enabled. Ensure challenge passwords are securely distributed.</span>
                  </div>
                )}
              </div>

              <Input
                label="Challenge Password Validity"
                type="number"
                value={config.challenge_validity || 24}
                onChange={(e) => setConfig({ ...config, challenge_validity: parseInt(e.target.value) })}
                min="1"
                max="168"
                disabled={!config.enabled}
                helperText="Hours before challenge passwords expire (1-168)"
                suffix="hours"
              />
            </Card>

            {hasPermission('write:scep') && (
              <div className="flex justify-end">
                <Button onClick={handleSaveConfig} disabled={saving}>
                  {saving ? <LoadingSpinner size="sm" /> : <Gear size={14} />}
                  {saving ? 'Saving...' : 'Save Configuration'}
                </Button>
              </div>
            )}
          </div>
        )}

        {/* Challenge Passwords Tab */}
        {activeTab === 'challenge' && (
          <div className="p-4 md:p-6 max-w-3xl mx-auto space-y-4">
            {!config.enabled && (
              <Card className="p-4 status-warning-border status-warning-bg border">
                <div className="flex items-start gap-3">
                  <Warning size={20} className="status-warning-text flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-medium status-warning-text">SCEP is disabled</p>
                    <p className="text-xs text-text-secondary">Enable SCEP in Configuration tab to use challenge passwords.</p>
                  </div>
                </div>
              </Card>
            )}

            {cas.length === 0 ? (
              <EmptyState 
                icon={ShieldCheck}
                title="No CAs available"
                description="Create a Certificate Authority first to configure SCEP challenge passwords"
              />
            ) : (
              cas.map(ca => (
                <Card key={ca.id} className="p-4">
                  <div className="flex items-start justify-between gap-4 mb-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <ShieldCheck size={16} className="text-accent-primary" weight="duotone" />
                        <h3 className="text-sm font-semibold text-text-primary truncate">{ca.name || ca.subject}</h3>
                      </div>
                      <p className="text-xs text-text-tertiary truncate">{ca.subject}</p>
                    </div>
                    {hasPermission('write:scep') && (
                      <Button 
                        size="sm" 
                        variant="secondary" 
                        onClick={() => handleRegenerateChallenge(ca.id)}
                      >
                        <ArrowsClockwise size={14} />
                        <span className="hidden md:inline">Regenerate</span>
                      </Button>
                    )}
                  </div>
                  <div className="p-3 bg-bg-tertiary rounded-lg">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-text-secondary mb-1">Challenge Password</p>
                        <code className="text-sm font-mono text-text-primary break-all">
                          {ca.scep_challenge || 'No challenge password set'}
                        </code>
                      </div>
                      {ca.scep_challenge && (
                        <Button size="sm" variant="ghost" onClick={() => copyToClipboard(ca.scep_challenge)}>
                          <Copy size={14} />
                        </Button>
                      )}
                    </div>
                  </div>
                </Card>
              ))
            )}
          </div>
        )}

        {/* Information Tab */}
        {activeTab === 'info' && (
          <div className="p-4 md:p-6 max-w-3xl mx-auto space-y-4">
            <Card className="p-4 space-y-4">
              <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <Globe size={16} />
                Connection Details
              </h3>
              
              <div className="space-y-3">
                <div className="p-3 bg-bg-tertiary rounded-lg">
                  <p className="text-xs text-text-secondary mb-1">SCEP URL</p>
                  <div className="flex items-center gap-2">
                    <code className="text-sm font-mono text-text-primary flex-1 break-all">
                      {window.location.origin}/scep/pkiclient.exe
                    </code>
                    <Button size="sm" variant="ghost" onClick={() => copyToClipboard(`${window.location.origin}/scep/pkiclient.exe`)}>
                      <Copy size={14} />
                    </Button>
                  </div>
                </div>
                
                <div className="p-3 bg-bg-tertiary rounded-lg">
                  <p className="text-xs text-text-secondary mb-1">CA Identifier</p>
                  <div className="flex items-center gap-2">
                    <code className="text-sm font-mono text-text-primary flex-1">
                      {config.ca_ident || 'ucm-ca'}
                    </code>
                    <Button size="sm" variant="ghost" onClick={() => copyToClipboard(config.ca_ident || 'ucm-ca')}>
                      <Copy size={14} />
                    </Button>
                  </div>
                </div>
              </div>
            </Card>

            <Card className="p-4 space-y-4">
              <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <CheckCircle size={16} />
                Supported Operations
              </h3>
              <div className="grid grid-cols-2 gap-2">
                {['GetCACaps', 'GetCACert', 'GetCACertChain', 'PKIOperation'].map(op => (
                  <div key={op} className="flex items-center gap-2 p-2 bg-bg-tertiary rounded">
                    <CheckCircle size={14} className="status-success-text" />
                    <span className="text-sm text-text-primary">{op}</span>
                  </div>
                ))}
              </div>
            </Card>

            <Card className="p-4 space-y-4">
              <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <FileText size={16} />
                Cisco IOS Example
              </h3>
              <pre className="p-3 bg-bg-tertiary rounded-lg text-xs text-text-primary font-mono overflow-x-auto border border-border">
{`crypto ca trustpoint UCM-CA
 enrollment url ${window.location.origin}/scep/pkiclient.exe
 subject-name CN=device.example.com
 revocation-check none
 auto-enroll 70
!
crypto ca authenticate UCM-CA
crypto ca enroll UCM-CA`}
              </pre>
            </Card>
          </div>
        )}
      </ResponsiveLayout>

      {/* Reject Modal */}
      <Modal
        open={showRejectModal}
        onClose={() => { setShowRejectModal(false); setRejectReason(''); setSelectedRequest(null); }}
        title="Reject SCEP Request"
        size="md"
      >
        <div className="space-y-4">
          <div className="p-3 status-danger-bg status-danger-border border rounded-lg">
            <p className="text-sm text-text-primary">
              Reject enrollment request from:
            </p>
            <p className="text-sm font-mono status-danger-text mt-1">
              {selectedRequest?.subject || selectedRequest?.transaction_id}
            </p>
          </div>
          <Textarea
            label="Rejection Reason (optional)"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder="Enter reason for rejection..."
            rows={3}
          />
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => { setShowRejectModal(false); setRejectReason(''); }}>
              Cancel
            </Button>
            <Button variant="danger" onClick={handleReject}>
              <XCircle size={14} />
              Reject Request
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}
