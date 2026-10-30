/**
 * UserCertificatesPage - Manage user/client certificates (mTLS)
 * 
 * Follows CertificatesPage patterns: stats bar, floating windows, rowActions, server-side pagination.
 * RBAC: viewers see own, operators/admins manage all, auditors read-only
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import {
  UserCircle, Download, Trash, XCircle,
  CheckCircle, Warning, Clock, Certificate, Info
} from '@phosphor-icons/react'
import {
  ResponsiveLayout, ResponsiveDataTable, Badge, Button
} from '../components'
import { userCertificatesService } from '../services'
import { RevokeCertificateModal } from '../components/RevokeCertificateModal'
import { ExportModal } from '../components/ExportModal'
import { useNotification, useMobile } from '../contexts'
import { useWindowManager } from '../contexts/WindowManagerContext'
import { usePermission, usePersistedState } from '../hooks'
import { formatDate, extractCN } from '../lib/utils'
import { canExportPrivateKey } from '../lib/exportPermissions'
import { downloadExport } from '../lib/exportDownload'
import { isExportFormatAllowed } from '../lib/keyAlgorithms'

export default function UserCertificatesPage() {
  const { t } = useTranslation()
  const { isMobile } = useMobile()
  const { showSuccess, showError, showConfirm, showWarning } = useNotification()
  const { openWindow } = useWindowManager()
  const { canWrite, canDelete, hasPermission } = usePermission()

  // Data
  const [certificates, setCertificates] = useState([])
  const [loading, setLoading] = useState(true)
  const [certStats, setCertStats] = useState({ total: 0, valid: 0, expiring: 0, expired: 0, revoked: 0 })

  // Selected (mobile slide-over only)
  const [selectedCert, setSelectedCert] = useState(null)

  // Pagination
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  const [total, setTotal] = useState(0)

  // Filters
  const [filterStatus, setFilterStatus] = usePersistedState('ucm-filter-usercerts-status', [])
  const [searchValue, setSearchValue] = useState('')

  // Export — ExportModal owns the format, password and PKCS#12 profile (#331);
  // exportFormat only says which tile it opens on.
  const [exportCert, setExportCert] = useState(null)
  const [exportFormat, setExportFormat] = useState('pem')

  // Load data
  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const params = { page, per_page: perPage }
      if (filterStatus.length > 0) params.status = filterStatus
      if (searchValue) params.search = searchValue

      const [certRes, statsRes] = await Promise.all([
        userCertificatesService.getAll(params),
        userCertificatesService.getStats(),
      ])

      setCertificates(certRes.data?.items || [])
      setTotal(certRes.data?.total || 0)
      setCertStats(statsRes.data || { total: 0, valid: 0, expiring: 0, expired: 0, revoked: 0 })
    } catch (error) {
      showError(error.message || t('messages.errors.loadFailed.certificates'))
    } finally {
      setLoading(false)
    }
  }, [page, perPage, JSON.stringify(filterStatus), searchValue, showError, t])

  useEffect(() => { loadData() }, [loadData])

  // Listen for data change events (from floating windows)
  useEffect(() => {
    const handler = (e) => {
      if (e.detail?.type === 'user_certificate') loadData()
    }
    window.addEventListener('ucm:data-changed', handler)
    return () => window.removeEventListener('ucm:data-changed', handler)
  }, [loadData])

  // Stats bar — follows exact ResponsiveLayout format: { icon, label, value, variant, filterValue }
  const stats = useMemo(() => [
    { icon: CheckCircle, label: t('common.valid'), value: certStats.valid, variant: 'success', filterValue: 'valid' },
    { icon: Warning, label: t('common.expiring'), value: certStats.expiring, variant: 'warning', filterValue: 'expiring' },
    { icon: Clock, label: t('common.expired'), value: certStats.expired, variant: 'danger', filterValue: 'expired' },
    { icon: XCircle, label: t('common.revoked'), value: certStats.revoked, variant: 'danger', filterValue: 'revoked' },
    { icon: Certificate, label: t('common.total'), value: certStats.total, variant: 'primary', filterValue: '' },
  ], [certStats, t])

  // Stat click → filter
  const handleStatClick = useCallback((filterValue) => {
    setPage(1)
    if (filterValue === '') {
      setFilterStatus([])
    } else {
      setFilterStatus(prev => {
        if (prev.includes(filterValue)) {
          return prev.filter(v => v !== filterValue)
        }
        return [...prev, filterValue]
      })
    }
  }, [])

  // Row click → open floating window (desktop) or slide-over (mobile)
  const handleSelectCert = useCallback(async (row) => {
    if (!row) { setSelectedCert(null); return }

    if (!isMobile) {
      openWindow('user_certificate', row.id)
      return
    }

    // Mobile: fetch full detail for slide-over
    try {
      const res = await userCertificatesService.getById(row.id)
      setSelectedCert(res.data || row)
    } catch {
      setSelectedCert(row)
    }
  }, [isMobile, openWindow])

  // Status badge helper
  const getStatusBadge = useCallback((row) => {
    const config = {
      valid: { variant: 'success', icon: CheckCircle, label: t('common.valid'), pulse: true },
      expiring: { variant: 'warning', icon: Warning, label: t('common.expiring'), pulse: true },
      expired: { variant: 'danger', icon: Clock, label: t('common.expired') },
      revoked: { variant: 'danger', icon: XCircle, label: t('common.revoked') },
      // Same neutral fallback as the certificates table (useCertificateColumns):
      // a status we do not know must not be announced as valid
      unknown: { variant: 'secondary', icon: Info, label: t('common.status') },
    }
    const c = config[row.status] || config.unknown
    return <Badge variant={c.variant} size="sm" icon={c.icon} dot pulse={c.pulse}>{c.label}</Badge>
  }, [t])

  // Export handler — options come from ExportModal, so include_key is whatever
  // the operator ticked rather than the service default (which is true).
  const handleExport = async (format, options = {}) => {
    if (!exportCert) return
    try {
      await downloadExport(
        userCertificatesService.export(exportCert.id, format, options),
        { format, name: exportCert.name || 'certificate' },
      )
      showSuccess(t('userCertificates.exportSuccess'))
    } catch (error) {
      showError(error.message || t('userCertificates.exportFailed'))
      throw error
    }
  }

  // Revoke handler
  // Revocation asks for the RFC 5280 reason (#334)
  const [revokingCert, setRevokingCert] = useState(null)
  const [revoking, setRevoking] = useState(false)
  const handleRevoke = useCallback((id) => {
    const cert = certificates.find(c => c.id === id)
    setRevokingCert(cert ? { ...cert, name: cert.name || cert.cert_subject } : { id })
  }, [certificates])
  const handleRevokeConfirm = async (reason) => {
    if (!revokingCert) return
    setRevoking(true)
    try {
      const res = await userCertificatesService.revoke(revokingCert.id, reason)
      if (res?.data?.approval_required) {
        showWarning(t('certificates.revocationApprovalRequired', { policy: res.data.policy_name }))
      } else {
        showSuccess(t('userCertificates.revokeSuccess'))
      }
      setRevokingCert(null)
      setSelectedCert(null)
      loadData()
    } catch (error) {
      showError(error.message || t('userCertificates.revokeFailed'))
    } finally {
      setRevoking(false)
    }
  }

  // Delete handler
  const handleDelete = useCallback(async (id) => {
    const cert = certificates.find(c => c.id === id)
    const name = cert?.name || cert?.cert_subject || id
    const confirmed = await showConfirm(
      t('userCertificates.deleteDescription', { name }),
      { title: t('userCertificates.deleteTitle'), variant: 'danger', confirmText: t('common.delete') }
    )
    if (!confirmed) return
    try {
      await userCertificatesService.delete(id)
      showSuccess(t('userCertificates.deleteSuccess'))
      setSelectedCert(null)
      loadData()
    } catch (error) {
      showError(error.message || t('userCertificates.deleteFailed'))
    }
  }, [certificates, showConfirm, showSuccess, showError, loadData, t])

  // Table columns — follows ResponsiveDataTable pattern: { key, header, priority, sortable, render(val, row) }
  const columns = useMemo(() => [
    {
      key: 'name',
      header: t('userCertificates.columns.name'),
      priority: 1,
      sortable: true,
      render: (_val, row) => (
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg flex items-center justify-center shrink-0 icon-bg-blue">
            <Certificate size={14} weight="duotone" />
          </div>
          <div className="min-w-0">
            <span className="font-medium truncate block">{row.name || extractCN(row.cert_subject) || '-'}</span>
            <span className="text-2xs text-text-tertiary truncate block">{row.cert_subject}</span>
          </div>
        </div>
      ),
      mobileRender: (_val, row) => (
        <div className="flex items-center justify-between gap-2 w-full">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <Certificate size={14} weight="duotone" />
            <span className="font-medium truncate">{row.name || extractCN(row.cert_subject) || '-'}</span>
          </div>
          <div className="shrink-0">{getStatusBadge(row)}</div>
        </div>
      ),
    },
    {
      key: 'owner',
      header: t('userCertificates.columns.owner'),
      priority: 3,
      hideOnMobile: true,
      render: (_val, row) => (
        <div className="flex items-center gap-1.5">
          <UserCircle size={14} className="text-text-tertiary" />
          <span>{row.owner || '-'}</span>
        </div>
      ),
    },
    {
      key: 'status',
      header: t('common.status'),
      priority: 2,
      hideOnMobile: true,
      render: (_val, row) => getStatusBadge(row),
    },
    {
      key: 'valid_to',
      header: t('common.expires'),
      priority: 4,
      sortable: true,
      mono: true,
      render: (val, row) => (
        <span className="text-xs text-text-secondary whitespace-nowrap">
          {formatDate(val || row.valid_until)}
        </span>
      ),
      mobileRender: (val, row) => (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-text-tertiary">{t('common.expires')}:</span>
          <span className="text-text-secondary font-mono">{formatDate(val || row.valid_until)}</span>
        </div>
      ),
    },
  ], [t, getStatusBadge])

  // Row actions — 3-dot menu per row (follows CertificatesPage pattern)
  const rowActions = useCallback((row) => [
    {
      label: t('common.details'),
      icon: Info,
      onClick: () => handleSelectCert(row),
    },
    {
      label: t('common.export'),
      icon: Download,
      onClick: () => { setExportFormat('pem'); setExportCert(row) },
    },
    ...(canWrite('user_certificates') && row.status !== 'revoked' ? [{
      label: t('userCertificates.actions.revoke'),
      icon: XCircle,
      variant: 'danger',
      onClick: () => handleRevoke(row.id),
    }] : []),
    ...(canDelete('user_certificates') ? [{
      label: t('common.delete'),
      icon: Trash,
      variant: 'danger',
      onClick: () => handleDelete(row.id),
    }] : []),
  ], [t, canWrite, canDelete, handleSelectCert, handleRevoke, handleDelete])

  // Filter presets callback
  const handleApplyFilterPreset = useCallback((filters) => {
    setPage(1)
    setFilterStatus(filters.status ? (Array.isArray(filters.status) ? filters.status : [filters.status]) : [])
  }, [])

  // Mobile slide-over content
  const slideOverContent = selectedCert ? (
    <div className="p-4 space-y-4">
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

      <div className="flex flex-wrap gap-2 pt-3 border-t border-border">
        <Button type="button" size="sm" onClick={() => { setExportFormat('pem'); setExportCert(selectedCert) }}>
          <Download size={14} /> {t('userCertificates.actions.exportPEM')}
        </Button>
        {selectedCert.has_private_key && isExportFormatAllowed(selectedCert.key_algorithm, 'pkcs12') && (
          <Button type="button" size="sm" variant="secondary" onClick={() => { setExportFormat('pkcs12'); setExportCert(selectedCert) }}>
            <Certificate size={14} /> {t('userCertificates.actions.exportPKCS12')}
          </Button>
        )}
        {canWrite('user_certificates') && selectedCert.status !== 'revoked' && (
          <Button type="button" size="sm" variant="danger" onClick={() => handleRevoke(selectedCert.id)}>
            <XCircle size={14} /> {t('userCertificates.actions.revoke')}
          </Button>
        )}
      </div>
    </div>
  ) : null

  return (
    <ResponsiveLayout
      icon={UserCircle}
      title={t('userCertificates.title')}
      subtitle={t('userCertificates.description')}
      stats={stats}
      onStatClick={handleStatClick}
      activeStatFilter={filterStatus}
      helpPageKey="user-certificates"
      splitView={isMobile}
      splitEmptyContent={isMobile ? (
        <div className="h-full flex flex-col items-center justify-center p-6 text-center">
          <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
            <Certificate size={24} className="text-text-tertiary" />
          </div>
          <p className="text-sm text-text-secondary">{t('userCertificates.empty.description')}</p>
        </div>
      ) : undefined}
      slideOverOpen={isMobile && !!selectedCert}
      slideOverTitle={selectedCert?.name || extractCN(selectedCert?.cert_subject) || t('userCertificates.title')}
      slideOverContent={isMobile ? slideOverContent : null}
      slideOverWidth="wide"
      onSlideOverClose={() => setSelectedCert(null)}
    >
      <ResponsiveDataTable
        data={certificates}
        columns={columns}
        loading={loading}
        onRowClick={handleSelectCert}
        selectedId={selectedCert?.id}
        rowActions={rowActions}
        searchable
        searchPlaceholder={t('userCertificates.searchPlaceholder')}
        externalSearch={searchValue}
        onSearchChange={(v) => { setSearchValue(v); setPage(1) }}
        columnStorageKey="ucm-user-certs-columns"
        filterPresetsKey="ucm-user-certs-presets"
        densityStorageKey="ucm-user-certs-density"
        onApplyFilterPreset={handleApplyFilterPreset}
        toolbarFilters={[{
          key: 'status',
          label: t('common.status'),
          type: 'multiSelect',
          value: filterStatus,
          onChange: (v) => { setFilterStatus(v); setPage(1) },
          placeholder: t('common.allStatus'),
          options: [
            { value: 'valid', label: t('common.valid') },
            { value: 'expiring', label: t('common.expiring') },
            { value: 'expired', label: t('common.expired') },
            { value: 'revoked', label: t('common.revoked') },
          ],
        }]}
        exportEnabled
        exportFilename="user-certificates"
        pagination={{
          page,
          total,
          perPage,
          onChange: setPage,
          onPerPageChange: (v) => { setPerPage(v); setPage(1) },
        }}
        emptyIcon={Certificate}
        emptyTitle={t('userCertificates.empty.title')}
        emptyDescription={t('userCertificates.empty.description')}
      />

      {/* Export — the dialog every other certificate surface uses */}
      <ExportModal
        open={!!exportCert}
        onClose={() => setExportCert(null)}
        entityType="certificate"
        entityName={exportCert?.name || exportCert?.cert_subject || ''}
        hasPrivateKey={!!exportCert?.has_private_key}
        canExportKey={canExportPrivateKey('user_certificate', { hasPermission, canWrite })}
        keyAlgorithm={exportCert?.key_algorithm}
        defaultFormat={exportFormat}
        onExport={handleExport}
      />
      <RevokeCertificateModal
        open={!!revokingCert}
        onClose={() => setRevokingCert(null)}
        onConfirm={handleRevokeConfirm}
        certificate={revokingCert}
        loading={revoking}
      />
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
