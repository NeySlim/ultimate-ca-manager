/**
 * CertificatesPage - FROM SCRATCH with ResponsiveLayout + ResponsiveDataTable
 * 
 * DESKTOP: Dense table with hover rows, inline slide-over details
 * MOBILE: Card-style list with full-screen details, swipe gestures
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import { 
  Certificate, Download, Trash, X, Plus, Info,
  CheckCircle, Warning, UploadSimple, Clock, XCircle
} from '@phosphor-icons/react'
import {
  ResponsiveLayout, ResponsiveDataTable, Badge, Button, Modal, Select, Input, Textarea, HelpCard,
  CertificateDetails, KeyIndicator
} from '../components'
import { certificatesService, casService } from '../services'
import { useNotification, useMobile } from '../contexts'
import { ERRORS, SUCCESS, LABELS, CONFIRM, BUTTONS } from '../lib/messages'
import { usePermission } from '../hooks'
import { formatDate, extractCN, cn } from '../lib/utils'

export default function CertificatesPage() {
  const { isMobile } = useMobile()
  
  // Data
  const [certificates, setCertificates] = useState([])
  const [cas, setCas] = useState([])
  const [loading, setLoading] = useState(true)
  const [certStats, setCertStats] = useState({ valid: 0, expiring: 0, expired: 0, revoked: 0, total: 0 })
  
  // Selection
  const [selectedCert, setSelectedCert] = useState(null)
  const [showIssueModal, setShowIssueModal] = useState(false)
  const [showKeyModal, setShowKeyModal] = useState(false)
  const [keyPem, setKeyPem] = useState('')
  const [keyPassphrase, setKeyPassphrase] = useState('')
  
  // Pagination
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  const [total, setTotal] = useState(0)
  
  // Filters
  const [filterStatus, setFilterStatus] = useState('')
  const [filterCA, setFilterCA] = useState('')
  
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canWrite, canDelete } = usePermission()

  // Load data
  useEffect(() => {
    loadData()
  }, [page, perPage])

  const loadData = async () => {
    try {
      setLoading(true)
      const [certsRes, casRes, statsRes] = await Promise.all([
        certificatesService.getAll({ page, per_page: perPage }),
        casService.getAll(),
        certificatesService.getStats()
      ])
      const certs = certsRes.data || []
      setCertificates(certs)
      setTotal(certsRes.meta?.total || certsRes.pagination?.total || certs.length)
      setCas(casRes.data || [])
      setCertStats(statsRes.data || { valid: 0, expiring: 0, expired: 0, revoked: 0, total: 0 })
    } catch (error) {
      showError(error.message || ERRORS.LOAD_FAILED.CERTIFICATES)
    } finally {
      setLoading(false)
    }
  }

  // Load cert details for slide-over
  const handleSelectCert = useCallback(async (cert) => {
    if (!cert) {
      setSelectedCert(null)
      return
    }
    try {
      const res = await certificatesService.getById(cert.id)
      setSelectedCert(res.data || cert)
    } catch {
      setSelectedCert(cert)
    }
  }, [])

  // Export certificate
  const handleExport = async (format) => {
    if (!selectedCert) return
    try {
      const blob = await certificatesService.export(selectedCert.id, format)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${selectedCert.common_name || 'certificate'}.${format}`
      a.click()
      URL.revokeObjectURL(url)
      showSuccess(SUCCESS.EXPORT.CERTIFICATE)
    } catch {
      showError(ERRORS.EXPORT_FAILED.CERTIFICATE)
    }
  }

  // Revoke certificate
  const handleRevoke = async (id) => {
    const confirmed = await showConfirm(CONFIRM.REVOKE.MESSAGE, {
      title: 'Revoke Certificate',
      confirmText: 'Revoke',
      variant: 'danger'
    })
    if (!confirmed) return
    try {
      await certificatesService.revoke(id)
      showSuccess(SUCCESS.OTHER.REVOKED)
      loadData()
      setSelectedCert(null)
    } catch {
      showError(ERRORS.REVOKE_FAILED.CERTIFICATE)
    }
  }

  // Delete certificate
  const handleDelete = async (id) => {
    const confirmed = await showConfirm(CONFIRM.DELETE.CERTIFICATE, {
      title: 'Delete Certificate',
      confirmText: 'Delete',
      variant: 'danger'
    })
    if (!confirmed) return
    try {
      await certificatesService.delete(id)
      showSuccess(SUCCESS.DELETE.CERTIFICATE)
      loadData()
      setSelectedCert(null)
    } catch (error) {
      showError(error.message || ERRORS.DELETE_FAILED.CERTIFICATE)
    }
  }

  const handleUploadKey = async () => {
    if (!keyPem.trim()) {
      showError('Please provide a private key')
      return
    }
    if (!keyPem.includes('PRIVATE KEY')) {
      showError('Invalid private key format - must be PEM format')
      return
    }
    try {
      await certificatesService.uploadKey(selectedCert.id, keyPem.trim(), keyPassphrase || null)
      showSuccess(SUCCESS.OTHER.KEY_UPLOADED)
      setShowKeyModal(false)
      setKeyPem('')
      setKeyPassphrase('')
      loadData()
      // Refresh selected cert
      const updated = await certificatesService.getById(selectedCert.id)
      setSelectedCert(updated.data || updated)
    } catch (error) {
      showError(error.message || 'Failed to upload private key')
    }
  }

  // Normalize and filter data
  const filteredCerts = useMemo(() => {
    let result = certificates.map(cert => ({
      ...cert,
      status: cert.revoked ? 'revoked' : cert.status,
      cn: extractCN(cert.subject) || cert.common_name || 'Certificate'
    }))
    
    if (filterStatus) {
      result = result.filter(c => c.status === filterStatus)
    }
    
    if (filterCA) {
      result = result.filter(c => String(c.ca_id) === filterCA || c.caref === filterCA)
    }
    
    return result
  }, [certificates, filterStatus, filterCA])

  // Stats - from backend API for accurate counts
  const stats = useMemo(() => [
    { icon: CheckCircle, label: 'Valid', value: certStats.valid, variant: 'success' },
    { icon: Warning, label: 'Expiring', shortLabel: 'Exp.', value: certStats.expiring, variant: 'warning' },
    { icon: Clock, label: 'Expired', value: certStats.expired, variant: 'neutral' },
    { icon: X, label: 'Revoked', shortLabel: 'Rev.', value: certStats.revoked, variant: 'danger' },
    { icon: Certificate, label: 'Total', value: certStats.total, variant: 'primary' }
  ], [certStats])

  // Table columns
  const columns = useMemo(() => [
    {
      key: 'cn',
      header: 'Common Name',
      priority: 1,
      sortable: true,
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <div className={cn(
            "w-7 h-7 rounded-lg flex items-center justify-center shrink-0",
            row.has_private_key 
              ? "bg-accent-success/15 text-accent-success" 
              : "bg-accent-primary/15 text-accent-primary"
          )}>
            <Certificate size={14} weight="duotone" />
          </div>
          <span className="font-medium truncate">{val}</span>
          <KeyIndicator hasKey={row.has_private_key} size={14} />
          {row.source === 'acme' && <Badge variant="cyan" size="sm" dot>ACME</Badge>}
          {row.source === 'scep' && <Badge variant="orange" size="sm" dot>SCEP</Badge>}
        </div>
      )
    },
    {
      key: 'status',
      header: 'Status',
      priority: 2,
      sortable: true,
      render: (val, row) => {
        const isRevoked = row.revoked
        const status = isRevoked ? 'revoked' : val || 'unknown'
        const config = {
          valid: { variant: 'success', icon: CheckCircle, label: 'Valid', pulse: true },
          expiring: { variant: 'warning', icon: Clock, label: 'Expiring', pulse: true },
          expired: { variant: 'danger', icon: XCircle, label: 'Expired', pulse: false },
          revoked: { variant: 'danger', icon: X, label: 'Revoked', pulse: false },
          unknown: { variant: 'secondary', icon: Info, label: 'Unknown', pulse: false }
        }
        const { variant, icon, label, pulse } = config[status] || config.unknown
        return (
          <Badge variant={variant} size="sm" icon={icon} dot pulse={pulse}>
            {label}
          </Badge>
        )
      }
    },
    {
      key: 'issuer',
      header: 'Issuer',
      priority: 3,
      hideOnMobile: true,
      render: (val, row) => (
        <span className="text-text-secondary truncate">
          {extractCN(val) || row.issuer_name || '—'}
        </span>
      )
    },
    {
      key: 'valid_to',
      header: 'Expires',
      hideOnMobile: true,
      sortable: true,
      render: (val) => (
        <span className="text-xs text-text-secondary whitespace-nowrap">
          {formatDate(val)}
        </span>
      )
    },
    {
      key: 'key_type',
      header: 'Key',
      hideOnMobile: true,
      render: (val, row) => (
        <span className="text-xs font-mono text-text-secondary">
          {row.key_algorithm || val || 'RSA'}
        </span>
      )
    }
  ], [])

  // Row actions
  const rowActions = useCallback((row) => [
    { label: 'View Details', icon: Info, onClick: () => handleSelectCert(row) },
    { label: 'Export PEM', icon: Download, onClick: () => handleExportRow(row, 'pem') },
    ...(canWrite('certificates') && !row.revoked ? [
      { label: 'Revoke', icon: X, variant: 'danger', onClick: () => handleRevoke(row.id) }
    ] : []),
    ...(canDelete('certificates') ? [
      { label: 'Delete', icon: Trash, variant: 'danger', onClick: () => handleDelete(row.id) }
    ] : [])
  ], [canWrite, canDelete])

  // Export from row
  const handleExportRow = async (cert, format) => {
    try {
      const blob = await certificatesService.export(cert.id, format)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${cert.common_name || cert.cn || 'certificate'}.${format}`
      a.click()
      URL.revokeObjectURL(url)
      showSuccess(SUCCESS.EXPORT.CERTIFICATE)
    } catch {
      showError(ERRORS.EXPORT_FAILED.CERTIFICATE)
    }
  }

  // Filters
  const filters = useMemo(() => [
    {
      key: 'status',
      label: 'Status',
      type: 'select',
      value: filterStatus,
      onChange: setFilterStatus,
      placeholder: LABELS.FILTERS.ALL_STATUS,
      options: [
        { value: 'valid', label: 'Valid' },
        { value: 'expiring', label: 'Expiring Soon' },
        { value: 'expired', label: 'Expired' },
        { value: 'revoked', label: 'Revoked' }
      ]
    },
    {
      key: 'ca',
      label: 'Issuing CA',
      type: 'select',
      value: filterCA,
      onChange: setFilterCA,
      placeholder: LABELS.FILTERS.ALL_CAS,
      options: cas.map(ca => ({ 
        value: String(ca.id), 
        label: ca.descr || ca.common_name 
      }))
    }
  ], [filterStatus, filterCA, cas])

  const activeFilters = (filterStatus ? 1 : 0) + (filterCA ? 1 : 0)

  // Help content
  const helpContent = (
    <div className="space-y-4">
      {/* Quick Stats */}
      <div className="visual-section">
        <div className="visual-section-header">
          <Certificate size={16} className="status-primary-text" />
          Certificate Statistics
        </div>
        <div className="visual-section-body">
          <div className="quick-info-grid">
            <div className="help-stat-card">
              <div className="help-stat-value help-stat-value-success">{stats.find(s => s.label === 'Valid')?.value || 0}</div>
              <div className="help-stat-label">Valid</div>
            </div>
            <div className="help-stat-card">
              <div className="help-stat-value help-stat-value-warning">{stats.find(s => s.label === 'Expiring')?.value || 0}</div>
              <div className="help-stat-label">Expiring</div>
            </div>
            <div className="help-stat-card">
              <div className="help-stat-value help-stat-value-danger">{stats.find(s => s.label === 'Expired')?.value || 0}</div>
              <div className="help-stat-label">Expired</div>
            </div>
          </div>
        </div>
      </div>

      <HelpCard title="About Certificates" variant="info">
        Digital certificates authenticate identities and enable encrypted communications using PKI.
      </HelpCard>
      <HelpCard title="Status Legend" variant="info">
        <div className="space-y-1.5 mt-2">
          <div className="flex items-center gap-2">
            <Badge variant="success" size="sm" dot>Valid</Badge>
            <span className="text-xs">Active and trusted</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="warning" size="sm" dot>Expiring</Badge>
            <span className="text-xs">Expires within 30 days</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="danger" size="sm" dot>Revoked</Badge>
            <span className="text-xs">No longer valid</span>
          </div>
        </div>
      </HelpCard>
      <HelpCard title="Export Formats" variant="tip">
        PEM format is most common. Use DER for Java apps, PKCS#12 for Windows.
      </HelpCard>
    </div>
  )

  // Slide-over content
  const slideOverContent = selectedCert ? (
    <CertificateDetails
      certificate={selectedCert}
      onExport={handleExport}
      onRevoke={() => handleRevoke(selectedCert.id)}
      onDelete={() => handleDelete(selectedCert.id)}
      onUploadKey={() => setShowKeyModal(true)}
      canWrite={canWrite('certificates')}
      canDelete={canDelete('certificates')}
    />
  ) : null

  return (
    <>
      <ResponsiveLayout
        title="Certificates"
        subtitle={`${total} certificate${total !== 1 ? 's' : ''}`}
        icon={Certificate}
        stats={stats}
        helpContent={helpContent}
        helpTitle="Certificates Help"
        splitView={true}
        splitEmptyContent={
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
              <Certificate size={24} className="text-text-tertiary" />
            </div>
            <p className="text-sm text-text-secondary">Select a certificate to view details</p>
          </div>
        }
        slideOverOpen={!!selectedCert}
        slideOverTitle={selectedCert?.cn || selectedCert?.common_name || 'Certificate Details'}
        slideOverContent={slideOverContent}
        slideOverWidth="wide"
        onSlideOverClose={() => setSelectedCert(null)}
      >
        <ResponsiveDataTable
          data={filteredCerts}
          columns={columns}
          loading={loading}
          onRowClick={handleSelectCert}
          selectedId={selectedCert?.id}
          rowActions={rowActions}
          searchable
          searchPlaceholder="Search certificates..."
          searchKeys={['cn', 'common_name', 'subject', 'issuer', 'serial']}
          toolbarFilters={[
            {
              key: 'status',
              value: filterStatus,
              onChange: setFilterStatus,
              placeholder: LABELS.FILTERS.ALL_STATUS,
              options: [
                { value: 'valid', label: 'Valid' },
                { value: 'expiring', label: 'Expiring' },
                { value: 'expired', label: 'Expired' },
                { value: 'revoked', label: 'Revoked' }
              ]
            },
            {
              key: 'ca',
              value: filterCA,
              onChange: setFilterCA,
              placeholder: LABELS.FILTERS.ALL_CAS,
              options: cas.map(ca => ({ 
                value: String(ca.id), 
                label: ca.descr || ca.common_name 
              }))
            }
          ]}
          toolbarActions={canWrite('certificates') && (
            isMobile ? (
              <Button size="lg" onClick={() => setShowIssueModal(true)} className="w-11 h-11 p-0">
                <Plus size={22} weight="bold" />
              </Button>
            ) : (
              <Button size="sm" onClick={() => setShowIssueModal(true)}>
                <Plus size={14} weight="bold" />
                Issue
              </Button>
            )
          )}
          sortable
          defaultSort={{ key: 'cn', direction: 'asc' }}
          pagination={{
            page,
            total,
            perPage,
            onChange: setPage,
            onPerPageChange: (v) => { setPerPage(v); setPage(1) }
          }}
          emptyIcon={Certificate}
          emptyTitle="No certificates"
          emptyDescription="Issue your first certificate to get started"
          emptyAction={canWrite('certificates') && (
            <Button onClick={() => setShowIssueModal(true)}>
              <Plus size={16} /> Issue Certificate
            </Button>
          )}
        />
      </ResponsiveLayout>

      {/* Issue Certificate Modal */}
      <Modal
        open={showIssueModal}
        onOpenChange={setShowIssueModal}
        title="Issue Certificate"
        size="lg"
      >
        <IssueCertificateForm
          cas={cas}
          onSubmit={async (data) => {
            try {
              await certificatesService.create(data)
              showSuccess(SUCCESS.CREATE.CERTIFICATE)
              setShowIssueModal(false)
              loadData()
            } catch (error) {
              showError(error.message || 'Failed to issue certificate')
            }
          }}
          onCancel={() => setShowIssueModal(false)}
        />
      </Modal>

      {/* Upload Private Key Modal */}
      <Modal
        open={showKeyModal}
        onOpenChange={() => { setShowKeyModal(false); setKeyPem(''); setKeyPassphrase('') }}
        title="Upload Private Key"
      >
        <div className="p-4 space-y-4">
          <p className="text-sm text-text-secondary">
            Upload a private key for <strong>{selectedCert?.cn || selectedCert?.common_name}</strong>
          </p>
          <Textarea
            label="Private Key (PEM)"
            value={keyPem}
            onChange={(e) => setKeyPem(e.target.value)}
            placeholder="-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQE...
-----END PRIVATE KEY-----"
            rows={8}
            className="font-mono text-xs"
          />
          <Input
            label="Passphrase (if encrypted)"
            type="password"
            value={keyPassphrase}
            onChange={(e) => setKeyPassphrase(e.target.value)}
            placeholder="Leave empty if key is not encrypted"
          />
          <div className="flex justify-end gap-2 pt-2 border-t border-border">
            <Button variant="secondary" onClick={() => { setShowKeyModal(false); setKeyPem(''); setKeyPassphrase('') }}>
              Cancel
            </Button>
            <Button onClick={handleUploadKey} disabled={!keyPem.trim()}>
              <UploadSimple size={16} /> Upload Key
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}

// Issue Certificate Form
function IssueCertificateForm({ cas, onSubmit, onCancel }) {
  const [formData, setFormData] = useState({
    ca_id: '',
    common_name: '',
    san: '',
    key_type: 'rsa',
    key_size: '2048',
    validity_days: '365'
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    onSubmit(formData)
  }

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
      <Select
        label="Certificate Authority"
        value={formData.ca_id}
        onChange={(e) => setFormData(prev => ({ ...prev, ca_id: e.target.value }))}
        required
      >
        <option value="">Select a CA...</option>
        {cas.map(ca => (
          <option key={ca.id} value={ca.id}>{ca.descr || ca.common_name}</option>
        ))}
      </Select>
      
      <Input 
        label="Common Name" 
        placeholder="example.com"
        value={formData.common_name}
        onChange={(e) => setFormData(prev => ({ ...prev, common_name: e.target.value }))}
        required
      />
      
      <Textarea 
        label="Subject Alternative Names" 
        placeholder="DNS:example.com&#10;DNS:www.example.com&#10;IP:192.168.1.1" 
        rows={3}
        value={formData.san}
        onChange={(e) => setFormData(prev => ({ ...prev, san: e.target.value }))}
      />
      
      <div className="grid grid-cols-2 gap-4">
        <Select
          label="Key Type"
          value={formData.key_type}
          onChange={(e) => setFormData(prev => ({ ...prev, key_type: e.target.value }))}
        >
          <option value="rsa">RSA</option>
          <option value="ecdsa">ECDSA</option>
        </Select>
        
        <Select
          label="Key Size"
          value={formData.key_size}
          onChange={(e) => setFormData(prev => ({ ...prev, key_size: e.target.value }))}
        >
          {formData.key_type === 'rsa' ? (
            <>
              <option value="2048">2048 bits</option>
              <option value="4096">4096 bits</option>
            </>
          ) : (
            <>
              <option value="256">P-256</option>
              <option value="384">P-384</option>
            </>
          )}
        </Select>
      </div>
      
      <Input 
        label="Validity (days)" 
        type="number"
        placeholder="365"
        value={formData.validity_days}
        onChange={(e) => setFormData(prev => ({ ...prev, validity_days: e.target.value }))}
      />
      
      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit">
          <Certificate size={16} />
          Issue Certificate
        </Button>
      </div>
    </form>
  )
}
