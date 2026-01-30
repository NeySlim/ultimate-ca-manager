/**
 * Certificates Page - Using PageLayout with Responsive Components
 */
import { useState, useEffect, useRef } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { 
  Certificate, Download, X, ArrowsClockwise, Trash, UploadSimple,
  ShieldCheck, Clock, Warning, Database, CheckCircle, Key
} from '@phosphor-icons/react'
import {
  PageLayout, FocusItem, Table, Button, Badge, Card,
  StatusIndicator, Modal, Input, Select, ExportDropdown,
  Tabs, LoadingSpinner, EmptyState, HelpCard,
  DetailHeader, DetailSection, DetailGrid, DetailField, DetailDivider, DetailContent, DetailTabs
} from '../components'
import { certificatesService, casService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useModals, useDebounce } from '../hooks'
import { extractCN, extractData, formatDate, safeJsonParse } from '../lib/utils'

export default function CertificatesPage() {
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canWrite, canDelete } = usePermission()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const { modals, open: openModal, close: closeModal } = useModals(['create', 'import'])
  
  const [certificates, setCertificates] = useState([])
  const [selectedCert, setSelectedCert] = useState(null)
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const debouncedSearch = useDebounce(searchQuery, 300)
  const [statusFilter, setStatusFilter] = useState('all')
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)
  const [total, setTotal] = useState(0)
  const [cas, setCas] = useState([])
  const [importFile, setImportFile] = useState(null)
  const [importName, setImportName] = useState('')
  const [importPassword, setImportPassword] = useState('')
  const [importCaId, setImportCaId] = useState('auto')
  const [importing, setImporting] = useState(false)
  const [activeTab, setActiveTab] = useState('overview')
  const importFileRef = useRef(null)

  useEffect(() => {
    loadCertificates()
    loadCAs()
    if (searchParams.get('action') === 'create') {
      openModal('create')
      searchParams.delete('action')
      setSearchParams(searchParams)
    }
  }, [page, perPage, statusFilter, debouncedSearch])

  // Handle selected param from navigation (e.g., after import redirect)
  useEffect(() => {
    const selectedId = searchParams.get('selected')
    if (selectedId && certificates.length > 0) {
      const cert = certificates.find(c => c.id === parseInt(selectedId))
      if (cert) {
        setSelectedCert(cert)
        searchParams.delete('selected')
        setSearchParams(searchParams)
      } else {
        // Load the specific certificate if not in current page
        loadCertificateDetails(parseInt(selectedId))
        searchParams.delete('selected')
        setSearchParams(searchParams)
      }
    }
  }, [certificates, searchParams])

  const loadCAs = async () => {
    try {
      const response = await casService.getAll()
      setCas(response.data || [])
    } catch (e) {
      // Ignore
    }
  }

  const loadCertificates = async () => {
    setLoading(true)
    try {
      const data = await certificatesService.getAll({
        page,
        per_page: perPage,
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
      setSelectedCert({ ...certData }) // Force new object reference
    } catch (error) {
      showError(error.message || 'Failed to load certificate details')
    }
  }

  const handleRevoke = async (id) => {
    const confirmed = await showConfirm('Are you sure you want to revoke this certificate?', {
      title: 'Revoke Certificate',
      confirmText: 'Revoke',
      variant: 'danger'
    })
    if (!confirmed) return
    
    try {
      await certificatesService.revoke(id, 'superseded')
      showSuccess('Certificate revoked successfully')
      loadCertificates()
    } catch (error) {
      showError(error.message || 'Failed to revoke certificate')
    }
  }

  const handleDelete = async (id) => {
    const confirmed = await showConfirm('Are you sure you want to permanently delete this certificate? This action cannot be undone.', {
      title: 'Delete Certificate',
      confirmText: 'Delete',
      variant: 'danger'
    })
    if (!confirmed) return
    
    try {
      await certificatesService.delete(id)
      showSuccess('Certificate deleted successfully')
      setSelectedCert(null)
      loadCertificates()
    } catch (error) {
      showError(error.message || 'Failed to delete certificate')
    }
  }

  const handleRenew = async (id) => {
    try {
      const response = await certificatesService.renew(id)
      const newCertId = response.data?.id
      showSuccess(response.message || 'Certificate renewed successfully')
      await loadCertificates()
      // Select the new certificate
      if (newCertId) {
        loadCertificateDetails(newCertId)
      }
    } catch (error) {
      showError(error.message || 'Failed to renew certificate')
    }
  }

  const handleImportCertificate = async () => {
    if (!importFile) {
      showError('Please select a file')
      return
    }
    setImporting(true)
    try {
      const formData = new FormData()
      formData.append('file', importFile)
      if (importName) formData.append('name', importName)
      if (importPassword) formData.append('password', importPassword)
      if (importCaId && importCaId !== 'auto') formData.append('ca_id', importCaId)
      formData.append('format', 'auto')
      
      const result = await certificatesService.import(formData)
      showSuccess(result.message || 'Certificate imported successfully')
      closeModal('import')
      setImportFile(null)
      setImportName('')
      setImportPassword('')
      setImportCaId('auto')
      
      // If CA was detected, navigate to CAs page with the new CA selected
      if (result.data && result.message?.includes('CA')) {
        navigate(`/cas?selected=${result.data.id}`)
      } else if (result.data) {
        // Regular certificate - select it here
        await loadCertificates()
        setSelectedCert(result.data)
      }
    } catch (error) {
      showError(error.message || 'Failed to import certificate')
    } finally {
      setImporting(false)
    }
  }

  const handleExport = async (format = 'pem', options = {}) => {
    if (!selectedCert) return
    try {
      const blob = await certificatesService.export(selectedCert.id, format, options)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      // Determine file extension
      const ext = format === 'pkcs12' ? 'p12' : format === 'der' ? 'der' : 'pem'
      a.download = `${selectedCert.common_name || selectedCert.descr || 'certificate'}.${ext}`
      a.click()
      URL.revokeObjectURL(url)
      showSuccess('Certificate exported successfully')
    } catch (error) {
      showError(error.message || 'Failed to export certificate')
    }
  }

  // Calculate statistics
  const validCount = certificates.filter(c => c.status === 'valid').length
  const expiringCount = certificates.filter(c => c.status === 'expiring').length
  const expiredCount = certificates.filter(c => c.status === 'expired').length
  const revokedCount = certificates.filter(c => c.status === 'revoked' || c.revoked).length

  // Help content for modal
  const helpContent = (
    <div className="space-y-4">
      {/* Certificate Statistics */}
      <Card className="p-4 space-y-3 bg-gradient-to-br from-accent-primary/5 to-transparent">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Database size={16} className="text-accent-primary" />
          Certificate Statistics
        </h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-status-success">{validCount}</p>
            <p className="text-xs text-text-secondary">Valid</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-status-warning">{expiringCount}</p>
            <p className="text-xs text-text-secondary">Expiring Soon</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-status-error">{expiredCount}</p>
            <p className="text-xs text-text-secondary">Expired</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-text-tertiary">{revokedCount}</p>
            <p className="text-xs text-text-secondary">Revoked</p>
          </div>
        </div>
      </Card>

      {/* Help Cards */}
      <div className="space-y-3">
        <HelpCard variant="info" title="About Certificates">
          Digital certificates bind public keys to identities. They are signed by a 
          Certificate Authority to establish trust and enable secure communications.
        </HelpCard>
        
        <HelpCard variant="tip" title="Certificate Renewal">
          Renewing a certificate creates a new certificate with the same subject but 
          fresh validity dates. The old certificate remains valid until it expires.
        </HelpCard>

        <HelpCard variant="warning" title="Revocation">
          Revoked certificates are added to the CRL and cannot be un-revoked. 
          Always verify the certificate before revoking as this action is permanent.
        </HelpCard>
      </div>
    </div>
  )

  // Focus panel content (certificate list)
  const focusContent = (
    <div className="flex flex-col h-full">
      {/* Search and Filter */}
      <div className="p-3 space-y-2 border-b border-border">
        <Input
          placeholder="Search certificates..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="text-sm"
        />
        <Select
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
      </div>

      {/* Certificate List */}
      <div className="flex-1 overflow-auto p-2 space-y-1.5">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <LoadingSpinner />
          </div>
        ) : certificates.length === 0 ? (
          <EmptyState
            icon={Certificate}
            title="No certificates"
            description="Issue your first certificate"
          />
        ) : (
          certificates.map((cert) => {
            const isSelected = selectedCert?.id === cert.id
            return (
              <FocusItem
                key={cert.id}
                icon={Certificate}
                title={extractCN(cert.subject) || cert.common_name || 'Certificate'}
                subtitle={`Expires ${formatDate(cert.valid_to)}`}
                badge={
                  <Badge 
                    variant={
                      cert.status === 'valid' ? 'success' : 
                      cert.status === 'expiring' ? 'warning' : 
                      'danger'
                    }
                    size="sm"
                  >
                    {cert.status}
                  </Badge>
                }
                selected={isSelected}
                onClick={() => loadCertificateDetails(cert.id)}
              />
            )
          })
        )}
      </div>
    </div>
  )

  // Focus panel actions (buttons)
  const focusActions = canWrite('certificates') && (
    <>
      <Button size="sm" onClick={() => openModal('create')} className="flex-1">
        <Certificate size={16} />
        Issue
      </Button>
      <Button variant="secondary" size="sm" onClick={() => openModal('import')}>
        <UploadSimple size={16} />
      </Button>
    </>
  )

  if (loading && certificates.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner />
      </div>
    )
  }

  return (
    <>
      <PageLayout
        title="Certificates"
        focusTitle="Certificates"
        focusContent={focusContent}
        focusActions={focusActions}
        focusFooter={`${total} certificate(s)`}
        helpContent={helpContent}
        helpTitle="Certificates - Help"
      >
        {/* Main Content - Certificate Details */}
        {!selectedCert ? (
          <div className="flex items-center justify-center h-full">
            <EmptyState
              icon={Certificate}
              title="No certificate selected"
              description="Select a certificate from the list to view details"
            />
          </div>
        ) : (
          <>
            {/* Header with gradient card style */}
            <div className="p-4 md:p-6">
              <DetailHeader
                icon={Certificate}
                title={selectedCert.common_name || extractCN(selectedCert.subject) || 'Certificate Details'}
                subtitle={selectedCert.subject}
                badge={
                  <Badge 
                    variant={
                      selectedCert.revoked ? 'red' : 
                      selectedCert.status === 'expired' ? 'red' :
                      selectedCert.status === 'expiring' ? 'amber' :
                      selectedCert.status === 'valid' ? 'emerald' :
                      'secondary'
                    } 
                    size="lg"
                  >
                    {selectedCert.status === 'valid' && <CheckCircle size={14} weight="fill" />}
                    {selectedCert.status === 'expiring' && <Warning size={14} weight="fill" />}
                    {selectedCert.revoked ? 'Revoked' : selectedCert.status || 'Active'}
                  </Badge>
                }
                stats={[
                  { icon: Clock, label: 'Expires', value: formatDate(selectedCert.valid_to) },
                  { icon: Key, label: 'Key:', value: selectedCert.key_algorithm || selectedCert.key_type || 'RSA' },
                  ...(selectedCert.has_private_key ? [{ icon: ShieldCheck, label: 'Private Key:', value: 'Available' }] : []),
                ]}
                actions={[
                  { label: 'Export', icon: Download, onClick: () => handleExport('pem') },
                  ...(canWrite('certificates') ? [{ label: 'Renew', icon: ArrowsClockwise, onClick: () => handleRenew(selectedCert.id) }] : []),
                  ...(canDelete('certificates') ? [{ label: 'Revoke', icon: X, variant: 'danger', onClick: () => handleRevoke(selectedCert.id) }] : []),
                  ...(canDelete('certificates') ? [{ label: 'Delete', icon: Trash, variant: 'danger', onClick: () => handleDelete(selectedCert.id) }] : []),
                ]}
              />
            </div>

            {/* Tabs Navigation */}
            <DetailTabs
              tabs={[
                { id: 'overview', label: 'Overview', icon: Certificate },
                { id: 'usage', label: 'Usage', icon: ShieldCheck },
                { id: 'pem', label: 'PEM', icon: Database },
              ]}
              activeTab={activeTab}
              onChange={setActiveTab}
            />

            {/* Tab Content */}
            <DetailContent>
              {/* Overview Tab */}
              {activeTab === 'overview' && (
                <>
                  {/* Subject Information */}
                  <DetailSection title="Subject Information">
                    <DetailGrid columns={2}>
                      <DetailField label="Common Name (CN)" value={selectedCert.common_name} />
                      <DetailField label="Organization (O)" value={selectedCert.organization} />
                      {selectedCert.organizational_unit && (
                        <DetailField label="Organizational Unit (OU)" value={selectedCert.organizational_unit} />
                      )}
                      {selectedCert.country && (
                        <DetailField label="Country (C)" value={selectedCert.country} />
                      )}
                      <DetailField label="Full Subject DN" value={selectedCert.subject} mono copyable fullWidth />
                    </DetailGrid>
                  </DetailSection>

                  <DetailDivider />

                  {/* Validity Period */}
                  <DetailSection title="Validity Period">
                    <DetailGrid columns={2}>
                      <DetailField label="Not Before" value={formatDate(selectedCert.valid_from)} />
                      <DetailField label="Not After" value={formatDate(selectedCert.valid_to)} />
                    </DetailGrid>
                  </DetailSection>

                  <DetailDivider />

                  {/* Issuer Information */}
                  <DetailSection title="Issuer Information">
                    <DetailGrid columns={2}>
                      <DetailField label="Issuer Name" value={selectedCert.issuer_name || extractCN(selectedCert.issuer)} />
                      <DetailField label="Full Issuer DN" value={selectedCert.issuer} mono fullWidth />
                    </DetailGrid>
                  </DetailSection>

                  <DetailDivider />

                  {/* Technical Details */}
                  <DetailSection title="Technical Details">
                    <DetailGrid columns={2}>
                      <DetailField label="Key Algorithm" value={selectedCert.key_algorithm || selectedCert.key_type} />
                      <DetailField label="Key Size" value={selectedCert.key_size ? `${selectedCert.key_size} bits` : null} />
                      <DetailField label="Signature Algorithm" value={selectedCert.signature_algorithm} />
                      <DetailField 
                        label="Private Key" 
                        value={
                          <Badge variant={selectedCert.has_private_key ? 'success' : 'warning'}>
                            {selectedCert.has_private_key ? 'Available' : 'Not Available'}
                          </Badge>
                        }
                      />
                      <DetailField label="Serial Number" value={selectedCert.serial_number} mono copyable fullWidth />
                    </DetailGrid>
                  </DetailSection>

                  {/* Revocation Info */}
                  {selectedCert.revoked && (
                    <>
                      <DetailDivider />
                      <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg mt-4">
                        <h3 className="text-sm font-semibold text-red-400 mb-3">Revocation Information</h3>
                        <DetailGrid columns={2}>
                          <DetailField label="Revoked At" value={formatDate(selectedCert.revoked_at)} />
                          <DetailField label="Reason" value={selectedCert.revoke_reason || 'Unspecified'} />
                        </DetailGrid>
                      </div>
                    </>
                  )}

                  {/* OCSP */}
                  {selectedCert.ocsp_uri && (
                    <>
                      <DetailDivider />
                      <DetailSection title="OCSP Responder">
                        <DetailGrid columns={1}>
                          <DetailField label="OCSP URI" value={selectedCert.ocsp_uri} mono copyable fullWidth />
                        </DetailGrid>
                      </DetailSection>
                    </>
                  )}
                </>
              )}

              {/* Usage Tab */}
              {activeTab === 'usage' && (
                <>
                  {/* Subject Alternative Names */}
                  <DetailSection title="Subject Alternative Names (SAN)">
                    <div className="space-y-3">
                      {selectedCert.san_dns && safeJsonParse(selectedCert.san_dns).length > 0 && (
                        <div>
                          <p className="text-xs text-text-tertiary uppercase tracking-wide mb-2">DNS Names</p>
                          <div className="flex flex-wrap gap-2">
                            {safeJsonParse(selectedCert.san_dns).map((dns, i) => (
                              <Badge key={i} variant="secondary">{dns}</Badge>
                            ))}
                          </div>
                        </div>
                      )}
                      {selectedCert.san_ip && safeJsonParse(selectedCert.san_ip).length > 0 && (
                        <div>
                          <p className="text-xs text-text-tertiary uppercase tracking-wide mb-2">IP Addresses</p>
                          <div className="flex flex-wrap gap-2">
                            {safeJsonParse(selectedCert.san_ip).map((ip, i) => (
                              <Badge key={i} variant="secondary">{ip}</Badge>
                            ))}
                          </div>
                        </div>
                      )}
                      {selectedCert.san_email && safeJsonParse(selectedCert.san_email).length > 0 && (
                        <div>
                          <p className="text-xs text-text-tertiary uppercase tracking-wide mb-2">Email Addresses</p>
                          <div className="flex flex-wrap gap-2">
                            {safeJsonParse(selectedCert.san_email).map((email, i) => (
                              <Badge key={i} variant="secondary">{email}</Badge>
                            ))}
                          </div>
                        </div>
                      )}
                      {selectedCert.san_uri && safeJsonParse(selectedCert.san_uri).length > 0 && (
                        <div>
                          <p className="text-xs text-text-tertiary uppercase tracking-wide mb-2">URIs</p>
                          <div className="flex flex-wrap gap-2">
                            {safeJsonParse(selectedCert.san_uri).map((uri, i) => (
                              <Badge key={i} variant="secondary">{uri}</Badge>
                            ))}
                          </div>
                        </div>
                      )}
                      {(!selectedCert.san_dns && !selectedCert.san_ip && !selectedCert.san_email && !selectedCert.san_uri) && (
                        <p className="text-sm text-text-secondary">No subject alternative names configured</p>
                      )}
                    </div>
                  </DetailSection>

                  <DetailDivider />

                  {/* Key Usage */}
                  <DetailSection title="Key Usage">
                    {selectedCert.key_usage ? (
                      <div className="flex flex-wrap gap-2">
                        {selectedCert.key_usage.map((usage, i) => (
                          <Badge key={i} variant="primary">{usage}</Badge>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-text-secondary">No key usage defined</p>
                    )}
                  </DetailSection>

                  <DetailDivider />

                  {/* Extended Key Usage */}
                  <DetailSection title="Extended Key Usage">
                    {selectedCert.extended_key_usage ? (
                      <div className="flex flex-wrap gap-2">
                        {selectedCert.extended_key_usage.map((usage, i) => (
                          <Badge key={i} variant="primary">{usage}</Badge>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-text-secondary">No extended key usage defined</p>
                    )}
                  </DetailSection>
                </>
              )}

              {/* PEM Tab */}
              {activeTab === 'pem' && (
                <>
                  {/* Certificate Fingerprints */}
                  <DetailSection title="Certificate Fingerprints">
                    <DetailGrid columns={1}>
                      <DetailField label="SHA-256" value={selectedCert.fingerprint_sha256} mono copyable fullWidth />
                      <DetailField label="SHA-1" value={selectedCert.fingerprint_sha1} mono copyable fullWidth />
                    </DetailGrid>
                  </DetailSection>

                  <DetailDivider />

                  {/* PEM Data */}
                  <DetailSection title="PEM Format">
                    <div className="flex items-center justify-end mb-2">
                      <Button 
                        variant="secondary" 
                        size="sm"
                        onClick={() => {
                          navigator.clipboard.writeText(selectedCert.pem || '')
                          showSuccess('PEM copied to clipboard')
                        }}
                        disabled={!selectedCert.pem}
                      >
                        Copy PEM
                      </Button>
                    </div>
                    <pre className="bg-bg-tertiary border border-border rounded-lg p-4 text-xs overflow-x-auto max-h-64">
                      {selectedCert.pem || 'PEM data not available'}
                    </pre>
                  </DetailSection>
                </>
              )}
            </DetailContent>
          </>
        )}
      </PageLayout>

      {/* Create Certificate Modal */}
      <Modal
        open={modals.create}
        onClose={() => closeModal('create')}
        title="Issue New Certificate"
        size="lg"
      >
        <form onSubmit={async (e) => {
          e.preventDefault()
          const formData = new FormData(e.target)
          const data = {
            cn: formData.get('cn'),
            ca_id: parseInt(formData.get('ca_id')),
            validity_days: parseInt(formData.get('validity_days')),
            key_type: formData.get('key_type'),
            san_dns: formData.get('san_dns') ? formData.get('san_dns').split(',').map(s => s.trim()) : []
          }
          
          try {
            await certificatesService.create(data)
            showSuccess('Certificate issued successfully')
            closeModal('create')
            loadCertificates()
          } catch (error) {
            showError(error.message || 'Failed to issue certificate')
          }
        }} className="space-y-4">
          
          <Input
            name="cn"
            label="Common Name (CN)"
            placeholder="example.com"
            required
          />
          
          <Select
            name="ca_id"
            label="Issuing CA"
            options={[
              { value: '1', label: 'Root CA' },
              { value: '2', label: 'Intermediate CA' }
            ]}
            required
          />
          
          <Input
            name="san_dns"
            label="Subject Alternative Names (SANs)"
            placeholder="www.example.com, api.example.com"
            helperText="Comma-separated DNS names"
          />
          
          <div className="grid grid-cols-2 gap-4">
            <Select
              name="validity_days"
              label="Validity Period"
              options={[
                { value: '90', label: '90 days' },
                { value: '180', label: '180 days' },
                { value: '365', label: '1 year' },
                { value: '730', label: '2 years' }
              ]}
              defaultValue="365"
            />
            
            <Select
              name="key_type"
              label="Key Type"
              options={[
                { value: 'RSA-2048', label: 'RSA 2048' },
                { value: 'RSA-4096', label: 'RSA 4096' },
                { value: 'ECDSA-P256', label: 'ECDSA P-256' }
              ]}
              defaultValue="RSA-2048"
            />
          </div>

          <div className="flex gap-3 justify-end pt-4 border-t border-border">
            <Button
              type="button"
              variant="secondary"
              onClick={() => closeModal('create')}
            >
              Cancel
            </Button>
            <Button type="submit">
              Issue Certificate
            </Button>
          </div>
        </form>
      </Modal>

      {/* Import Certificate Modal */}
      <Modal
        open={modals.import}
        onClose={() => closeModal('import')}
        title="Import Certificate"
        size="md"
      >
        <div className="space-y-4">
          <p className="text-sm text-text-secondary">
            Import an existing certificate from a file. Supports PEM, DER, and PKCS#12 formats.
          </p>
          
          <div>
            <label className="block text-xs font-medium text-text-primary mb-1">Certificate File</label>
            <input
              ref={importFileRef}
              type="file"
              accept=".pem,.crt,.cer,.der,.p12,.pfx"
              onChange={(e) => setImportFile(e.target.files[0])}
              className="w-full text-sm text-text-secondary file:mr-4 file:py-1.5 file:px-3 file:rounded-sm file:border-0 file:text-sm file:bg-accent-primary file:text-white hover:file:bg-accent-primary/80"
            />
            <p className="text-xs text-text-secondary mt-1">Accepted: .pem, .crt, .cer, .der, .p12, .pfx</p>
          </div>
          
          <Input 
            label="Display Name (optional)" 
            value={importName}
            onChange={(e) => setImportName(e.target.value)}
            placeholder="My Certificate"
          />
          
          <Input 
            label="Password (for PKCS#12)" 
            type="password"
            value={importPassword}
            onChange={(e) => setImportPassword(e.target.value)}
            placeholder="Enter password if needed"
          />
          
          <Select
            label="Link to CA (optional)"
            value={importCaId}
            onChange={(value) => setImportCaId(value)}
            options={[
              { value: 'auto', label: 'Auto-detect from issuer' },
              ...cas.map(ca => ({ value: ca.id.toString(), label: ca.name }))
            ]}
          />
          
          <div className="flex gap-3 justify-end pt-4 border-t border-border">
            <Button
              variant="secondary"
              onClick={() => closeModal('import')}
            >
              Cancel
            </Button>
            <Button onClick={handleImportCertificate} disabled={importing || !importFile}>
              {importing ? <LoadingSpinner size="sm" /> : <UploadSimple size={16} />}
              Import Certificate
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}
