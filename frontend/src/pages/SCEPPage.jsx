/**
 * SCEP Management Page
 * Simple Certificate Enrollment Protocol configuration and request management
 */
import { useState, useEffect } from 'react'
import { 
  Robot, Gear, CheckCircle, XCircle, Clock, Copy, ArrowsClockwise, 
  Eye, ShieldCheck, Plugs, Key, Warning, Info, FileText, Globe
} from '@phosphor-icons/react'
import {
  ExplorerPanel, DetailsPanel, Button, Input, Select, Card,
  Table, Badge, LoadingSpinner, Modal, Textarea, EmptyState, StatusIndicator
} from '../components'
import { scepService, casService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks/usePermission'
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
      setCas(casRes.data || [])
      setStats(statsRes.data || { pending: 0, approved: 0, rejected: 0, total: 0 })
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
      icon: <Clock size={16} weight="duotone" />, 
      label: 'Enrollment Requests',
      badge: stats.pending > 0 ? stats.pending : null
    },
    { 
      id: 'config', 
      icon: <Gear size={16} weight="duotone" />, 
      label: 'Configuration' 
    },
    { 
      id: 'challenge', 
      icon: <Key size={16} weight="duotone" />, 
      label: 'Challenge Passwords' 
    },
    { 
      id: 'info', 
      icon: <Info size={16} weight="duotone" />, 
      label: 'SCEP Information' 
    }
  ]

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full w-full">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return (
    <>
      <ExplorerPanel
        title="SCEP"
        footer={
          <div className="flex items-center justify-between text-xs">
            <span className="text-text-secondary">
              {config.enabled ? (
                <StatusIndicator status="online" label="Enabled" />
              ) : (
                <StatusIndicator status="offline" label="Disabled" />
              )}
            </span>
            <span className="text-text-tertiary">{stats.total} total requests</span>
          </div>
        }
      >
        {/* Stats Cards */}
        <div className="grid grid-cols-2 gap-2 mb-4">
          <div className="p-3 bg-gradient-to-br from-yellow-500/10 to-yellow-500/5 border border-yellow-500/20 rounded-lg">
            <div className="flex items-center gap-2">
              <Clock size={16} className="text-yellow-500" weight="duotone" />
              <span className="text-xs text-text-secondary">Pending</span>
            </div>
            <p className="text-lg font-bold text-yellow-500 mt-1">{stats.pending}</p>
          </div>
          <div className="p-3 bg-gradient-to-br from-green-500/10 to-green-500/5 border border-green-500/20 rounded-lg">
            <div className="flex items-center gap-2">
              <CheckCircle size={16} className="text-green-500" weight="duotone" />
              <span className="text-xs text-text-secondary">Approved</span>
            </div>
            <p className="text-lg font-bold text-green-500 mt-1">{stats.approved}</p>
          </div>
        </div>

        {/* Navigation Menu */}
        <div className="space-y-1">
          {menuItems.map(item => (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-sm transition-all ${
                activeTab === item.id 
                  ? 'bg-accent-primary/15 text-accent-primary border border-accent-primary/30' 
                  : 'text-text-secondary hover:bg-bg-tertiary hover:text-text-primary'
              }`}
            >
              <div className="flex items-center gap-2.5">
                {item.icon}
                <span>{item.label}</span>
              </div>
              {item.badge && (
                <Badge variant="warning" size="sm">{item.badge}</Badge>
              )}
            </button>
          ))}
        </div>
      </ExplorerPanel>

      <DetailsPanel>
        {/* Requests Tab */}
        {activeTab === 'requests' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold text-text-primary">SCEP Enrollment Requests</h2>
                <p className="text-xs text-text-secondary mt-0.5">
                  Review and approve certificate enrollment requests from devices
                </p>
              </div>
              <Button variant="secondary" onClick={loadData} size="sm">
                <ArrowsClockwise size={14} />
                Refresh
              </Button>
            </div>

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
          </div>
        )}

        {/* Configuration Tab */}
        {activeTab === 'config' && (
          <div className="space-y-6 max-w-2xl">
            <div>
              <h2 className="text-lg font-semibold text-text-primary">SCEP Configuration</h2>
              <p className="text-xs text-text-secondary mt-0.5">
                Configure the Simple Certificate Enrollment Protocol server
              </p>
            </div>
            
            {/* Enable Toggle Card */}
            <Card className="p-4">
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
            </Card>

            {/* Server Settings */}
            <Card className="p-4 space-y-4">
              <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <Globe size={16} className="text-accent-primary" />
                Server Settings
              </h3>

              <Input
                label="SCEP Endpoint URL"
                value={config.url || '/scep/pkiclient.exe'}
                onChange={(e) => setConfig({ ...config, url: e.target.value })}
                helperText="The URL path for SCEP enrollment (clients will use this)"
                disabled={!config.enabled}
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
            </Card>

            {/* Security Settings */}
            <Card className="p-4 space-y-4">
              <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <ShieldCheck size={16} className="text-accent-primary" />
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
            </Card>

            {hasPermission('write:scep') && (
              <div className="flex justify-end">
                <Button onClick={handleSaveConfig} disabled={saving}>
                  {saving ? <LoadingSpinner size="sm" /> : <Gear size={16} />}
                  {saving ? 'Saving...' : 'Save Configuration'}
                </Button>
              </div>
            )}
          </div>
        )}

        {/* Challenge Passwords Tab */}
        {activeTab === 'challenge' && (
          <div className="space-y-6 max-w-2xl">
            <div>
              <h2 className="text-lg font-semibold text-text-primary">Challenge Passwords</h2>
              <p className="text-xs text-text-secondary mt-0.5">
                Pre-shared secrets used to authenticate SCEP enrollment requests. Each CA has its own challenge password.
              </p>
            </div>

            {!config.enabled && (
              <Card className="p-4 border-yellow-500/30 bg-yellow-500/5">
                <div className="flex items-start gap-3">
                  <Warning size={20} className="text-yellow-500 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-medium text-yellow-500">SCEP is disabled</p>
                    <p className="text-xs text-text-secondary">Enable SCEP in the Configuration tab to use challenge passwords.</p>
                  </div>
                </div>
              </Card>
            )}

            <div className="space-y-3">
              {cas.length === 0 ? (
                <Card className="p-8">
                  <EmptyState 
                    icon={ShieldCheck}
                    title="No CAs available"
                    description="Create a Certificate Authority first to configure SCEP challenge passwords"
                  />
                </Card>
              ) : (
                cas.map(ca => (
                  <Card key={ca.id} className="p-4">
                    <div className="flex items-start justify-between gap-4">
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
                    <div className="mt-3 flex items-center gap-2">
                      <div className="flex-1 flex items-center gap-2 px-3 py-2 bg-bg-tertiary border border-border rounded-lg font-mono text-sm">
                        <Key size={14} className="text-text-tertiary flex-shrink-0" />
                        <code className="flex-1 truncate text-text-primary">
                          {ca.scep_challenge || 'No challenge password set'}
                        </code>
                      </div>
                      <Button 
                        size="sm" 
                        variant="ghost" 
                        onClick={() => copyToClipboard(ca.scep_challenge || '')}
                        disabled={!ca.scep_challenge}
                        title="Copy to clipboard"
                      >
                        <Copy size={14} />
                      </Button>
                    </div>
                  </Card>
                ))
              )}
            </div>
          </div>
        )}

        {/* Information Tab */}
        {activeTab === 'info' && (
          <div className="space-y-6 max-w-2xl">
            <div>
              <h2 className="text-lg font-semibold text-text-primary">SCEP Protocol Information</h2>
              <p className="text-xs text-text-secondary mt-0.5">
                Reference information for configuring SCEP clients
              </p>
            </div>

            <Card className="p-4 space-y-4">
              <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <Globe size={16} className="text-accent-primary" />
                Connection Details
              </h3>
              <div className="grid gap-3">
                <div className="p-3 bg-bg-tertiary rounded-lg">
                  <p className="text-xs text-text-secondary mb-1">SCEP URL</p>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 text-sm text-accent-primary">
                      https://your-server:8443{config.url || '/scep/pkiclient.exe'}
                    </code>
                    <Button size="sm" variant="ghost" onClick={() => copyToClipboard(`https://your-server:8443${config.url || '/scep/pkiclient.exe'}`)}>
                      <Copy size={14} />
                    </Button>
                  </div>
                </div>
                <div className="p-3 bg-bg-tertiary rounded-lg">
                  <p className="text-xs text-text-secondary mb-1">CA Identifier</p>
                  <code className="text-sm text-text-primary">{config.ca_ident || 'ucm-ca'}</code>
                </div>
              </div>
            </Card>

            <Card className="p-4 space-y-4">
              <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <FileText size={16} className="text-accent-primary" />
                Supported Operations
              </h3>
              <div className="grid grid-cols-2 gap-2 text-sm">
                {['GetCACaps', 'GetCACert', 'GetCACertChain', 'PKIOperation'].map(op => (
                  <div key={op} className="flex items-center gap-2 p-2 bg-bg-tertiary rounded">
                    <CheckCircle size={14} className="text-green-500" />
                    <span className="text-text-primary">{op}</span>
                  </div>
                ))}
              </div>
            </Card>

            <Card className="p-4 space-y-4">
              <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <Info size={16} className="text-accent-primary" />
                Client Configuration Example
              </h3>
              <div className="p-3 bg-bg-tertiary rounded-lg">
                <p className="text-xs text-text-secondary mb-2">Cisco IOS Example:</p>
                <pre className="text-xs text-text-primary font-mono overflow-x-auto">
{`crypto ca trustpoint UCM-CA
 enrollment url https://your-server:8443${config.url || '/scep/pkiclient.exe'}
 subject-name CN=device.example.com
 revocation-check none
 auto-enroll 70
!
crypto ca authenticate UCM-CA
crypto ca enroll UCM-CA`}
                </pre>
              </div>
            </Card>
          </div>
        )}
      </DetailsPanel>

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
            <Button variant="secondary" onClick={() => setShowRejectModal(false)}>Cancel</Button>
            <Button variant="danger" onClick={handleReject}>
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
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <Card className="p-3">
                <p className="text-xs text-text-tertiary mb-1">Transaction ID</p>
                <p className="text-sm text-text-primary font-mono break-all">{selectedRequest.transaction_id}</p>
              </Card>
              <Card className="p-3">
                <p className="text-xs text-text-tertiary mb-1">Status</p>
                <div className="mt-1">{getStatusBadge(selectedRequest.status)}</div>
              </Card>
              <Card className="p-3">
                <p className="text-xs text-text-tertiary mb-1">Subject</p>
                <p className="text-sm text-text-primary">{selectedRequest.subject || '-'}</p>
              </Card>
              <Card className="p-3">
                <p className="text-xs text-text-tertiary mb-1">Requested</p>
                <p className="text-sm text-text-primary">{formatDate(selectedRequest.created_at)}</p>
              </Card>
              <Card className="p-3">
                <p className="text-xs text-text-tertiary mb-1">IP Address</p>
                <p className="text-sm text-text-primary">{selectedRequest.ip_address || '-'}</p>
              </Card>
              <Card className="p-3">
                <p className="text-xs text-text-tertiary mb-1">Message Type</p>
                <p className="text-sm text-text-primary">{selectedRequest.message_type || '-'}</p>
              </Card>
            </div>
            {selectedRequest.csr && (
              <Card className="p-3">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs text-text-tertiary">Certificate Signing Request</p>
                  <Button size="sm" variant="ghost" onClick={() => copyToClipboard(selectedRequest.csr)}>
                    <Copy size={14} />
                    Copy
                  </Button>
                </div>
                <pre className="p-3 bg-bg-tertiary rounded text-xs overflow-auto max-h-40 font-mono">
                  {selectedRequest.csr}
                </pre>
              </Card>
            )}
            
            {selectedRequest.status === 'pending' && hasPermission('write:scep') && (
              <div className="flex gap-3 justify-end pt-2 border-t border-border">
                <Button variant="danger" onClick={() => { setShowDetailsModal(false); setShowRejectModal(true) }}>
                  <XCircle size={16} />
                  Reject
                </Button>
                <Button variant="success" onClick={() => { handleApprove(selectedRequest); setShowDetailsModal(false) }}>
                  <CheckCircle size={16} />
                  Approve & Issue Certificate
                </Button>
              </div>
            )}
          </div>
        )}
      </Modal>
    </>
  )
}
