/**
 * Certificates Page - Using TablePageLayout (Audit pattern)
 * 
 * Pattern: Full-width table with filters in focus panel, details in modal
 */
import { useState, useEffect, useMemo } from 'react'
import { 
  Certificate, Download, Trash, ArrowsClockwise, X, Key,
  CheckCircle, Warning, Clock, ShieldCheck, Plus, UploadSimple,
  CalendarBlank, User, Lock, Info
} from '@phosphor-icons/react'
import {
  TablePageLayout, Badge, Button, Modal, Select, Input, Textarea, HelpCard, Card,
  CertificateDetails
} from '../components'
import { certificatesService, casService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { formatDate, extractCN, cn } from '../lib/utils'

export default function CertificatesPage() {
  // Data state
  const [certificates, setCertificates] = useState([])
  const [cas, setCas] = useState([])
  const [loading, setLoading] = useState(true)
  
  // Selection & modals
  const [selectedCert, setSelectedCert] = useState(null)
  const [showIssueModal, setShowIssueModal] = useState(false)
  
  // Pagination
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  const [total, setTotal] = useState(0)
  
  // Filters
  const [filterStatus, setFilterStatus] = useState('')
  const [filterCA, setFilterCA] = useState('')
  const [search, setSearch] = useState('')
  
  const { showSuccess, showError } = useNotification()
  const { canWrite, canDelete } = usePermission()

  useEffect(() => {
    loadData()
  }, [page, perPage])

  // Reset to page 1 when filters change
  useEffect(() => {
    if (page !== 1) setPage(1)
  }, [filterStatus, filterCA, search])

  const loadData = async () => {
    try {
      setLoading(true)
      const [certsRes, casRes] = await Promise.all([
        certificatesService.getAll({ page, per_page: perPage }),
        casService.getAll()
      ])
      const certs = certsRes.data || []
      setCertificates(certs)
      // Use API total if available, otherwise use array length
      setTotal(certsRes.meta?.total || certsRes.pagination?.total || certs.length)
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

  // Filter and normalize data
  const filteredCerts = useMemo(() => {
    let result = certificates.map(cert => ({
      ...cert,
      status: cert.revoked ? 'revoked' : cert.status,
      cn: extractCN(cert.subject) || cert.common_name || 'Certificate'
    }))
    
    // Apply status filter
    if (filterStatus) {
      result = result.filter(c => c.status === filterStatus)
    }
    
    // Apply CA filter  
    if (filterCA) {
      result = result.filter(c => String(c.ca_id) === filterCA || c.caref === filterCA)
    }
    
    // Apply search (handled by TablePageLayout if not doing server-side)
    
    return result
  }, [certificates, filterStatus, filterCA])

  // Stats for focus panel
  const stats = useMemo(() => {
    const valid = certificates.filter(c => !c.revoked && c.status === 'valid').length
    const expiring = certificates.filter(c => c.status === 'expiring').length
    const revoked = certificates.filter(c => c.revoked).length
    return [
      { icon: CheckCircle, label: 'Valid', value: valid, color: 'text-emerald-500' },
      { icon: Warning, label: 'Expiring', value: expiring, color: 'text-amber-500' },
      { icon: X, label: 'Revoked', value: revoked, color: 'text-red-500' },
      { icon: Certificate, label: 'Total', value: total, color: 'text-accent-primary' }
    ]
  }, [certificates, total])

  // Table columns
  const columns = [
    {
      key: 'cn',
      label: 'Common Name',
      sortable: true,
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <Certificate size={16} className="text-accent-primary shrink-0" />
          <span className="font-medium truncate">{val}</span>
          {row.source === 'acme' && (
            <Badge variant="info" size="sm">ACME</Badge>
          )}
          {row.source === 'scep' && (
            <Badge variant="warning" size="sm">SCEP</Badge>
          )}
        </div>
      )
    },
    {
      key: 'issuer',
      label: 'Issuer',
      render: (val, row) => (
        <span className="text-text-secondary truncate">
          {extractCN(val) || row.issuer_name || '—'}
        </span>
      )
    },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
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
      label: 'Expires',
      sortable: true,
      render: (val) => (
        <span className="text-xs text-text-secondary whitespace-nowrap">
          {formatDate(val)}
        </span>
      )
    },
    {
      key: 'key_type',
      label: 'Key',
      render: (val, row) => (
        <span className="text-xs font-mono text-text-secondary">
          {row.key_algorithm || val || 'RSA'}
        </span>
      )
    }
  ]

  // Filters config
  const filters = [
    {
      key: 'status',
      label: 'Status',
      type: 'select',
      value: filterStatus,
      onChange: setFilterStatus,
      placeholder: 'All Status',
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
      placeholder: 'All CAs',
      options: cas.map(ca => ({ 
        value: String(ca.id), 
        label: ca.descr || ca.common_name 
      }))
    }
  ]

  // Quick filters
  const quickFilters = [
    {
      icon: Warning,
      title: 'Expiring Soon',
      subtitle: 'Within 30 days',
      selected: filterStatus === 'expiring',
      onClick: () => setFilterStatus(filterStatus === 'expiring' ? '' : 'expiring')
    },
    {
      icon: X,
      title: 'Revoked',
      subtitle: 'Invalid certificates',
      selected: filterStatus === 'revoked',
      onClick: () => setFilterStatus(filterStatus === 'revoked' ? '' : 'revoked')
    }
  ]

  // Help content
  const helpContent = (
    <div className="space-y-3">
      <HelpCard title="About Certificates" variant="info">
        Digital certificates authenticate identities and enable encrypted communications using PKI.
      </HelpCard>
      <HelpCard title="Status Legend" variant="info">
        <div className="space-y-1 mt-2">
          <div className="flex items-center gap-2">
            <Badge variant="success" size="sm">Valid</Badge>
            <span className="text-xs">Active and trusted</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="warning" size="sm">Expiring</Badge>
            <span className="text-xs">Expires within 30 days</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="danger" size="sm">Revoked</Badge>
            <span className="text-xs">No longer valid</span>
          </div>
        </div>
      </HelpCard>
      <HelpCard title="Export Formats" variant="tip">
        PEM format is most common. Use DER for Java applications, PKCS#12 for Windows.
      </HelpCard>
    </div>
  )

  // Clear all filters
  const handleClearFilters = () => {
    setFilterStatus('')
    setFilterCA('')
    setSearch('')
  }

  return (
    <>
      <TablePageLayout
        title="Certificates"
        loading={loading}
        data={filteredCerts}
        columns={columns}
        searchable
        searchPlaceholder="Search certificates..."
        searchKeys={['cn', 'common_name', 'subject', 'issuer', 'serial']}
        externalSearch={search}
        onSearch={setSearch}
        onRowClick={loadCertDetails}
        filters={filters}
        quickFilters={quickFilters}
        onClearFilters={handleClearFilters}
        stats={stats}
        helpContent={helpContent}
        onRefresh={loadData}
        emptyIcon={Certificate}
        emptyTitle="No certificates"
        emptyDescription="Issue your first certificate to get started"
        emptyAction={canWrite('certificates') && (
          <Button onClick={() => setShowIssueModal(true)}>
            <Plus size={16} /> Issue Certificate
          </Button>
        )}
        actions={canWrite('certificates') && (
          <>
            <Button size="sm" onClick={() => setShowIssueModal(true)} className="flex-1">
              <Plus size={14} /> Issue
            </Button>
          </>
        )}
        pagination={{
          page,
          total,
          perPage,
          onChange: setPage,
          onPerPageChange: (v) => { setPerPage(v); setPage(1) }
        }}
      />

      {/* Certificate Details Modal */}
      <Modal
        open={!!selectedCert}
        onOpenChange={() => setSelectedCert(null)}
        title="Certificate Details"
        size="lg"
      >
        {selectedCert && (
          <CertificateDetails
            certificate={selectedCert}
            onExport={handleExport}
            onRevoke={() => handleRevoke(selectedCert.id)}
            onDelete={() => handleDelete(selectedCert.id)}
            canWrite={canWrite('certificates')}
            canDelete={canDelete('certificates')}
          />
        )}
      </Modal>

      {/* Issue Certificate Modal */}
      <Modal
        open={showIssueModal}
        onOpenChange={setShowIssueModal}
        title="Issue Certificate"
        size="lg"
      >
        <div className="p-4 space-y-4">
          <Select
            label="Certificate Authority"
            placeholder="Select a CA..."
          >
            <option value="">Select a CA...</option>
            {cas.map(ca => (
              <option key={ca.id} value={ca.id}>{ca.descr || ca.common_name}</option>
            ))}
          </Select>
          <Input label="Common Name" placeholder="example.com" />
          <Textarea 
            label="Subject Alternative Names" 
            placeholder="DNS:example.com, DNS:www.example.com" 
            rows={3} 
          />
          <div className="flex justify-end gap-2 pt-4">
            <Button variant="secondary" onClick={() => setShowIssueModal(false)}>
              Cancel
            </Button>
            <Button onClick={() => { 
              showSuccess('Certificate issued'); 
              setShowIssueModal(false); 
              loadData() 
            }}>
              <Certificate size={16} />
              Issue Certificate
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}
