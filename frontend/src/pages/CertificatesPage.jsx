/**
 * CertificatesPage - FROM SCRATCH with ResponsiveLayout + ResponsiveDataTable
 * 
 * DESKTOP: Dense table with hover rows, inline slide-over details
 * MOBILE: Card-style list with full-screen details, swipe gestures
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { 
  Certificate, Download, Trash, X, Plus, Info,
  CheckCircle, Warning, UploadSimple, Clock, ArrowClockwise, LinkBreak, Star, ArrowsLeftRight
} from '@phosphor-icons/react'
import {
  ResponsiveLayout, ResponsiveDataTable, Badge, Button, Modal, HelpCard,
  CertificateDetails, CertificateCompareModal
} from '../components'
import { ExportModal } from '../components/ExportModal'
import { SmartImportModal } from '../components/SmartImport'
import { certificatesService, casService, truststoreService } from '../services'
import { useNotification, useMobile, useWindowManager } from '../contexts'
import { usePermission, useRecentHistory, useFavorites, useWebSocket, usePersistedState } from '../hooks'
import { extractCN, cn, downloadBlob } from '../lib/utils'
import { IssueCertificateForm } from './certificates/IssueCertificateForm'
import { useCertificateColumns } from './certificates/useCertificateColumns'
import { UploadKeyModal } from './certificates/UploadKeyModal'

export default function CertificatesPage() {
  const { t } = useTranslation()
  const { id: urlCertId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const { isMobile } = useMobile()
  const { openWindow } = useWindowManager()
  const { addToHistory } = useRecentHistory('certificates')
  const { isFavorite, toggleFavorite } = useFavorites('certificates')
  
  // Data
  const [certificates, setCertificates] = useState([])
  const [cas, setCas] = useState([])
  const [loading, setLoading] = useState(true)
  const [certStats, setCertStats] = useState({ valid: 0, expiring: 0, expired: 0, revoked: 0, total: 0 })
  
  // Selection
  const [selectedCert, setSelectedCert] = useState(null)
  const [showIssueModal, setShowIssueModal] = useState(false)
  const [issueInitialData, setIssueInitialData] = useState(null)
  const [showImportModal, setShowImportModal] = useState(false)
  const [showKeyModal, setShowKeyModal] = useState(false)
  const [showCompareModal, setShowCompareModal] = useState(false)
  const [exportRowCert, setExportRowCert] = useState(null)
  
  // Pagination
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  const [total, setTotal] = useState(0)
  
  // Sorting (server-side)
  const [sortBy, setSortBy] = useState('subject')
  const [sortOrder, setSortOrder] = useState('asc')
  
  // Filters
  const [filterStatus, setFilterStatus] = usePersistedState('ucm-filter-certs-status', [])
  const [filterCA, setFilterCA] = usePersistedState('ucm-filter-certs-ca', [])
  
  // Apply filter preset callback
  const handleApplyFilterPreset = useCallback((filters) => {
    setPage(1) // Reset to first page when applying preset
    if (filters.status) {
      setFilterStatus(Array.isArray(filters.status) ? filters.status : [filters.status])
    } else {
      setFilterStatus([])
    }
    if (filters.ca) setFilterCA(Array.isArray(filters.ca) ? filters.ca : [filters.ca])
    else setFilterCA([])
  }, [])
  
  const { showSuccess, showError, showConfirm, showPrompt, showWarning } = useNotification()
  const { canWrite, canDelete } = usePermission()
  const { muteToasts } = useWebSocket()

  // Load data - reload when filters or sort change
  useEffect(() => {
    loadData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, perPage, JSON.stringify(filterStatus), JSON.stringify(filterCA), sortBy, sortOrder])

  // Reload when floating window actions change data
  useEffect(() => {
    const handler = (e) => {
      if (e.detail?.type === 'certificate') loadData()
    }
    window.addEventListener('ucm:data-changed', handler)
    return () => window.removeEventListener('ucm:data-changed', handler)
  }, [])

  // Handle re-key prefill from CSRs page navigation
  useEffect(() => {
    if (location.state?.prefill && location.state?.source === 'rekey') {
      if (canWrite('certificates')) {
        setIssueInitialData(location.state.prefill)
        setShowIssueModal(true)
      }
      // Clear navigation state to prevent re-triggering on refresh
      navigate(location.pathname, { replace: true, state: {} })
    }
  }, [location.state])

  const loadData = async () => {
    try {
      setLoading(true)
      
      // Build query params with filters and sort
      const params = { 
        page, 
        per_page: perPage,
        sort_by: sortBy,
        sort_order: sortOrder
      }
      if (filterStatus.length > 0 && !filterStatus.includes('orphan')) {
        params.status = filterStatus
      }
      if (filterCA.length > 0) {
        params.ca_id = filterCA
      }
      
      const [certsRes, casRes, statsRes] = await Promise.all([
        certificatesService.getAll(params),
        casService.getAll(),
        certificatesService.getStats()
      ])
      let certs = certsRes.data || []
      
      // Handle orphan filter client-side (no CA or CA not in our list)
      if (filterStatus.includes('orphan') && cas.length > 0) {
        const caRefIds = new Set(cas.map(ca => ca.refid))
        certs = certs.filter(c => c.caref && !caRefIds.has(c.caref))
      }
      
      setCertificates(certs)
      setTotal(certsRes.meta?.total || certsRes.pagination?.total || certs.length)
      setCas(casRes.data || [])
      setCertStats(statsRes.data || { valid: 0, expiring: 0, expired: 0, revoked: 0, total: 0 })
    } catch (error) {
      showError(error.message || t('messages.errors.loadFailed.certificates'))
    } finally {
      setLoading(false)
    }
  }

  // Load cert details — floating window on desktop, slide-over on mobile
  const handleSelectCert = useCallback(async (cert) => {
    if (!cert) {
      setSelectedCert(null)
      return
    }

    // Desktop: open floating detail window
    if (!isMobile) {
      openWindow('certificate', cert.id)
      // Add to recent history
      addToHistory({
        id: cert.id,
        name: cert.common_name || extractCN(cert.subject) || `Certificate ${cert.id}`,
        subtitle: cert.issuer ? extractCN(cert.issuer) : ''
      })
      return
    }

    // Mobile: slide-over
    try {
      const res = await certificatesService.getById(cert.id)
      const fullCert = res.data || cert
      setSelectedCert(fullCert)
      addToHistory({
        id: fullCert.id,
        name: fullCert.common_name || extractCN(fullCert.subject) || `Certificate ${fullCert.id}`,
        subtitle: fullCert.issuer ? extractCN(fullCert.issuer) : ''
      })
    } catch {
      setSelectedCert(cert)
    }
  }, [addToHistory, isMobile, openWindow])

  // Deep-link: auto-select certificate from URL param
  useEffect(() => {
    if (urlCertId && !loading && certificates.length > 0) {
      const id = parseInt(urlCertId, 10)
      if (!isNaN(id)) {
        if (!isMobile) {
          openWindow('certificate', id)
        } else {
          handleSelectCert({ id })
        }
        navigate('/certificates', { replace: true })
      }
    }
  }, [urlCertId, loading, certificates.length])

  // Export certificate
  const handleExport = async (format, options = {}) => {
    if (!selectedCert) return
    
    try {
      const blob = await certificatesService.export(selectedCert.id, format, options)
      const ext = { pem: 'pem', der: 'der', pkcs7: 'p7b', pkcs12: 'p12', pfx: 'pfx', jks: 'jks' }[format] || format
      downloadBlob(blob, `${selectedCert.common_name || 'certificate'}.${ext}`)
      showSuccess(t('messages.success.export.certificate'))
    } catch {
      showError(t('messages.errors.exportFailed.certificate'))
    }
  }

  // Revoke certificate
  const handleRevoke = async (id) => {
    const confirmed = await showConfirm(
      t('certificates.revokeWarning', 'Revoking a certificate is permanent and cannot be undone. The certificate will be added to the CRL and will no longer be trusted by any client that checks revocation status. Only proceed if you are certain this certificate should be permanently invalidated.'),
      {
        title: t('certificates.revokeCertificate'),
        confirmText: t('certificates.revokeCertificate').split(' ')[0],
        variant: 'danger'
      }
    )
    if (!confirmed) return
    try {
      muteToasts()
      await certificatesService.revoke(id)
      showSuccess(t('messages.success.other.revoked'))
      loadData()
      setSelectedCert(null)
    } catch {
      showError(t('messages.errors.revokeFailed.certificate'))
    }
  }

  // Renew certificate
  const handleRenew = async (id) => {
    const confirmed = await showConfirm(
      t('certificates.confirmRenew'),
      {
        title: t('certificates.renewCertificate'),
        confirmText: t('common.refresh'),
        variant: 'primary'
      }
    )
    if (!confirmed) return
    try {
      muteToasts()
      await certificatesService.renew(id)
      showSuccess(t('notifications.certificateIssued', { name: '' }).replace(': ', ''))
      loadData()
      setSelectedCert(null)
    } catch (error) {
      showError(error.message || t('common.operationFailed'))
    }
  }

  // Delete certificate
  const handleDelete = async (id) => {
    const confirmed = await showConfirm(t('messages.confirm.delete.certificate'), {
      title: t('common.deleteCertificate'),
      confirmText: t('common.delete'),
      variant: 'danger'
    })
    if (!confirmed) return
    try {
      muteToasts()
      await certificatesService.delete(id)
      showSuccess(t('messages.success.delete.certificate'))
      loadData()
      setSelectedCert(null)
    } catch (error) {
      showError(error.message || t('messages.errors.deleteFailed.certificate'))
    }
  }

  const handleAddToTrustStore = async (caRefid) => {
    try {
      await truststoreService.addFromCA(caRefid)
      showSuccess(t('details.addedToTrustStore'))
      // Refresh cert detail to update chain_status
      const res = await certificatesService.getById(selectedCert.id)
      setSelectedCert(res.data)
    } catch (error) {
      showError(error.message || t('details.addToTrustStoreFailed'))
    }
  }

  // Normalize and filter data - detect orphans (cert without existing CA)
  const filteredCerts = useMemo(() => {
    const caRefIds = new Set(cas.map(ca => ca.refid))
    
    let result = certificates.map(cert => ({
      ...cert,
      status: cert.revoked ? 'revoked' : cert.status,
      cn: cert.cn || cert.common_name || extractCN(cert.subject) || cert.descr || (cert.san_dns ? JSON.parse(cert.san_dns)[0] : null) || 'Certificate',
      isOrphan: cert.caref && !caRefIds.has(cert.caref)
    }))
    
    if (filterStatus.length > 0) {
      result = result.filter(c => filterStatus.includes(c.status))
    }
    
    return result
  }, [certificates, cas, filterStatus, filterCA])

  // Count orphans for stats
  const orphanCount = useMemo(() => {
    const caRefIds = new Set(cas.map(ca => ca.refid))
    return certificates.filter(c => c.caref && !caRefIds.has(c.caref)).length
  }, [certificates, cas])

  // Stats - from backend API for accurate counts
  // Each stat is clickable to filter the table
  const stats = useMemo(() => {
    const baseStats = [
      { icon: CheckCircle, label: t('common.valid'), value: certStats.valid, variant: 'success', filterValue: 'valid' },
      { icon: Warning, label: t('common.expiring'), shortLabel: t('common.expiring').substring(0, 3) + '.', value: certStats.expiring, variant: 'warning', filterValue: 'expiring' },
      { icon: Clock, label: t('common.expired'), value: certStats.expired, variant: 'neutral', filterValue: 'expired' },
      { icon: X, label: t('common.revoked'), shortLabel: t('common.revoked').substring(0, 3) + '.', value: certStats.revoked, variant: 'danger', filterValue: 'revoked' }
    ]
    // Add orphan stat if there are any
    if (orphanCount > 0) {
      baseStats.push({ icon: LinkBreak, label: t('certificates.orphan'), value: orphanCount, variant: 'warning', filterValue: 'orphan' })
    }
    baseStats.push({ icon: Certificate, label: t('common.total'), value: certStats.total, variant: 'primary', filterValue: '' })
    return baseStats
  }, [certStats, orphanCount, t])
  
  // Handle stat click to filter
  const handleStatClick = useCallback((filterValue) => {
    setPage(1) // Reset to first page when filtering
    if (filterValue === '') {
      setFilterStatus([]) // "Total" clears all
    } else {
      setFilterStatus(prev => {
        if (prev.includes(filterValue)) {
          return prev.filter(v => v !== filterValue)
        }
        return [...prev, filterValue]
      })
    }
  }, [])
  
  // Handle sort change (server-side)
  const handleSortChange = useCallback((newSort) => {
    setPage(1) // Reset to first page when sorting
    if (newSort) {
      // Map frontend column keys to backend field names
      const keyMap = {
        'cn': 'subject',
        'common_name': 'subject',
        'status': 'status', // Backend handles with CASE (groups by type)
        'issuer': 'issuer',
        'expires': 'valid_to',
        'valid_to': 'valid_to',
        'key_type': 'key_algo',
        'created_at': 'created_at',
        'compliance_grade': 'compliance_grade'
      }
      const backendKey = keyMap[newSort.key]
      if (backendKey) {
        setSortBy(backendKey)
        setSortOrder(newSort.direction)
      }
    } else {
      setSortBy('subject')
      setSortOrder('asc')
    }
  }, [])

  // Column definitions (extracted to sub-module)
  const columns = useCertificateColumns(t)

  // Row actions
  const rowActions = useCallback((row) => [
    { label: t('common.details'), icon: Info, onClick: () => handleSelectCert(row) },
    { label: t('export.title'), icon: Download, onClick: () => setExportRowCert(row) },
    ...(canWrite('certificates') && !row.revoked && row.has_private_key ? [
      { label: t('certificates.renewCertificate').split(' ')[0], icon: ArrowClockwise, onClick: () => handleRenew(row.id) }
    ] : []),
    ...(canWrite('certificates') && !row.revoked ? [
      { label: t('certificates.revokeCertificate').split(' ')[0], icon: X, variant: 'danger', onClick: () => handleRevoke(row.id) }
    ] : []),
    ...(canDelete('certificates') ? [
      { label: t('common.delete'), icon: Trash, variant: 'danger', onClick: () => handleDelete(row.id) }
    ] : [])
  ], [canWrite, canDelete, t])

  // Export from row via ExportModal
  const handleExportRow = async (format, options = {}) => {
    if (!exportRowCert) return
    const cert = exportRowCert
    try {
      const blob = await certificatesService.export(cert.id, format, options)
      const ext = { pkcs12: 'p12', pkcs7: 'p7b', jks: 'jks' }[format] || format
      downloadBlob(blob, `${cert.common_name || cert.cn || 'certificate'}.${ext}`)
      showSuccess(t('messages.success.export.certificate'))
    } catch {
      showError(t('messages.errors.exportFailed.certificate'))
    }
  }

  // Filters
  const filters = useMemo(() => [
    {
      key: 'status',
      label: t('common.status'),
      type: 'multiSelect',
      value: filterStatus,
      onChange: (val) => { setPage(1); setFilterStatus(val) },
      placeholder: t('common.allStatus'),
      options: [
        { value: 'valid', label: t('common.valid') },
        { value: 'expiring', label: t('common.expiring') },
        { value: 'expired', label: t('common.expired') },
        { value: 'revoked', label: t('common.revoked') }
      ]
    },
    {
      key: 'ca',
      label: t('common.issuer'),
      type: 'multiSelect',
      value: filterCA,
      onChange: (val) => { setPage(1); setFilterCA(val) },
      placeholder: t('common.allCAs'),
      options: cas.map(ca => ({ 
        value: String(ca.id), 
        label: ca.descr || ca.common_name 
      }))
    }
  ], [filterStatus, filterCA, cas, t])

  const activeFilters = (filterStatus.length > 0 ? 1 : 0) + (filterCA.length > 0 ? 1 : 0)

  // Help content
  const helpContent = (
    <div className="space-y-4">
      {/* Quick Stats */}
      <div className="visual-section">
        <div className="visual-section-header">
          <Certificate size={16} className="status-primary-text" />
          {t('common.certificates')}
        </div>
        <div className="visual-section-body">
          <div className="quick-info-grid">
            <div className="help-stat-card">
              <div className="help-stat-value help-stat-value-success">{stats.find(s => s.filterValue === 'valid')?.value || 0}</div>
              <div className="help-stat-label">{t('common.valid')}</div>
            </div>
            <div className="help-stat-card">
              <div className="help-stat-value help-stat-value-warning">{stats.find(s => s.filterValue === 'expiring')?.value || 0}</div>
              <div className="help-stat-label">{t('common.expiring')}</div>
            </div>
            <div className="help-stat-card">
              <div className="help-stat-value help-stat-value-danger">{stats.find(s => s.filterValue === 'expired')?.value || 0}</div>
              <div className="help-stat-label">{t('common.expired')}</div>
            </div>
          </div>
        </div>
      </div>

      <HelpCard title={t('help.aboutCertificates')} variant="info">
        {t('common.certificates')}
      </HelpCard>
      <HelpCard title={t('help.statusLegend')} variant="info">
        <div className="space-y-1.5 mt-2">
          <div className="flex items-center gap-2">
            <Badge variant="success" size="sm" dot>{t('common.valid')}</Badge>
            <span className="text-xs">{t('common.active')}</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="warning" size="sm" dot>{t('common.expiring')}</Badge>
            <span className="text-xs">{t('common.expiring')}</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="danger" size="sm" dot>{t('common.revoked')}</Badge>
            <span className="text-xs">{t('common.invalid')}</span>
          </div>
        </div>
      </HelpCard>
      <HelpCard title={t('help.exportFormats')} variant="tip">
        {t('certificates.exportPEM')}, {t('certificates.exportDER')}, {t('certificates.exportPKCS12')}
      </HelpCard>
    </div>
  )

  // Slide-over content
  const slideOverContent = selectedCert ? (
    <CertificateDetails
      certificate={selectedCert}
      onExport={handleExport}
      onRevoke={() => handleRevoke(selectedCert.id)}
      onRenew={selectedCert.has_private_key && !selectedCert.revoked ? () => handleRenew(selectedCert.id) : null}
      onDelete={() => handleDelete(selectedCert.id)}
      onUploadKey={() => setShowKeyModal(true)}
      onAddToTrustStore={handleAddToTrustStore}
      canWrite={canWrite('certificates')}
      canDelete={canDelete('certificates')}
    />
  ) : null

  return (
    <>
      <ResponsiveLayout
        title={t('common.certificates')}
        subtitle={t('certificates.subtitle', { count: total })}
        icon={Certificate}
        stats={stats}
        onStatClick={handleStatClick}
        activeStatFilter={filterStatus}
        helpPageKey="certificates"
        splitView={isMobile}
        splitEmptyContent={isMobile ? (
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
              <Certificate size={24} className="text-text-tertiary" />
            </div>
            <p className="text-sm text-text-secondary">{t('certificates.noCertificates')}</p>
          </div>
        ) : undefined}
        slideOverOpen={isMobile && !!selectedCert}
        slideOverTitle={selectedCert?.cn || selectedCert?.common_name || t('common.certificate')}
        slideOverContent={isMobile ? slideOverContent : null}
        slideOverWidth="wide"
        slideOverActions={selectedCert && (
          <button
            onClick={() => toggleFavorite({
              id: selectedCert.id,
              name: selectedCert.common_name || extractCN(selectedCert.subject),
              subtitle: selectedCert.issuer ? extractCN(selectedCert.issuer) : ''
            })}
            className={cn(
              'p-1.5 rounded-md transition-colors',
              isFavorite(selectedCert.id)
                ? 'text-status-warning hover:text-status-warning bg-status-warning-op10'
                : 'text-text-tertiary hover:text-status-warning hover:bg-status-warning-op10'
            )}
          >
            <Star size={16} weight={isFavorite(selectedCert.id) ? 'fill' : 'regular'} />
          </button>
        )}
        onSlideOverClose={() => setSelectedCert(null)}
      >
        <ResponsiveDataTable
          data={filteredCerts}
          columns={columns}
          loading={loading}
          onRowClick={handleSelectCert}
          selectedId={selectedCert?.id}
          searchable
          searchPlaceholder={t('common.search') + ' ' + t('common.certificates').toLowerCase() + '...'}
          searchKeys={['cn', 'common_name', 'subject', 'issuer', 'serial']}
          columnStorageKey="ucm-certs-columns"
          filterPresetsKey="ucm-certs-presets"
          densityStorageKey="ucm-certs-density"
          onApplyFilterPreset={handleApplyFilterPreset}
          exportEnabled
          exportFilename="certificates"
          toolbarFilters={filters}
          toolbarActions={
            <div className="flex items-center gap-2">
              {!isMobile && (
                <Button type="button" size="sm" variant="secondary" onClick={() => setShowCompareModal(true)}>
                  <ArrowsLeftRight size={14} />
                  {t('common.compare') || 'Compare'}
                </Button>
              )}
              {canWrite('certificates') && (
                isMobile ? (
                  <>
                    <Button type="button" size="lg" variant="secondary" onClick={() => setShowImportModal(true)} className="w-11 h-11 p-0">
                      <UploadSimple size={22} weight="bold" />
                    </Button>
                    <Button type="button" size="lg" onClick={() => setShowIssueModal(true)} className="w-11 h-11 p-0">
                      <Plus size={22} weight="bold" />
                    </Button>
                  </>
                ) : (
                  <>
                    <Button type="button" size="sm" variant="secondary" onClick={() => setShowImportModal(true)}>
                      <UploadSimple size={14} />
                      {t('common.import')}
                    </Button>
                    <Button type="button" size="sm" onClick={() => setShowIssueModal(true)}>
                      <Plus size={14} weight="bold" />
                      {t('certificates.issueCertificate').split(' ')[0]}
                    </Button>
                  </>
                )
              )}
            </div>
          }
          sortable
          defaultSort={{ key: 'cn', direction: 'asc' }}
          onSortChange={handleSortChange}
          pagination={{
            page,
            total,
            perPage,
            onChange: setPage,
            onPerPageChange: (v) => { setPerPage(v); setPage(1) }
          }}
          emptyIcon={Certificate}
          emptyTitle={t('certificates.noCertificates')}
          emptyDescription={t('certificates.issueCertificate')}
          emptyAction={canWrite('certificates') && (
            <Button type="button" onClick={() => setShowIssueModal(true)}>
              <Plus size={16} /> {t('certificates.issueCertificate')}
            </Button>
          )}
        />
      </ResponsiveLayout>

      {/* Issue Certificate Modal */}
      <Modal
        open={showIssueModal}
        onOpenChange={(open) => {
          setShowIssueModal(open)
          if (!open) setIssueInitialData(null)
        }}
        title={t('certificates.issueCertificate')}
        size="xl"
      >
        <IssueCertificateForm
          cas={cas}
          initialData={issueInitialData}
          onSubmit={async (data) => {
            try {
              muteToasts()
              const response = await certificatesService.create(data)
              if (response?.data?.approval_required) {
                showWarning(t('certificates.approvalRequired', { policy: response.data.policy_name }))
              } else {
                showSuccess(t('messages.success.create.certificate'))
              }
              setShowIssueModal(false)
              setIssueInitialData(null)
              loadData()
            } catch (error) {
              showError(error.message || t('common.operationFailed'))
            }
          }}
          onCancel={() => { setShowIssueModal(false); setIssueInitialData(null) }}
          t={t}
        />
      </Modal>

      {/* Upload Private Key Modal */}
      <UploadKeyModal
        open={showKeyModal}
        onOpenChange={(open) => setShowKeyModal(open)}
        selectedCert={selectedCert}
        onUploadComplete={(updatedCert) => {
          loadData()
          setSelectedCert(updatedCert)
        }}
        t={t}
      />

      {/* Certificate Compare Modal */}
      <CertificateCompareModal
        open={showCompareModal}
        onClose={() => setShowCompareModal(false)}
        certificates={certificates}
        initialCert={selectedCert}
      />

      {/* Smart Import Modal */}
      <SmartImportModal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        onImportComplete={() => {
          setShowImportModal(false)
          loadData()
        }}
      />

      {/* Row Export Modal */}
      <ExportModal
        open={!!exportRowCert}
        onClose={() => setExportRowCert(null)}
        entityType="certificate"
        entityName={exportRowCert?.common_name || exportRowCert?.subject || ''}
        hasPrivateKey={!!exportRowCert?.has_private_key}
        canExportKey={canWrite('certificates')}
        onExport={handleExportRow}
      />
    </>
  )
}
