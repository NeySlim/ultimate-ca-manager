/**
 * SCEP Management Page
 * Simple Certificate Enrollment Protocol configuration and request management
 */
import { useState, useEffect } from 'react'
import { Robot, Gear, CheckCircle, XCircle, Clock, Copy, ArrowsClockwise, Eye } from '@phosphor-icons/react'
import {
  ExplorerPanel, DetailsPanel, Button, Input, Select,
  Table, Badge, LoadingSpinner, Modal, Textarea
} from '../components'
import { scepService, casService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks/usePermission'
import { formatDate } from '../lib/utils'

export default function SCEPPage() {
  const { showSuccess, showError } = useNotification()
  const { hasPermission } = usePermission()
  
  const [loading, setLoading] = useState(true)
  const [config, setConfig] = useState({})
  const [requests, setRequests] = useState([])
  const [cas, setCas] = useState([])
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
      const [configRes, requestsRes, casRes] = await Promise.all([
        scepService.getConfig(),
        scepService.getRequests(),
        casService.getAll()
      ])
      setConfig(configRes.data || {})
      setRequests(requestsRes.data || [])
      setCas(casRes.data || [])
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
      showSuccess('Request approved')
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
    showSuccess('Copied to clipboard')
  }

  const getStatusBadge = (status) => {
    const variants = {
      pending: { variant: 'warning', icon: <Clock size={12} /> },
      approved: { variant: 'success', icon: <CheckCircle size={12} /> },
      rejected: { variant: 'danger', icon: <XCircle size={12} /> },
      issued: { variant: 'info', icon: <CheckCircle size={12} /> }
    }
    const { variant, icon } = variants[status] || variants.pending
    return <Badge variant={variant}>{icon} {status}</Badge>
  }

  const requestColumns = [
    { key: 'id', label: 'ID', width: '60px' },
    { key: 'transaction_id', label: 'Transaction ID', render: (v) => <code className="text-xs">{v?.slice(0, 16)}...</code> },
    { key: 'subject', label: 'Subject', render: (v) => v || '-' },
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
              <Button size="sm" variant="success" onClick={() => handleApprove(row)}>
                <CheckCircle size={14} />
              </Button>
              <Button size="sm" variant="danger" onClick={() => { setSelectedRequest(row); setShowRejectModal(true) }}>
                <XCircle size={14} />
              </Button>
            </>
          )}
        </div>
      )
    }
  ]

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return (
    <>
      <ExplorerPanel
        title="SCEP"
        icon={<Robot size={20} />}
        subtitle="Simple Certificate Enrollment Protocol"
      >
        <div className="p-4 space-y-2">
          <button
            onClick={() => setActiveTab('requests')}
            className={`w-full text-left px-3 py-2 rounded-sm text-sm transition-colors ${
              activeTab === 'requests' 
                ? 'bg-accent-primary/20 text-accent-primary' 
                : 'text-text-secondary hover:bg-bg-tertiary'
            }`}
          >
            <Clock size={16} className="inline mr-2" />
            Pending Requests ({requests.filter(r => r.status === 'pending').length})
          </button>
          <button
            onClick={() => setActiveTab('config')}
            className={`w-full text-left px-3 py-2 rounded-sm text-sm transition-colors ${
              activeTab === 'config' 
                ? 'bg-accent-primary/20 text-accent-primary' 
                : 'text-text-secondary hover:bg-bg-tertiary'
            }`}
          >
            <Gear size={16} className="inline mr-2" />
            Configuration
          </button>
          <button
            onClick={() => setActiveTab('challenge')}
            className={`w-full text-left px-3 py-2 rounded-sm text-sm transition-colors ${
              activeTab === 'challenge' 
                ? 'bg-accent-primary/20 text-accent-primary' 
                : 'text-text-secondary hover:bg-bg-tertiary'
            }`}
          >
            <Robot size={16} className="inline mr-2" />
            Challenge Passwords
          </button>
        </div>
      </ExplorerPanel>

      <DetailsPanel>
        {activeTab === 'requests' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-text-primary">SCEP Requests</h2>
              <Button variant="secondary" onClick={loadData}>
                <ArrowsClockwise size={16} />
                Refresh
              </Button>
            </div>

            {requests.length === 0 ? (
              <div className="p-12 text-center bg-bg-secondary border border-border rounded-lg">
                <Robot size={48} className="mx-auto mb-4 text-text-tertiary" />
                <p className="text-text-secondary">No SCEP requests</p>
                <p className="text-xs text-text-tertiary mt-1">
                  Requests will appear here when devices enroll via SCEP
                </p>
              </div>
            ) : (
              <Table
                columns={requestColumns}
                data={requests}
                onRowClick={(row) => { setSelectedRequest(row); setShowDetailsModal(true) }}
              />
            )}
          </div>
        )}

        {activeTab === 'config' && (
          <div className="space-y-6 max-w-2xl">
            <h2 className="text-lg font-semibold text-text-primary">SCEP Configuration</h2>
            
            <div className="space-y-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={config.enabled || false}
                  onChange={(e) => setConfig({ ...config, enabled: e.target.checked })}
                  className="rounded border-border bg-bg-tertiary"
                />
                <div>
                  <p className="text-sm text-text-primary font-medium">Enable SCEP</p>
                  <p className="text-xs text-text-secondary">Allow devices to enroll certificates via SCEP protocol</p>
                </div>
              </label>

              <Input
                label="SCEP URL"
                value={config.url || '/scep/pkiclient.exe'}
                onChange={(e) => setConfig({ ...config, url: e.target.value })}
                helperText="The URL path for SCEP enrollment"
                disabled={!config.enabled}
              />

              <Select
                label="Issuing CA"
                options={cas.map(ca => ({ value: ca.id.toString(), label: ca.name || ca.subject }))}
                value={config.ca_id?.toString() || ''}
                onChange={(val) => setConfig({ ...config, ca_id: parseInt(val) })}
                disabled={!config.enabled}
              />

              <Input
                label="CA Identifier"
                value={config.ca_ident || 'ucm-ca'}
                onChange={(e) => setConfig({ ...config, ca_ident: e.target.value })}
                helperText="Identifier sent to clients during enrollment"
                disabled={!config.enabled}
              />

              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={config.auto_approve || false}
                  onChange={(e) => setConfig({ ...config, auto_approve: e.target.checked })}
                  className="rounded border-border bg-bg-tertiary"
                  disabled={!config.enabled}
                />
                <div>
                  <p className="text-sm text-text-primary font-medium">Auto-approve requests</p>
                  <p className="text-xs text-text-secondary">Automatically approve valid SCEP requests (not recommended)</p>
                </div>
              </label>

              <Input
                label="Challenge Password Validity (hours)"
                type="number"
                value={config.challenge_validity || 24}
                onChange={(e) => setConfig({ ...config, challenge_validity: parseInt(e.target.value) })}
                min="1"
                max="168"
                disabled={!config.enabled}
              />
            </div>

            {hasPermission('write:scep') && (
              <Button onClick={handleSaveConfig} disabled={saving}>
                {saving ? 'Saving...' : 'Save Configuration'}
              </Button>
            )}
          </div>
        )}

        {activeTab === 'challenge' && (
          <div className="space-y-6 max-w-2xl">
            <h2 className="text-lg font-semibold text-text-primary">Challenge Passwords</h2>
            <p className="text-sm text-text-secondary">
              Challenge passwords are used to authenticate SCEP enrollment requests.
              Each CA has its own challenge password.
            </p>

            <div className="space-y-4">
              {cas.map(ca => (
                <div key={ca.id} className="p-4 bg-bg-secondary border border-border rounded-lg">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-sm font-semibold text-text-primary">{ca.name || ca.subject}</h3>
                    {hasPermission('write:scep') && (
                      <Button size="sm" variant="secondary" onClick={() => handleRegenerateChallenge(ca.id)}>
                        <ArrowsClockwise size={14} />
                        Regenerate
                      </Button>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 px-3 py-2 bg-bg-tertiary rounded text-sm font-mono">
                      {ca.scep_challenge || 'Not configured'}
                    </code>
                    <Button size="sm" variant="ghost" onClick={() => copyToClipboard(ca.scep_challenge || '')}>
                      <Copy size={14} />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </DetailsPanel>

      {/* Reject Modal */}
      <Modal
        open={showRejectModal}
        onClose={() => { setShowRejectModal(false); setRejectReason('') }}
        title="Reject SCEP Request"
      >
        <div className="space-y-4">
          <p className="text-sm text-text-secondary">
            Reject request from: <strong>{selectedRequest?.subject || selectedRequest?.transaction_id}</strong>
          </p>
          <Textarea
            label="Rejection Reason"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder="Optional reason for rejection"
            rows={3}
          />
          <div className="flex gap-3 justify-end">
            <Button variant="secondary" onClick={() => setShowRejectModal(false)}>Cancel</Button>
            <Button variant="danger" onClick={handleReject}>Reject Request</Button>
          </div>
        </div>
      </Modal>

      {/* Details Modal */}
      <Modal
        open={showDetailsModal}
        onClose={() => setShowDetailsModal(false)}
        title="SCEP Request Details"
      >
        {selectedRequest && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-text-tertiary">Transaction ID</p>
                <p className="text-text-primary font-mono">{selectedRequest.transaction_id}</p>
              </div>
              <div>
                <p className="text-text-tertiary">Status</p>
                <p>{getStatusBadge(selectedRequest.status)}</p>
              </div>
              <div>
                <p className="text-text-tertiary">Subject</p>
                <p className="text-text-primary">{selectedRequest.subject || '-'}</p>
              </div>
              <div>
                <p className="text-text-tertiary">Requested</p>
                <p className="text-text-primary">{formatDate(selectedRequest.created_at)}</p>
              </div>
              <div>
                <p className="text-text-tertiary">IP Address</p>
                <p className="text-text-primary">{selectedRequest.ip_address || '-'}</p>
              </div>
              <div>
                <p className="text-text-tertiary">Message Type</p>
                <p className="text-text-primary">{selectedRequest.message_type || '-'}</p>
              </div>
            </div>
            {selectedRequest.csr && (
              <div>
                <p className="text-text-tertiary text-sm mb-1">CSR</p>
                <pre className="p-3 bg-bg-tertiary rounded text-xs overflow-auto max-h-40">
                  {selectedRequest.csr}
                </pre>
              </div>
            )}
          </div>
        )}
      </Modal>
    </>
  )
}
