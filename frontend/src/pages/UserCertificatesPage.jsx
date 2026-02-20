/**
 * UserCertificatesPage - Manage user/client certificates (mTLS)
 * 
 * RBAC: viewers see own, operators/admins manage all, auditors read-only
 */
import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import {
  UserCircle, Download, Trash, ShieldCheck, XCircle,
  CheckCircle, Warning, Clock, Certificate
} from '@phosphor-icons/react'
import {
  ResponsiveLayout, ResponsiveDataTable, Badge, Button, Modal, Input
} from '../components'
import { userCertificatesService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { formatDate, extractCN } from '../lib/utils'

export default function UserCertificatesPage() {
  const { t } = useTranslation()
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canWrite, canDelete } = usePermission()

  // Data
  const [certificates, setCertificates] = useState([])
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState({ total: 0, valid: 0, expiring: 0, expired: 0, revoked: 0 })

  // Selected
  const [selectedCert, setSelectedCert] = useState(null)

  // Pagination
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  const [total, setTotal] = useState(0)

  // Sorting
  const [sortBy, setSortBy] = useState('created_at')
  const [sortOrder, setSortOrder] = useState('desc')

  // Filters
  const [filterStatus, setFilterStatus] = useState('')
  const [search, setSearch] = useState('')

  // Modals
  const [showExportModal, setShowExportModal] = useState(false)
  const [exportCert, setExportCert] = useState(null)
  const [exportFormat, setExportFormat] = useState('pem')
  const [exportPassword, setExportPassword] = useState('')
  const [exporting, setExporting] = useState(false)

  const handleApplyFilterPreset = useCallback((filters) => {
    setPage(1)
    if (filters.status) setFilterStatus(filters.status)
    else setFilterStatus('')
  }, [])

  // Load data
  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const params = {
        page,
        per_page: perPage,
        sort_by: sortBy,
        sort_order: sortOrder,
      }
      if (filterStatus) params.status = filterStatus
      if (search) params.search = search

      const [certRes, statsRes] = await Promise.all([
        userCertificatesService.getAll(params),
        userCertificatesService.getStats(),
      ])

      setCertificates(certRes.data?.items || [])
      setTotal(certRes.data?.total || 0)
      setStats(statsRes.data || { total: 0, valid: 0, expiring: 0, expired: 0, revoked: 0 })
    } catch (error) {
      showError(error.message || t('messages.errors.loadFailed.certificates'))
    } finally {
      setLoading(false)
    }
  }, [page, perPage, filterStatus, search, sortBy, sortOrder, showError, t])

  useEffect(() => { loadData() }, [loadData])

  // Status badge
  const statusBadge = (status) => {
    const config = {
      valid: { variant: 'success', icon: CheckCircle, label: t('certificates.statuses.valid') },
      expiring: { variant: 'warning', icon: Warning, label: t('certificates.statuses.expiring') },
      expired: { variant: 'danger', icon: Clock, label: t('certificates.statuses.expired') },
      revoked: { variant: 'danger', icon: XCircle, label: t('certificates.statuses.revoked') },
      orphan: { variant: 'default', icon: Warning, label: 'Orphan' },
    }
    const c = config[status] || config.valid
    const Icon = c.icon
    return <Badge variant={c.variant}><Icon size={12} weight="bold" /> {c.label}</Badge>
  }

  // Export handler
  const handleExport = async () => {
    if (!exportCert) return
    if (exportFormat === 'pkcs12' && exportPassword.length < 8) {
      showError(t('userCertificates.exportPasswordMin'))
      return
    }
    setExporting(true)
    try {
      const response = await userCertificatesService.exportCert(
        exportCert.id,
        exportFormat,
        { password: exportFormat === 'pkcs12' ? exportPassword : undefined }
      )
      // Download the blob
      const blob = response instanceof Blob ? response : new Blob([response.data || response])
      const ext = exportFormat === 'pkcs12' ? 'p12' : 'pem'
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${exportCert.name || 'certificate'}.${ext}`
      a.click()
      URL.revokeObjectURL(url)
      showSuccess(t('userCertificates.exportSuccess'))
      setShowExportModal(false)
      setExportPassword('')
    } catch (error) {
      showError(error.message || t('userCertificates.exportFailed'))
    } finally {
      setExporting(false)
    }
  }

  // Revoke handler
  const handleRevoke = async (cert) => {
    const confirmed = await showConfirm(
      t('userCertificates.revokeDescription', { name: cert.name || cert.subject_cn || cert.id }),
      { title: t('userCertificates.revokeTitle'), variant: 'danger', confirmText: t('userCertificates.actions.revoke') }
    )
    if (!confirmed) return
    try {
      await userCertificatesService.revoke(cert.id)
      showSuccess(t('userCertificates.revokeSuccess'))
      loadData()
    } catch (error) {
      showError(error.message || t('userCertificates.revokeFailed'))
    }
  }

  // Delete handler
  const handleDelete = async (cert) => {
    const confirmed = await showConfirm(
      t('userCertificates.deleteDescription', { name: cert.name || cert.subject_cn || cert.id }),
      { title: t('userCertificates.deleteTitle'), variant: 'danger', confirmText: t('common.delete') }
    )
    if (!confirmed) return
    try {
      await userCertificatesService.delete(cert.id)
      showSuccess(t('userCertificates.deleteSuccess'))
      if (selectedCert?.id === cert.id) setSelectedCert(null)
      loadData()
    } catch (error) {
      showError(error.message || t('userCertificates.deleteFailed'))
    }
  }

  // Stats cards
  const statsCards = [
    { label: t('userCertificates.stats.valid'), value: stats.valid, color: 'success', filter: 'valid' },
    { label: t('userCertificates.stats.expiring'), value: stats.expiring, color: 'warning', filter: 'expiring' },
    { label: t('userCertificates.stats.expired'), value: stats.expired, color: 'danger', filter: 'expired' },
    { label: t('userCertificates.stats.revoked'), value: stats.revoked, color: 'danger', filter: 'revoked' },
  ]

  // Table columns
  const columns = [
    {
      key: 'name',
      label: t('userCertificates.columns.name'),
      sortable: true,
      render: (_value, row) => (
        <div className="flex items-center gap-2">
          <ShieldCheck size={16} className="text-accent-primary shrink-0" />
          <div className="min-w-0">
            <div className="font-medium text-text-primary truncate">{row.name || extractCN(row.cert_subject) || '-'}</div>
            <div className="text-2xs text-text-tertiary truncate">{row.cert_subject}</div>
          </div>
        </div>
      ),
    },
    {
      key: 'owner',
      label: t('userCertificates.columns.owner'),
      render: (_value, row) => (
        <div className="flex items-center gap-1.5">
          <UserCircle size={14} className="text-text-tertiary" />
          <span>{row.owner || '-'}</span>
        </div>
      ),
    },
    {
      key: 'status',
      label: t('userCertificates.columns.status'),
      render: (value) => statusBadge(value),
    },
    {
      key: 'valid_to',
      label: t('userCertificates.columns.expires'),
      sortable: true,
      render: (_value, row) => <span className="text-text-secondary text-xs">{formatDate(row.valid_to || row.valid_until)}</span>,
    },
    {
      key: 'last_used_at',
      label: t('userCertificates.columns.lastUsed'),
      render: (value) => (
        <span className="text-text-tertiary text-xs">
          {value ? formatDate(value) : t('common.never')}
        </span>
      ),
    },
    {
      key: 'actions',
      label: '',
      width: 'auto',
      render: (_value, row) => (
        <div className="flex items-center gap-1">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            title={t('userCertificates.actions.export')}
            onClick={(e) => { e.stopPropagation(); setExportCert(row); setExportFormat('pem'); setShowExportModal(true) }}
          >
            <Download size={14} />
          </Button>
          {canWrite('user_certificates') && row.status !== 'revoked' && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              title={t('userCertificates.actions.revoke')}
              onClick={(e) => { e.stopPropagation(); handleRevoke(row) }}
            >
              <XCircle size={14} className="text-accent-danger" />
            </Button>
          )}
          {canDelete('user_certificates') && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              title={t('userCertificates.actions.delete')}
              onClick={(e) => { e.stopPropagation(); handleDelete(row) }}
            >
              <Trash size={14} className="text-accent-danger" />
            </Button>
          )}
        </div>
      ),
    },
  ]

  // Detail panel
  const detailContent = selectedCert ? (
    <div className="p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-text-primary">
          {selectedCert.name || extractCN(selectedCert.cert_subject)}
        </h3>
        {statusBadge(selectedCert.status)}
      </div>

      <div className="space-y-3">
        <DetailField label={t('userCertificates.detail.owner')} value={selectedCert.owner} />
        <DetailField label={t('userCertificates.detail.subject')} value={selectedCert.cert_subject} mono />
        <DetailField label={t('userCertificates.detail.issuer')} value={selectedCert.cert_issuer || selectedCert.issuer} mono />
        <DetailField label={t('userCertificates.detail.serial')} value={selectedCert.serial_number || selectedCert.cert_serial} mono />
        <DetailField label={t('userCertificates.detail.fingerprint')} value={selectedCert.cert_fingerprint} mono />
        <DetailField label={t('userCertificates.detail.validFrom')} value={formatDate(selectedCert.valid_from)} />
        <DetailField label={t('userCertificates.detail.validTo')} value={formatDate(selectedCert.valid_to || selectedCert.valid_until)} />
        <DetailField label={t('userCertificates.detail.lastUsed')} value={selectedCert.last_used_at ? formatDate(selectedCert.last_used_at) : t('common.never')} />
        <DetailField label={t('userCertificates.detail.created')} value={formatDate(selectedCert.created_at)} />
        <DetailField label={t('userCertificates.detail.privateKey')} value={selectedCert.has_private_key ? t('common.yes') : t('common.no')} />
      </div>

      <div className="flex gap-2 pt-3 border-t border-border">
        <Button
          type="button"
          size="sm"
          onClick={() => { setExportCert(selectedCert); setExportFormat('pem'); setShowExportModal(true) }}
        >
          <Download size={14} /> {t('userCertificates.actions.exportPEM')}
        </Button>
        {selectedCert.has_private_key && (
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={() => { setExportCert(selectedCert); setExportFormat('pkcs12'); setShowExportModal(true) }}
          >
            <Certificate size={14} /> {t('userCertificates.actions.exportPKCS12')}
          </Button>
        )}
      </div>
    </div>
  ) : null

  return (
    <ResponsiveLayout
      icon={ShieldCheck}
      title={t('userCertificates.title')}
      description={t('userCertificates.description')}
      stats={statsCards}
      onStatClick={(stat) => handleApplyFilterPreset({ status: stat.filter === filterStatus ? '' : stat.filter })}
      activeStatFilter={filterStatus}
      detailContent={detailContent}
      detailOpen={!!selectedCert}
      onDetailClose={() => setSelectedCert(null)}
    >
      <ResponsiveDataTable
        data={certificates}
        columns={columns}
        loading={loading}
        selectedRow={selectedCert}
        onRowClick={setSelectedCert}
        searchValue={search}
        onSearchChange={(v) => { setSearch(v); setPage(1) }}
        searchPlaceholder={t('userCertificates.searchPlaceholder')}
        page={page}
        perPage={perPage}
        total={total}
        onPageChange={setPage}
        onPerPageChange={(v) => { setPerPage(v); setPage(1) }}
        sortBy={sortBy}
        sortOrder={sortOrder}
        onSort={(col, order) => { setSortBy(col); setSortOrder(order) }}
        emptyIcon={ShieldCheck}
        emptyTitle={t('userCertificates.empty.title')}
        emptyDescription={t('userCertificates.empty.description')}
      />

      {/* Export Modal */}
      <Modal
        open={showExportModal}
        onClose={() => { setShowExportModal(false); setExportPassword('') }}
        title={t('userCertificates.exportTitle')}
        size="sm"
      >
        <div className="p-4 space-y-4">
          <p className="text-sm text-text-secondary">
            {t('userCertificates.exportDescription', { name: exportCert?.name || '' })}
          </p>

          <div className="flex gap-2">
            <Button
              type="button"
              variant={exportFormat === 'pem' ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => setExportFormat('pem')}
            >
              PEM
            </Button>
            {exportCert?.has_private_key && (
              <Button
                type="button"
                variant={exportFormat === 'pkcs12' ? 'primary' : 'secondary'}
                size="sm"
                onClick={() => setExportFormat('pkcs12')}
              >
                PKCS12 (.p12)
              </Button>
            )}
          </div>

          {exportFormat === 'pkcs12' && (
            <Input
              type="password"
              label={t('userCertificates.exportPasswordLabel')}
              placeholder={t('userCertificates.exportPasswordPlaceholder')}
              value={exportPassword}
              onChange={(e) => setExportPassword(e.target.value)}
              helperText={t('userCertificates.exportPasswordMin')}
            />
          )}

          <div className="flex justify-end gap-2 pt-2 border-t border-border">
            <Button type="button" variant="secondary" onClick={() => { setShowExportModal(false); setExportPassword('') }}>
              {t('common.cancel')}
            </Button>
            <Button type="button" onClick={handleExport} loading={exporting} disabled={exporting}>
              <Download size={14} /> {t('common.export')}
            </Button>
          </div>
        </div>
      </Modal>
    </ResponsiveLayout>
  )
}

function DetailField({ label, value, mono }) {
  return (
    <div>
      <dt className="text-xs text-text-tertiary">{label}</dt>
      <dd className={`text-sm text-text-primary ${mono ? 'font-mono text-xs break-all' : ''}`}>
        {value || '-'}
      </dd>
    </div>
  )
}
