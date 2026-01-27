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
  }, [page, statusFilter])

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
      const data = await certificatesService.getById(id)
      setSelectedCert(data)
    } catch (error) {
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
      key: 'common_name', 
      label: 'Common Name',
      render: (val) => <span className="font-medium">{val}</span>
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
      key: 'expires', 
      label: 'Expires',
      render: (val) => new Date(val).toLocaleDateString()
    },
    { key: 'issuer', label: 'Issuer' },
  ]

  const detailTabs = selectedCert ? [
    {
      id: 'overview',
      label: 'Overview',
      icon: <Certificate size={16} />,
      content: (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-xs text-text-secondary uppercase mb-1">Serial Number</p>
              <p className="text-sm font-mono text-text-primary">{selectedCert.serial_number}</p>
            </div>
            <div>
              <p className="text-xs text-text-secondary uppercase mb-1">Status</p>
              <div className="flex items-center gap-2">
                <StatusIndicator status={selectedCert.status} />
                <span className="text-sm">{selectedCert.status}</span>
              </div>
            </div>
            <div>
              <p className="text-xs text-text-secondary uppercase mb-1">Subject DN</p>
              <p className="text-sm text-text-primary">{selectedCert.subject}</p>
            </div>
            <div>
              <p className="text-xs text-text-secondary uppercase mb-1">Issuer DN</p>
              <p className="text-sm text-text-primary">{selectedCert.issuer}</p>
            </div>
            <div>
              <p className="text-xs text-text-secondary uppercase mb-1">Valid From</p>
              <p className="text-sm text-text-primary">{new Date(selectedCert.valid_from).toLocaleString()}</p>
            </div>
            <div>
              <p className="text-xs text-text-secondary uppercase mb-1">Valid Until</p>
              <p className="text-sm text-text-primary">{new Date(selectedCert.valid_to).toLocaleString()}</p>
            </div>
            <div>
              <p className="text-xs text-text-secondary uppercase mb-1">Signature Algorithm</p>
              <p className="text-sm text-text-primary">{selectedCert.signature_algorithm}</p>
            </div>
            <div>
              <p className="text-xs text-text-secondary uppercase mb-1">Key Algorithm</p>
              <p className="text-sm text-text-primary">{selectedCert.key_algorithm}</p>
            </div>
          </div>
        </div>
      )
    },
    {
      id: 'extensions',
      label: 'Extensions',
      content: (
        <div className="space-y-4">
          <div>
            <p className="text-sm font-medium text-text-primary mb-2">Key Usage</p>
            <div className="flex flex-wrap gap-2">
              {selectedCert.key_usage?.map((usage, i) => (
                <Badge key={i} variant="secondary">{usage}</Badge>
              )) || <p className="text-sm text-text-secondary">None</p>}
            </div>
          </div>
          <div>
            <p className="text-sm font-medium text-text-primary mb-2">Subject Alternative Names</p>
            <div className="flex flex-wrap gap-2">
              {selectedCert.san?.map((name, i) => (
                <Badge key={i} variant="secondary">{name}</Badge>
              )) || <p className="text-sm text-text-secondary">None</p>}
            </div>
          </div>
        </div>
      )
    },
    {
      id: 'raw',
      label: 'Raw Data',
      content: (
        <div className="space-y-4">
          <div>
            <p className="text-sm font-medium text-text-primary mb-2">PEM Format</p>
            <pre className="bg-bg-tertiary border border-border rounded-lg p-4 text-xs overflow-x-auto">
              {selectedCert.pem}
            </pre>
          </div>
          <div>
            <p className="text-sm font-medium text-text-primary mb-2">Fingerprints</p>
            <div className="space-y-2">
              <div>
                <p className="text-xs text-text-secondary">SHA-256</p>
                <p className="text-xs font-mono text-text-primary">{selectedCert.fingerprint_sha256}</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary">SHA-1</p>
                <p className="text-xs font-mono text-text-primary">{selectedCert.fingerprint_sha1}</p>
              </div>
            </div>
          </div>
        </div>
      )
    }
  ] : []

  const filteredCerts = certificates.filter(c => 
    c.common_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    c.issuer?.toLowerCase().includes(searchQuery.toLowerCase())
  )

  return (
    <>
      <ExplorerPanel
        title="Certificates"
        searchable
        searchValue={searchQuery}
        onSearch={setSearchQuery}
        footer={
          <div className="text-xs text-text-secondary">
            {total} total certificates
          </div>
        }
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
      </ExplorerPanel>

      <DetailsPanel
        breadcrumb={[
          { label: 'Certificates' },
          { label: selectedCert?.common_name || '...' }
        ]}
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
          <Tabs tabs={detailTabs} defaultTab="overview" />
        )}
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
