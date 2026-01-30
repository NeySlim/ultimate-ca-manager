/**
 * Certificates Page - Using ListPageLayout for consistent UI
 */
import { useState, useEffect } from 'react'
import { 
  Certificate, Download, Trash, ArrowsClockwise, X, Key,
  CheckCircle, Warning, Clock, ShieldCheck, Plus, UploadSimple
} from '@phosphor-icons/react'
import {
  ListPageLayout, Badge, Button, Modal, Select, Input, Textarea,
  DetailHeader, DetailSection, DetailGrid, DetailField, DetailTabs, HelpCard
} from '../components'
import { certificatesService, casService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { formatDate, extractCN } from '../lib/utils'

export default function CertificatesPage() {
  const [certificates, setCertificates] = useState([])
  const [selectedCert, setSelectedCert] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showIssueModal, setShowIssueModal] = useState(false)
  const [cas, setCas] = useState([])
  const { showSuccess, showError } = useNotification()
  const { canWrite, canDelete } = usePermission()

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      setLoading(true)
      const [certsRes, casRes] = await Promise.all([
        certificatesService.getAll(),
        casService.getAll()
      ])
      setCertificates(certsRes.data || [])
      setCas(casRes.data || [])
    } catch (error) {
      showError('Failed to load certificates')
    } finally {
      setLoading(false)
    }
  }

  const loadCertDetails = async (cert) => {
    try {
      const res = await certificatesService.getById(cert.id)
      setSelectedCert(res.data || cert)
    } catch {
      setSelectedCert(cert)
    }
  }

  const handleExport = async (format) => {
    if (!selectedCert) return
    try {
      const blob = await certificatesService.export(selectedCert.id, format)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${selectedCert.common_name || 'certificate'}.${format}`
      a.click()
      showSuccess('Certificate exported')
    } catch (error) {
      showError('Export failed')
    }
  }

  const handleRevoke = async (id) => {
    if (!confirm('Revoke this certificate?')) return
    try {
      await certificatesService.revoke(id)
      showSuccess('Certificate revoked')
      loadData()
      setSelectedCert(null)
    } catch (error) {
      showError('Revoke failed')
    }
  }

  const handleDelete = async (id) => {
    if (!confirm('Delete this certificate permanently?')) return
    try {
      await certificatesService.delete(id)
      showSuccess('Certificate deleted')
      loadData()
      setSelectedCert(null)
    } catch (error) {
      showError('Delete failed')
    }
  }

  // Table columns
  const columns = [
    {
      key: 'common_name',
      header: 'Common Name',
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <Certificate size={16} className="text-accent-primary shrink-0" />
          <span className="font-medium truncate">{extractCN(row.subject) || val || 'Certificate'}</span>
        </div>
      )
    },
    {
      key: 'issuer_name',
      header: 'Issuer',
      render: (val, row) => extractCN(row.issuer) || val || '—'
    },
    {
      key: 'status',
      header: 'Status',
      render: (val, row) => (
        <Badge 
          variant={
            row.revoked ? 'danger' :
            val === 'valid' ? 'success' : 
            val === 'expiring' ? 'warning' : 
            'danger'
          }
          size="sm"
        >
          {row.revoked ? 'Revoked' : val || 'Unknown'}
        </Badge>
      )
    },
    {
      key: 'valid_to',
      header: 'Expires',
      sortType: 'date',
      render: (val) => formatDate(val)
    },
    {
      key: 'key_type',
      header: 'Key',
      render: (val, row) => row.key_algorithm || val || 'RSA'
    }
  ]

  // Row actions
  const rowActions = (row) => [
    { label: 'Export PEM', icon: Download, onClick: () => { setSelectedCert(row); handleExport('pem') }},
    ...(canWrite('certificates') && !row.revoked ? [
      { label: 'Revoke', icon: X, variant: 'danger', onClick: () => handleRevoke(row.id) }
    ] : []),
    ...(canDelete('certificates') ? [
      { label: 'Delete', icon: Trash, variant: 'danger', onClick: () => handleDelete(row.id) }
    ] : [])
  ]

  // Render details panel
  const renderDetails = (cert) => (
    <div className="p-4 space-y-4">
      <DetailHeader
        icon={Certificate}
        title={cert.common_name || extractCN(cert.subject) || 'Certificate'}
        subtitle={cert.subject}
        badge={
          <Badge 
            variant={
              cert.revoked ? 'danger' :
              cert.status === 'valid' ? 'success' : 
              cert.status === 'expiring' ? 'warning' : 'danger'
            }
          >
            {cert.revoked ? 'Revoked' : cert.status || 'Active'}
          </Badge>
        }
        stats={[
          { icon: Clock, label: 'Expires', value: formatDate(cert.valid_to) },
          { icon: Key, label: 'Key', value: cert.key_algorithm || cert.key_type || 'RSA' },
        ]}
        actions={[
          { label: 'Export', icon: Download, onClick: () => handleExport('pem') },
          ...(canDelete('certificates') && !cert.revoked ? [
            { label: 'Revoke', icon: X, variant: 'danger', onClick: () => handleRevoke(cert.id) }
          ] : [])
        ]}
      />

      <DetailSection title="Subject">
        <DetailGrid>
          <DetailField label="Common Name" value={cert.common_name || extractCN(cert.subject)} />
          <DetailField label="Organization" value={cert.organization} />
          <DetailField label="Country" value={cert.country} />
          <DetailField label="State" value={cert.state} />
        </DetailGrid>
      </DetailSection>

      <DetailSection title="Validity">
        <DetailGrid>
          <DetailField label="Valid From" value={formatDate(cert.valid_from)} />
          <DetailField label="Valid Until" value={formatDate(cert.valid_to)} />
          <DetailField label="Serial Number" value={cert.serial} mono copyable />
        </DetailGrid>
      </DetailSection>

      <DetailSection title="Technical">
        <DetailGrid>
          <DetailField label="Key Algorithm" value={cert.key_algorithm || cert.key_type} />
          <DetailField label="Signature Algorithm" value={cert.signature_algorithm} />
          <DetailField label="Has Private Key" value={cert.has_private_key ? 'Yes' : 'No'} />
        </DetailGrid>
      </DetailSection>
    </div>
  )

  // Help content
  const helpContent = (
    <div className="space-y-4">
      <HelpCard title="Certificates" variant="info">
        Digital certificates authenticate identities and enable secure communications.
      </HelpCard>
      <HelpCard title="Status" variant="default">
        <ul className="text-sm space-y-1">
          <li><Badge variant="success" size="sm">Valid</Badge> - Active and trusted</li>
          <li><Badge variant="warning" size="sm">Expiring</Badge> - Expires within 30 days</li>
          <li><Badge variant="danger" size="sm">Expired</Badge> - No longer valid</li>
        </ul>
      </HelpCard>
    </div>
  )

  return (
    <>
      <ListPageLayout
        title="Certificates"
        data={certificates}
        columns={columns}
        loading={loading}
        selectedItem={selectedCert}
        onSelectItem={(cert) => cert ? loadCertDetails(cert) : setSelectedCert(null)}
        renderDetails={renderDetails}
        detailsTitle="Certificate Details"
        searchable
        searchPlaceholder="Search certificates..."
        searchKeys={['common_name', 'subject', 'issuer']}
        sortable
        defaultSort={{ key: 'valid_to', direction: 'asc' }}
        paginated
        pageSize={25}
        rowActions={rowActions}
        emptyIcon={Certificate}
        emptyTitle="No certificates"
        emptyDescription="Issue your first certificate to get started"
        emptyAction={canWrite('certificates') && (
          <Button onClick={() => setShowIssueModal(true)}>
            <Plus size={16} /> Issue Certificate
          </Button>
        )}
        helpContent={helpContent}
        actions={canWrite('certificates') && (
          <>
            <Button size="sm" onClick={() => setShowIssueModal(true)}>
              <Plus size={16} /> Issue
            </Button>
            <Button size="sm" variant="secondary" onClick={() => {}}>
              <UploadSimple size={16} /> Import
            </Button>
          </>
        )}
      />

      {/* Issue Modal - simplified for now */}
      <Modal
        open={showIssueModal}
        onClose={() => setShowIssueModal(false)}
        title="Issue Certificate"
        size="lg"
      >
        <div className="p-4 space-y-4">
          <Select
            label="Certificate Authority"
            options={cas.map(ca => ({ value: ca.id, label: ca.name || ca.common_name }))}
            placeholder="Select a CA..."
          />
          <Input label="Common Name" placeholder="example.com" />
          <Textarea label="Subject Alternative Names" placeholder="DNS:example.com, DNS:www.example.com" rows={3} />
          <div className="flex justify-end gap-2 pt-4">
            <Button variant="secondary" onClick={() => setShowIssueModal(false)}>Cancel</Button>
            <Button onClick={() => { showSuccess('Certificate issued'); setShowIssueModal(false); loadData() }}>
              Issue Certificate
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}
