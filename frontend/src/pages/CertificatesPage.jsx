/**
 * Certificates Page
 */
import { useState, useEffect } from 'react'
import { Certificate, Download, X, ArrowsClockwise, Trash } from '@phosphor-icons/react'
import {
  ExplorerPanel, DetailsPanel, Table, Button, Badge, 
  StatusIndicator, Modal, Input, Select, ExportDropdown,
  Tabs, LoadingSpinner, EmptyState
} from '../components'
import { certificatesService } from '../services'
import { useNotification } from '../contexts'
import { extractCN, extractData, formatDate } from '../lib/utils'

export default function CertificatesPage() {
  const { showSuccess, showError } = useNotification()
  
  const [certificates, setCertificates] = useState([])
  const [selectedCert, setSelectedCert] = useState(null)
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)

  useEffect(() => {
    loadCertificates()
  }, [page, statusFilter, searchQuery])

  const loadCertificates = async () => {
    setLoading(true)
    try {
      const data = await certificatesService.getAll({
        page,
        per_page: 20,
        status: statusFilter !== 'all' ? statusFilter : undefined,
        search: searchQuery || undefined,
      })
      // API returns {data: [...], meta: {...}}
      const certsList = data.data || []
      setCertificates(certsList)
      setTotal(data.meta?.total || 0)
      if (certsList.length > 0 && !selectedCert) {
        loadCertificateDetails(certsList[0].id)
      }
    } catch (error) {
      showError(error.message || 'Failed to load certificates')
    } finally {
      setLoading(false)
    }
  }

  const loadCertificateDetails = async (id) => {
    try {
      const response = await certificatesService.getById(id)
      const certData = extractData(response)
      console.log('Certificate details loaded:', certData)
      setSelectedCert({ ...certData }) // Force new object reference
    } catch (error) {
      console.error('Failed to load certificate details:', error)
      showError(error.message || 'Failed to load certificate details')
    }
  }

  const handleRevoke = async (id) => {
    if (!confirm('Are you sure you want to revoke this certificate?')) return
    
    try {
      await certificatesService.revoke(id, 'superseded')
      showSuccess('Certificate revoked successfully')
      loadCertificates()
    } catch (error) {
      showError(error.message || 'Failed to revoke certificate')
    }
  }

  const handleRenew = async (id) => {
    try {
      await certificatesService.renew(id)
      showSuccess('Certificate renewed successfully')
      loadCertificates()
    } catch (error) {
      showError(error.message || 'Failed to renew certificate')
    }
  }

  const handleExport = async (id, format = 'pem') => {
    try {
      const blob = await certificatesService.export(id, format)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `certificate.${format}`
      a.click()
      showSuccess('Certificate exported successfully')
    } catch (error) {
      showError(error.message || 'Failed to export certificate')
    }
  }

  const certColumns = [
    { 
      key: 'subject', 
      label: 'Common Name',
      render: (val) => <span className="font-medium">{extractCN(val)}</span>
    },
    {
      key: 'status',
      label: 'Status',
      render: (val) => (
        <div className="flex items-center gap-2">
          <StatusIndicator status={val} />
          <Badge variant={
            val === 'valid' ? 'success' : 
            val === 'expiring' ? 'warning' : 
            'danger'
          }>
            {val}
          </Badge>
        </div>
      )
    },
    { 
      key: 'valid_to', 
      label: 'Expires',
      render: (val) => formatDate(val)
    },
    { 
      key: 'issuer', 
      label: 'Issuer',
      render: (val) => extractCN(val)
    },
  ]

  const detailTabs = selectedCert ? [
    {
      id: 'overview',
      label: 'Overview',
      icon: <Certificate size={16} />,
      content: (
        <div className="space-y-6">
          {/* Status & Type */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-xs text-text-secondary uppercase mb-1">Status</p>
              <div className="flex items-center gap-2">
                <StatusIndicator status={selectedCert.status} />
                <Badge variant={selectedCert.revoked ? 'danger' : 'success'}>
                  {selectedCert.revoked ? 'Revoked' : selectedCert.status || 'Active'}
                </Badge>
              </div>
            </div>
            <div>
              <p className="text-xs text-text-secondary uppercase mb-1">Certificate Type</p>
              <Badge variant="secondary">{selectedCert.cert_type || 'Standard'}</Badge>
            </div>
          </div>

          {/* Subject Information */}
          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-3">Subject Information</h3>
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <p className="text-xs text-text-secondary uppercase mb-1">Common Name (CN)</p>
                <p className="text-sm text-text-primary font-medium">{selectedCert.common_name || 'N/A'}</p>
              </div>
              {selectedCert.organization && (
                <div className="col-span-2">
                  <p className="text-xs text-text-secondary uppercase mb-1">Organization (O)</p>
                  <p className="text-sm text-text-primary">{selectedCert.organization}</p>
                </div>
              )}
              {selectedCert.organizational_unit && (
                <div className="col-span-2">
                  <p className="text-xs text-text-secondary uppercase mb-1">Organizational Unit (OU)</p>
                  <p className="text-sm text-text-primary">{selectedCert.organizational_unit}</p>
                </div>
              )}
            </div>
          </div>

          {/* Certificate Details */}
          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-3">Certificate Details</h3>
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <p className="text-xs text-text-secondary uppercase mb-1">Serial Number</p>
                <p className="text-sm font-mono text-text-primary break-all">{selectedCert.serial_number}</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary uppercase mb-1">Valid From</p>
                <p className="text-sm text-text-primary">{formatDate(selectedCert.valid_from)}</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary uppercase mb-1">Valid Until</p>
                <p className="text-sm text-text-primary">{formatDate(selectedCert.valid_to)}</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary uppercase mb-1">Key Algorithm</p>
                <p className="text-sm text-text-primary">{selectedCert.key_algorithm || selectedCert.key_type || 'N/A'}</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary uppercase mb-1">Key Size</p>
                <p className="text-sm text-text-primary">{selectedCert.key_size ? `${selectedCert.key_size} bits` : 'N/A'}</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary uppercase mb-1">Signature Algorithm</p>
                <p className="text-sm text-text-primary">{selectedCert.signature_algorithm || 'N/A'}</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary uppercase mb-1">Private Key</p>
                <Badge variant={selectedCert.has_private_key ? 'success' : 'warning'}>
                  {selectedCert.has_private_key ? 'Available' : 'Not Available'}
                </Badge>
              </div>
            </div>
          </div>

          {/* Issuer Information */}
          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-3">Issuer Information</h3>
            <div className="space-y-3">
              <div>
                <p className="text-xs text-text-secondary uppercase mb-1">Issuer Name</p>
                <p className="text-sm text-text-primary">{selectedCert.issuer_name || extractCN(selectedCert.issuer)}</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary uppercase mb-1">Full Issuer DN</p>
                <p className="text-xs font-mono text-text-primary break-all">{selectedCert.issuer}</p>
              </div>
            </div>
          </div>

          {/* OCSP */}
          {selectedCert.ocsp_uri && (
            <div className="p-3 bg-bg-tertiary border border-border rounded-lg">
              <p className="text-xs text-text-secondary uppercase mb-1">OCSP Responder</p>
              <p className="text-xs font-mono text-text-primary break-all">{selectedCert.ocsp_uri}</p>
            </div>
          )}

          {/* Revocation Info */}
          {selectedCert.revoked && (
            <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
              <h3 className="text-sm font-semibold text-red-400 mb-3">Revocation Information</h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-xs text-text-secondary uppercase mb-1">Revoked At</p>
                  <p className="text-sm text-text-primary">{formatDateTime(selectedCert.revoked_at)}</p>
                </div>
                <div>
                  <p className="text-xs text-text-secondary uppercase mb-1">Reason</p>
                  <p className="text-sm text-text-primary">{selectedCert.revoke_reason || 'Unspecified'}</p>
                </div>
              </div>
            </div>
          )}

          {/* Full Subject DN */}
          <div className="p-4 bg-bg-tertiary border border-border rounded-lg">
            <p className="text-xs text-text-secondary uppercase mb-2">Full Subject DN</p>
            <p className="text-xs font-mono text-text-primary break-all">
              {selectedCert.subject}
            </p>
          </div>
        </div>
      )
    },
    {
      id: 'extensions',
      label: 'Extensions',
      icon: <Certificate size={16} />,
      content: (
        <div className="space-y-6">
          {/* Subject Alternative Names */}
          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-3">Subject Alternative Names (SAN)</h3>
            
            {/* DNS Names */}
            {selectedCert.san_dns && JSON.parse(selectedCert.san_dns).length > 0 && (
              <div className="mb-4">
                <p className="text-xs text-text-secondary uppercase mb-2">DNS Names</p>
                <div className="flex flex-wrap gap-2">
                  {JSON.parse(selectedCert.san_dns).map((dns, i) => (
                    <Badge key={i} variant="secondary">{dns}</Badge>
                  ))}
                </div>
              </div>
            )}
            
            {/* IP Addresses */}
            {selectedCert.san_ip && JSON.parse(selectedCert.san_ip).length > 0 && (
              <div className="mb-4">
                <p className="text-xs text-text-secondary uppercase mb-2">IP Addresses</p>
                <div className="flex flex-wrap gap-2">
                  {JSON.parse(selectedCert.san_ip).map((ip, i) => (
                    <Badge key={i} variant="secondary">{ip}</Badge>
                  ))}
                </div>
              </div>
            )}
            
            {/* Email Addresses */}
            {selectedCert.san_email && JSON.parse(selectedCert.san_email).length > 0 && (
              <div className="mb-4">
                <p className="text-xs text-text-secondary uppercase mb-2">Email Addresses</p>
                <div className="flex flex-wrap gap-2">
                  {JSON.parse(selectedCert.san_email).map((email, i) => (
                    <Badge key={i} variant="secondary">{email}</Badge>
                  ))}
                </div>
              </div>
            )}
            
            {/* URIs */}
            {selectedCert.san_uri && JSON.parse(selectedCert.san_uri).length > 0 && (
              <div className="mb-4">
                <p className="text-xs text-text-secondary uppercase mb-2">URIs</p>
                <div className="flex flex-wrap gap-2">
                  {JSON.parse(selectedCert.san_uri).map((uri, i) => (
                    <Badge key={i} variant="secondary">{uri}</Badge>
                  ))}
                </div>
              </div>
            )}
            
            {(!selectedCert.san_dns && !selectedCert.san_ip && !selectedCert.san_email && !selectedCert.san_uri) && (
              <p className="text-sm text-text-secondary">No subject alternative names configured</p>
            )}
          </div>

          {/* Key Usage */}
          {selectedCert.key_usage && (
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-3">Key Usage</h3>
              <div className="flex flex-wrap gap-2">
                {selectedCert.key_usage.map((usage, i) => (
                  <Badge key={i} variant="primary">{usage}</Badge>
                ))}
              </div>
            </div>
          )}
          
          {/* Extended Key Usage */}
          {selectedCert.extended_key_usage && (
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-3">Extended Key Usage</h3>
              <div className="flex flex-wrap gap-2">
                {selectedCert.extended_key_usage.map((usage, i) => (
                  <Badge key={i} variant="primary">{usage}</Badge>
                ))}
              </div>
            </div>
          )}
        </div>
      )
    },
    {
      id: 'raw',
      label: 'Raw Data',
      content: (
        <div className="space-y-6">
          <div>
            <p className="text-sm font-medium text-text-primary mb-2">PEM Format</p>
            <pre className="bg-bg-tertiary border border-border rounded-lg p-4 text-xs overflow-x-auto">
              {selectedCert.pem}
            </pre>
          </div>
          <div className="p-4 bg-bg-tertiary border border-border rounded-lg">
            <p className="text-xs text-text-secondary uppercase mb-2">Certificate Fingerprints</p>
            <div className="space-y-2">
              <div>
                <p className="text-xs text-text-secondary">SHA-256</p>
                <p className="text-xs font-mono text-text-primary break-all">
                  {selectedCert.fingerprint_sha256}
                </p>
              </div>
              <div>
                <p className="text-xs text-text-secondary">SHA-1</p>
                <p className="text-xs font-mono text-text-primary break-all">
                  {selectedCert.fingerprint_sha1}
                </p>
              </div>
            </div>
          </div>
        </div>
      )
    }
  ] : []

  // No need to filter client-side - backend does it
  const filteredCerts = certificates

  return (
    <>
      <ExplorerPanel
        title={selectedCert?.common_name || 'Select a certificate'}
        actions={selectedCert && (
          <>
            <ExportDropdown 
              onExport={(format) => handleExport(selectedCert.id, format)} 
              formats={['pem', 'der', 'pkcs12']}
            />
            <Button variant="secondary" size="sm" onClick={() => handleRenew(selectedCert.id)}>
              <ArrowsClockwise size={16} />
              Renew
            </Button>
            <Button variant="danger" size="sm" onClick={() => handleRevoke(selectedCert.id)}>
              <X size={16} />
              Revoke
            </Button>
          </>
        )}
      >
        {!selectedCert ? (
          <EmptyState
            title="No certificate selected"
            description="Select a certificate from the list to view details"
          />
        ) : (
          <Tabs key={selectedCert.id} tabs={detailTabs} defaultTab="overview" />
        )}
      </ExplorerPanel>

      <DetailsPanel
        breadcrumb={[
          { label: 'Certificates' },
          { label: `${total} certificates` }
        ]}
        title="Certificates"
        searchable
        searchValue={searchQuery}
        onSearch={setSearchQuery}
      >
        <div className="p-4 space-y-3">
          <Select
            label="Filter by Status"
            options={[
              { value: 'all', label: 'All Certificates' },
              { value: 'valid', label: 'Valid' },
              { value: 'expiring', label: 'Expiring Soon' },
              { value: 'expired', label: 'Expired' },
              { value: 'revoked', label: 'Revoked' },
            ]}
            value={statusFilter}
            onChange={setStatusFilter}
          />

          <Button onClick={() => setShowCreateModal(true)} className="w-full">
            <Certificate size={18} />
            Issue Certificate
          </Button>
        </div>

        <div className="flex-1 overflow-auto">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <LoadingSpinner />
            </div>
          ) : filteredCerts.length === 0 ? (
            <EmptyState
              icon={Certificate}
              title="No certificates"
              description="Issue your first certificate to get started"
            />
          ) : (
            <Table
              columns={certColumns}
              data={filteredCerts}
              onRowClick={(cert) => loadCertificateDetails(cert.id)}
              pagination={{
                total,
                page,
                perPage: 20,
                onChange: setPage
              }}
            />
          )}
        </div>
      </DetailsPanel>

      {/* Create Certificate Modal */}
      <Modal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Issue New Certificate"
      >
        <p className="text-text-secondary mb-4">Certificate creation form will be implemented here</p>
        <Button onClick={() => setShowCreateModal(false)}>Close</Button>
      </Modal>
    </>
  )
}
