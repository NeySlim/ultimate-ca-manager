/**
 * SCEP Management Page
 * Simple Certificate Enrollment Protocol configuration and request management
 */
import { useState, useEffect } from 'react'
import { 
  Robot, Gear, CheckCircle, XCircle, Clock, Copy, ArrowsClockwise, 
  Eye, ShieldCheck, Plugs, Key, Warning, Info, FileText, Globe, Database, MagnifyingGlass
} from '@phosphor-icons/react'
import {
  PageLayout, FocusItem, Button, Input, Select, Card,
  Table, Badge, LoadingSpinner, Modal, Textarea, EmptyState, StatusIndicator, HelpCard,
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
  const [showDetailsModal, setShowDetailsModal] = useState(false)

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
      const res = await scepService.regenerateChallenge(caId)
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

  const requestColumns = [
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
    { key: 'created_at', label: 'Requested', render: (v) => formatDate(v) },
    {
      key: 'actions',
      label: 'Actions',
      width: '150px',
      render: (_, row) => (
        <div className="flex gap-1">
          <Button size="sm" variant="ghost" onClick={() => { setSelectedRequest(row); setShowDetailsModal(true) }}>
            <Eye size={14} />
          </Button>
          {row.status === 'pending' && hasPermission('write:scep') && (
            <>
              <Button size="sm" variant="success" onClick={() => handleApprove(row)} title="Approve">
                <CheckCircle size={14} />
              </Button>
              <Button size="sm" variant="danger" onClick={() => { setSelectedRequest(row); setShowRejectModal(true) }} title="Reject">
                <XCircle size={14} />
              </Button>
            </>
          )}
        </div>
      )
    }
  ]

  const menuItems = [
    { 
      id: 'requests', 
      icon: Clock, 
      label: 'Enrollment Requests',
      badge: stats.pending > 0 ? stats.pending : null
    },
    { 
      id: 'config', 
      icon: Gear, 
      label: 'Configuration' 
    },
    { 
      id: 'challenge', 
      icon: Key, 
      label: 'Challenge Passwords' 
    },
    { 
      id: 'info', 
      icon: Info, 
      label: 'SCEP Information' 
    }
  ]

  // Filter menu items based on search
  const filteredMenuItems = menuItems.filter(item =>
    item.label.toLowerCase().includes(searchQuery.toLowerCase())
  )

  // Help content for modal
  const helpContent = (
    <div className="space-y-4">
      {/* SCEP Statistics */}
      <Card className="p-4 space-y-3 bg-gradient-to-br from-accent-primary/5 to-transparent">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Database size={16} className="text-accent-primary" />
          SCEP Statistics
        </h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-yellow-500">{stats.pending}</p>
            <p className="text-xs text-text-secondary">Pending</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-green-500">{stats.approved}</p>
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

      {/* SCEP Status */}
      <Card className={`p-4 space-y-3 bg-gradient-to-br ${config.enabled ? 'from-emerald-500/10' : 'from-amber-500/10'}`}>
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Plugs size={16} className="text-accent-primary" />
          SCEP Server Status
        </h3>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">Status</span>
            <StatusIndicator status={config.enabled ? 'success' : 'warning'}>
              {config.enabled ? 'Enabled' : 'Disabled'}
            </StatusIndicator>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">Auto-Approve</span>
            <span className="text-sm font-medium text-text-primary">{config.auto_approve ? 'Yes' : 'No'}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">CAs Configured</span>
            <span className="text-sm font-medium text-text-primary">{cas.length}</span>
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

  // Focus panel content (profile/section list)
  const focusContent = (
    <div className="p-2 space-y-1.5">
      {filteredMenuItems.length === 0 ? (
        <EmptyState 
          icon={Robot}
          title="No matches"
          description="Try a different search"
        />
      ) : (
        filteredMenuItems.map((item) => {
          const isSelected = activeTab === item.id
          return (
            <FocusItem
              key={item.id}
              icon={item.icon}
              title={item.label}
              subtitle={item.id === 'requests' ? `${stats.total} total requests` : null}
              badge={item.badge ? (
                <Badge variant="warning" size="sm">{item.badge}</Badge>
              ) : null}
              selected={isSelected}
              onClick={() => setActiveTab(item.id)}
            />
          )
        })
      )}
    </div>
  )

  // Focus actions (search)
  const focusActions = (
    <div className="flex-1 relative">
      <MagnifyingGlass size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-tertiary" />
      <input
        type="text"
        placeholder="Search profiles..."
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        className="w-full pl-8 pr-3 py-1.5 text-sm bg-bg-tertiary border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-accent-primary"
      />
    </div>
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full w-full">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return (
    <PageLayout
      title="SCEP Protocol"
      focusTitle="Profiles"
      focusContent={focusContent}
      focusActions={focusActions}
      focusFooter={
        <div className="flex items-center justify-between">
          <span>
            {config.enabled ? (
              <StatusIndicator status="online" label="Enabled" />
            ) : (
              <StatusIndicator status="offline" label="Disabled" />
            )}
          </span>
          <span>{menuItems.length} profiles</span>
        </div>
      }
      helpContent={helpContent}
      helpTitle="SCEP Protocol - Aide"
    >
      {/* Main Content Area */}
      <div className="p-6">
        {/* Requests Tab */}
        {activeTab === 'requests' && (
          <div className="space-y-0">
            <DetailHeader
              icon={Clock}
              title="SCEP Enrollment Requests"
              subtitle="Review and approve certificate enrollment requests from devices"
              badge={stats.pending > 0 ? <Badge variant="warning">{stats.pending} pending</Badge> : <Badge variant="success">All processed</Badge>}
              stats={[
                { label: 'Pending', value: stats.pending },
                { label: 'Approved', value: stats.approved },
                { label: 'Rejected', value: stats.rejected },
                { label: 'Total', value: stats.total }
              ]}
              actions={[
                { label: 'Refresh', icon: ArrowsClockwise, variant: 'secondary', onClick: loadData }
              ]}
            />

            <DetailSection title="Request Queue" noBorder>
              {requests.length === 0 ? (
                <Card className="p-8">
                  <EmptyState 
                    icon={Robot}
                    title="No SCEP requests"
                    description="Enrollment requests will appear here when devices request certificates via SCEP protocol"
                  />
                </Card>
              ) : (
                <Card className="p-0 overflow-hidden">
                  <Table
                    columns={requestColumns}
                    data={requests}
                    onRowClick={(row) => { setSelectedRequest(row); setShowDetailsModal(true) }}
                  />
                </Card>
              )}
            </DetailSection>
          </div>
        )}

        {/* Configuration Tab */}
        {activeTab === 'config' && (
          <div className="space-y-0 max-w-2xl">
            <DetailHeader
              icon={Gear}
              title="SCEP Configuration"
              subtitle="Configure the Simple Certificate Enrollment Protocol server"
              badge={<Badge variant={config.enabled ? 'success' : 'warning'}>{config.enabled ? 'Enabled' : 'Disabled'}</Badge>}
              actions={hasPermission('write:scep') ? [
                { label: saving ? 'Saving...' : 'Save Configuration', icon: saving ? LoadingSpinner : Gear, onClick: handleSaveConfig, disabled: saving }
              ] : undefined}
            />

            <HelpCard variant="info" title="About SCEP" className="mt-4">
              SCEP enables automated certificate enrollment for devices like MDM-managed devices, 
              network equipment, and IoT devices. Compatible with Microsoft Intune, Jamf, and others.
            </HelpCard>
            
            <DetailSection title="Server Status">
              <div className="flex items-start gap-4">
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${
                  config.enabled ? 'bg-green-500/15' : 'bg-bg-tertiary'
                }`}>
                  <Plugs size={24} className={config.enabled ? 'text-green-500' : 'text-text-tertiary'} weight="duotone" />
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
                      <p className="text-xs text-text-secondary">Allow devices to enroll certificates via SCEP protocol (RFC 8894)</p>
                    </div>
                  </label>
                </div>
              </div>
            </DetailSection>

            <DetailSection title="Server Settings">
              <div className="space-y-4">
                <Input
                  label="SCEP Endpoint URL"
                  value={`${window.location.origin}/scep/pkiclient.exe`}
                  readOnly
                  helperText="The full URL for SCEP enrollment (use this in client configuration)"
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
                  helperText="Identifier sent to clients during GetCACaps operation"
                  disabled={!config.enabled}
                />
              </div>
            </DetailSection>

            <DetailSection title="Security Settings">
              <div className="space-y-4">
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
                      <p className="text-xs text-text-secondary">Automatically approve valid SCEP requests with correct challenge password</p>
                    </div>
                  </label>
                  {config.auto_approve && (
                    <div className="mt-2 flex items-start gap-2 text-yellow-500 text-xs">
                      <Warning size={14} className="flex-shrink-0 mt-0.5" />
                      <span>Auto-approve is enabled. Ensure challenge passwords are securely distributed.</span>
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
              </div>
            </DetailSection>
          </div>
        )}

        {/* Challenge Passwords Tab */}
        {activeTab === 'challenge' && (
          <div className="space-y-0 max-w-2xl">
            <DetailHeader
              icon={Key}
              title="Challenge Passwords"
              subtitle="Pre-shared secrets for SCEP enrollment authentication"
              badge={<Badge variant={config.enabled ? 'success' : 'warning'}>{cas.length} CAs</Badge>}
            />

            {!config.enabled && (
              <Card className="p-4 border-yellow-500/30 bg-yellow-500/5 mt-4">
                <div className="flex items-start gap-3">
                  <Warning size={20} className="text-yellow-500 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-medium text-yellow-500">SCEP is disabled</p>
                    <p className="text-xs text-text-secondary">Enable SCEP in the Configuration tab to use challenge passwords.</p>
                  </div>
                </div>
              </Card>
            )}

            <DetailSection title="CA Challenge Passwords">
              {cas.length === 0 ? (
                <EmptyState 
                  icon={ShieldCheck}
                  title="No CAs available"
                  description="Create a Certificate Authority first to configure SCEP challenge passwords"
                />
              ) : (
                <div className="space-y-3">
                  {cas.map(ca => (
                    <div key={ca.id} className="rounded-md p-4 border border-white/5 bg-white/[0.02]">
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
                            title="Generate new challenge password"
                          >
                            <ArrowsClockwise size={14} />
                            Regenerate
                          </Button>
                        )}
                      </div>
                      <DetailGrid columns={1}>
                        <DetailField 
                          label="Challenge Password" 
                          value={ca.scep_challenge || 'No challenge password set'} 
                          mono 
                          copyable={!!ca.scep_challenge}
                          fullWidth
                        />
                      </DetailGrid>
                    </div>
                  ))}
                </div>
              )}
            </DetailSection>
          </div>
        )}

        {/* Information Tab */}
        {activeTab === 'info' && (
          <div className="space-y-0 max-w-2xl">
            <DetailHeader
              icon={Info}
              title="SCEP Protocol Information"
              subtitle="Reference information for configuring SCEP clients"
              badge={<Badge variant="info">RFC 8894</Badge>}
            />

            <DetailSection title="Connection Details">
              <DetailGrid columns={1}>
                <DetailField 
                  label="SCEP URL" 
                  value={`${window.location.origin}/scep/pkiclient.exe`} 
                  mono 
                  copyable 
                  fullWidth
                />
                <DetailField 
                  label="CA Identifier" 
                  value={config.ca_ident || 'ucm-ca'} 
                  mono
                  copyable
                  fullWidth
                />
              </DetailGrid>
            </DetailSection>

            <DetailSection title="Supported Operations">
              <div className="grid grid-cols-2 gap-2 text-sm">
                {['GetCACaps', 'GetCACert', 'GetCACertChain', 'PKIOperation'].map(op => (
                  <div key={op} className="flex items-center gap-2 p-2 bg-bg-tertiary rounded">
                    <CheckCircle size={14} className="text-green-500" />
                    <span className="text-text-primary">{op}</span>
                  </div>
                ))}
              </div>
            </DetailSection>

            <DetailSection title="Client Configuration Example">
              <div className="space-y-2">
                <p className="text-xs text-text-secondary">Cisco IOS Example:</p>
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
              </div>
            </DetailSection>
          </div>
        )}
      </div>

      {/* Reject Modal */}
      <Modal
        open={showRejectModal}
        onClose={() => { setShowRejectModal(false); setRejectReason('') }}
        title="Reject SCEP Request"
        size="md"
      >
        <div className="space-y-4">
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
            <p className="text-sm text-text-primary">
              Reject enrollment request from:
            </p>
            <p className="text-sm font-mono text-red-400 mt-1">
              {selectedRequest?.subject || selectedRequest?.transaction_id}
            </p>
          </div>
          <Textarea
            label="Rejection Reason (optional)"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder="Enter a reason for rejection..."
            rows={3}
          />
          <div className="flex gap-3 justify-end pt-2">
            <Button size="sm" variant="secondary" onClick={() => setShowRejectModal(false)}>Cancel</Button>
            <Button size="sm" variant="danger" onClick={handleReject}>
              <XCircle size={16} />
              Reject Request
            </Button>
          </div>
        </div>
      </Modal>

      {/* Details Modal */}
      <Modal
        open={showDetailsModal}
        onClose={() => setShowDetailsModal(false)}
        title="SCEP Request Details"
        size="lg"
      >
        {selectedRequest && (
          <DetailContent className="p-0">
            <DetailHeader
              icon={Robot}
              title={selectedRequest.subject || 'SCEP Request'}
              subtitle={`Transaction: ${selectedRequest.transaction_id?.slice(0, 16)}...`}
              badge={getStatusBadge(selectedRequest.status)}
              actions={selectedRequest.status === 'pending' && hasPermission('write:scep') ? [
                { label: 'Approve', icon: CheckCircle, variant: 'success', onClick: () => { handleApprove(selectedRequest); setShowDetailsModal(false) }},
                { label: 'Reject', icon: XCircle, variant: 'danger', onClick: () => { setShowDetailsModal(false); setShowRejectModal(true) }}
              ] : undefined}
            />

            <DetailSection title="Request Information">
              <DetailGrid>
                <DetailField label="Transaction ID" value={selectedRequest.transaction_id} mono copyable />
                <DetailField label="Status" value={selectedRequest.status?.toUpperCase()} />
                <DetailField label="Subject" value={selectedRequest.subject} />
                <DetailField label="Requested" value={formatDate(selectedRequest.created_at)} />
                <DetailField label="IP Address" value={selectedRequest.ip_address} />
                <DetailField label="Message Type" value={selectedRequest.message_type} />
              </DetailGrid>
            </DetailSection>

            {selectedRequest.csr && (
              <DetailSection title="Certificate Signing Request">
                <div className="space-y-2">
                  <div className="flex justify-end">
                    <Button size="sm" variant="ghost" onClick={() => copyToClipboard(selectedRequest.csr)}>
                      <Copy size={14} />
                      Copy CSR
                    </Button>
                  </div>
                  <pre className="p-3 bg-bg-tertiary rounded text-xs overflow-auto max-h-40 font-mono border border-border">
                    {selectedRequest.csr}
                  </pre>
                </div>
              </DetailSection>
            )}
          </DetailContent>
        )}
      </Modal>
    </PageLayout>
  )
}
