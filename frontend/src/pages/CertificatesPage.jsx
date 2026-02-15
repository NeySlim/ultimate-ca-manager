/**
 * CertificatesPage - FROM SCRATCH with ResponsiveLayout + ResponsiveDataTable
 * 
 * DESKTOP: Dense table with hover rows, inline slide-over details
 * MOBILE: Card-style list with full-screen details, swipe gestures
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams, useNavigate } from 'react-router-dom'
import { 
  Certificate, Download, Trash, X, Plus, Info,
  CheckCircle, Warning, UploadSimple, Clock, XCircle, ArrowClockwise, LinkBreak, Star, ArrowsLeftRight
} from '@phosphor-icons/react'
import {
  ResponsiveLayout, ResponsiveDataTable, Badge, Button, Modal, Select, Input, Textarea, HelpCard,
  CertificateDetails, CertificateCompareModal, KeyIndicator
} from '../components'
import { SmartImportModal } from '../components/SmartImport'
import { certificatesService, casService, truststoreService } from '../services'
import { useNotification, useMobile, useWindowManager } from '../contexts'
import { ERRORS, SUCCESS, LABELS, CONFIRM } from '../lib/messages'
import { usePermission, useRecentHistory, useFavorites } from '../hooks'
import { formatDate, extractCN, cn } from '../lib/utils'

export default function CertificatesPage() {
  const { t } = useTranslation()
  const { id: urlCertId } = useParams()
  const navigate = useNavigate()
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
  const [showImportModal, setShowImportModal] = useState(false)
  const [showKeyModal, setShowKeyModal] = useState(false)
  const [showCompareModal, setShowCompareModal] = useState(false)
  const [keyPem, setKeyPem] = useState('')
  const [keyPassphrase, setKeyPassphrase] = useState('')
  
  // Pagination
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  const [total, setTotal] = useState(0)
  
  // Sorting (server-side)
  const [sortBy, setSortBy] = useState('subject')
  const [sortOrder, setSortOrder] = useState('asc')
  
  // Filters
  const [filterStatus, setFilterStatus] = useState('')
  const [filterCA, setFilterCA] = useState('')
  
  // Apply filter preset callback
  const handleApplyFilterPreset = useCallback((filters) => {
    setPage(1) // Reset to first page when applying preset
    if (filters.status) setFilterStatus(filters.status)
    else setFilterStatus('')
    if (filters.ca) setFilterCA(filters.ca)
    else setFilterCA('')
  }, [])
  
  const { showSuccess, showError, showConfirm, showPrompt } = useNotification()
  const { canWrite, canDelete } = usePermission()

  // Load data - reload when filters or sort change
  useEffect(() => {
    loadData()
  }, [page, perPage, filterStatus, filterCA, sortBy, sortOrder])

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
      if (filterStatus && filterStatus !== 'orphan') {
        params.status = filterStatus
      }
      if (filterCA) {
        params.ca_id = filterCA
      }
      
      const [certsRes, casRes, statsRes] = await Promise.all([
        certificatesService.getAll(params),
        casService.getAll(),
        certificatesService.getStats()
      ])
      let certs = certsRes.data || []
      
      // Handle orphan filter client-side (no CA or CA not in our list)
      if (filterStatus === 'orphan' && cas.length > 0) {
        const caIds = new Set(cas.map(ca => ca.id))
        certs = certs.filter(c => c.ca_id && !caIds.has(c.ca_id) && !caIds.has(Number(c.ca_id)))
      }
      
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
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const ext = { pem: 'pem', der: 'der', pkcs7: 'p7b', pkcs12: 'p12', pfx: 'pfx' }[format] || format
      a.download = `${selectedCert.common_name || 'certificate'}.${ext}`
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
      title: t('certificates.revokeCertificate'),
      confirmText: t('certificates.revokeCertificate').split(' ')[0],
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
    const confirmed = await showConfirm(CONFIRM.DELETE.CERTIFICATE, {
      title: t('common.deleteCertificate'),
      confirmText: t('common.delete'),
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

  const handleAddToTrustStore = async (caRefid) => {
    try {
      await truststoreService.addFromCA(caRefid)
      showSuccess(t('details.addedToTrustStore'))
      // Refresh cert detail to update chain_status
      const res = await certificatesService.getById(selectedCert.id)
      setSelectedCert(res.data)
    } catch (error) {
      showError(error.response?.data?.error || error.message || t('details.addToTrustStoreFailed'))
    }
  }

  const handleUploadKey = async () => {
    if (!keyPem.trim()) {
      showError(t('validation.required'))
      return
    }
    if (!keyPem.includes('PRIVATE KEY')) {
      showError(t('validation.invalidFormat'))
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
      showError(error.message || t('common.operationFailed'))
    }
  }

  // Normalize and filter data - detect orphans (cert without existing CA)
  const filteredCerts = useMemo(() => {
    const caIds = new Set(cas.map(ca => ca.id))
    
    let result = certificates.map(cert => ({
      ...cert,
      status: cert.revoked ? 'revoked' : cert.status,
      cn: cert.cn || cert.common_name || extractCN(cert.subject) || cert.descr || (cert.san_dns ? JSON.parse(cert.san_dns)[0] : null) || 'Certificate',
      isOrphan: cert.ca_id && !caIds.has(cert.ca_id) && !caIds.has(Number(cert.ca_id))
    }))
    
    if (filterStatus) {
      result = result.filter(c => c.status === filterStatus)
    }
    
    if (filterCA) {
      result = result.filter(c => String(c.ca_id) === filterCA || c.caref === filterCA)
    }
    
    return result
  }, [certificates, cas, filterStatus, filterCA])

  // Count orphans for stats
  const orphanCount = useMemo(() => {
    const caIds = new Set(cas.map(ca => ca.id))
    return certificates.filter(c => c.ca_id && !caIds.has(c.ca_id) && !caIds.has(Number(c.ca_id))).length
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
    if (filterValue === filterStatus) {
      setFilterStatus('') // Toggle off if same
    } else {
      setFilterStatus(filterValue)
    }
  }, [filterStatus])
  
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
        'created_at': 'created_at'
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

  // Table columns
  // Status badge helper for mobile
  const getStatusBadge = (row) => {
    const isRevoked = row.revoked
    const status = isRevoked ? 'revoked' : row.status || 'unknown'
    const config = {
      valid: { variant: 'success', icon: CheckCircle, label: t('common.valid'), pulse: true },
      expiring: { variant: 'warning', icon: Clock, label: t('common.expiring'), pulse: true },
      expired: { variant: 'danger', icon: XCircle, label: t('common.expired'), pulse: false },
      revoked: { variant: 'danger', icon: X, label: t('common.revoked'), pulse: false },
      unknown: { variant: 'secondary', icon: Info, label: t('common.status'), pulse: false }
    }
    const { variant, icon, label, pulse } = config[status] || config.unknown
    return <Badge variant={variant} size="sm" icon={icon} dot pulse={pulse}>{label}</Badge>
  }

  const columns = useMemo(() => [
    {
      key: 'cn',
      header: t('common.commonName'),
      priority: 1,
      sortable: true,
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <div className={cn(
            "w-7 h-7 rounded-lg flex items-center justify-center shrink-0",
            row.has_private_key ? "icon-bg-emerald" : "icon-bg-blue"
          )}>
            <Certificate size={14} weight="duotone" />
          </div>
          <span className="font-medium truncate">{val}</span>
          <KeyIndicator hasKey={row.has_private_key} size={14} />
          {row.isOrphan && <Badge variant="warning" size="sm" icon={LinkBreak} title={t('certificates.orphanDescription')}>{t('certificates.orphan')}</Badge>}
          {row.source === 'import' && <Badge variant="secondary" size="sm" dot>IMPORT</Badge>}
          {row.source === 'acme' && <Badge variant="cyan" size="sm" dot>LOCAL ACME</Badge>}
          {row.source === 'letsencrypt' && <Badge variant="green" size="sm" dot>LET'S ENCRYPT</Badge>}
          {row.source === 'scep' && <Badge variant="orange" size="sm" dot>SCEP</Badge>}
        </div>
      ),
      // Mobile: Icon + CN left + status badge right
      mobileRender: (val, row) => (
        <div className="flex items-center justify-between gap-2 w-full">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <div className={cn(
              "w-7 h-7 rounded-lg flex items-center justify-center shrink-0",
              row.has_private_key ? "icon-bg-emerald" : "icon-bg-blue"
            )}>
              <Certificate size={14} weight="duotone" />
            </div>
            <span className="font-medium truncate">{val || row.cn || row.common_name || t('common.certificate')}</span>
            <KeyIndicator hasKey={row.has_private_key} size={12} />
          </div>
          <div className="shrink-0">
            {getStatusBadge(row)}
          </div>
        </div>
      )
    },
    {
      key: 'status',
      header: t('common.status'),
      priority: 2,
      sortable: true, // Groups by status type, then alphabetically
      hideOnMobile: true, // Status shown in CN mobileRender
      render: (val, row) => {
        const isRevoked = row.revoked
        const status = isRevoked ? 'revoked' : val || 'unknown'
        const config = {
          valid: { variant: 'success', icon: CheckCircle, label: t('common.valid'), pulse: true },
          expiring: { variant: 'warning', icon: Clock, label: t('common.expiring'), pulse: true },
          expired: { variant: 'danger', icon: XCircle, label: t('common.expired'), pulse: false },
          revoked: { variant: 'danger', icon: X, label: t('common.revoked'), pulse: false },
          unknown: { variant: 'secondary', icon: Info, label: t('common.status'), pulse: false }
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
      header: t('common.issuer'),
      priority: 3,
      sortable: true,
      render: (val, row) => (
        <span className="text-text-secondary truncate">
          {extractCN(val) || row.issuer_name || '—'}
        </span>
      ),
      // Mobile: labeled CA info
      mobileRender: (val, row) => (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-text-tertiary">CA:</span>
          <span className="text-text-secondary truncate">{extractCN(val) || row.issuer_name || '—'}</span>
        </div>
      )
    },
    {
      key: 'valid_to',
      header: t('common.expires'),
      priority: 4,
      sortable: true,
      mono: true,
      render: (val) => (
        <span className="text-xs text-text-secondary whitespace-nowrap">
          {formatDate(val)}
        </span>
      ),
      // Mobile: labeled expiration with badges
      mobileRender: (val, row) => (
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex items-center gap-2 text-xs">
            <span className="text-text-tertiary">{t('common.expires').substring(0, 3)}:</span>
            <span className="text-text-secondary font-mono">{formatDate(val)}</span>
          </div>
          {row.isOrphan && <Badge variant="warning" size="xs" icon={LinkBreak}>{t('certificates.orphan')}</Badge>}
          {row.source === 'import' && <Badge variant="secondary" size="xs" dot>IMPORT</Badge>}
          {row.source === 'acme' && <Badge variant="cyan" size="xs" dot>LOCAL ACME</Badge>}
          {row.source === 'letsencrypt' && <Badge variant="green" size="xs" dot>LET'S ENCRYPT</Badge>}
          {row.source === 'scep' && <Badge variant="orange" size="xs" dot>SCEP</Badge>}
        </div>
      )
    },
    {
      key: 'key_type',
      header: t('common.keyType'),
      hideOnMobile: true,
      sortable: true,
      mono: true,
      render: (val, row) => (
        <span className="text-xs text-text-secondary">
          {row.key_algorithm || row.key_algo || val || 'RSA'}
        </span>
      )
    }
  ], [t])

  // Row actions
  const rowActions = useCallback((row) => [
    { label: t('common.details'), icon: Info, onClick: () => handleSelectCert(row) },
    { label: t('certificates.exportPEM'), icon: Download, onClick: () => handleExportRow(row, 'pem') },
    { label: t('certificates.exportPKCS12'), icon: Download, onClick: () => handleExportRow(row, 'p12') },
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

  // Export from row (uses showPrompt for P12 password since it's from a menu)
  const handleExportRow = async (cert, format, options = {}) => {
    if ((format === 'p12' || format === 'pkcs12') && cert.has_private_key) {
      const password = await showPrompt(t('certificates.enterP12Password', 'Enter password for PKCS#12 file:'), {
        title: t('certificates.exportPKCS12', 'Export PKCS#12'),
        type: 'password',
        placeholder: t('common.password', 'Password'),
        confirmText: t('common.export', 'Export')
      })
      if (!password || password.length < 4) return
      options = { ...options, password }
    }
    
    try {
      const blob = await certificatesService.export(cert.id, format, options)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const ext = { pkcs12: 'p12', pkcs7: 'p7b' }[format] || format
      a.download = `${cert.common_name || cert.cn || 'certificate'}.${ext}`
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
      label: t('common.status'),
      type: 'select',
      value: filterStatus,
      onChange: setFilterStatus,
      placeholder: LABELS.FILTERS.ALL_STATUS,
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
      type: 'select',
      value: filterCA,
      onChange: setFilterCA,
      placeholder: LABELS.FILTERS.ALL_CAS,
      options: cas.map(ca => ({ 
        value: String(ca.id), 
        label: ca.descr || ca.common_name 
      }))
    }
  ], [filterStatus, filterCA, cas, t])

  const activeFilters = (filterStatus ? 1 : 0) + (filterCA ? 1 : 0)

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
                ? 'text-status-warning hover:text-status-warning bg-status-warning/10'
                : 'text-text-tertiary hover:text-status-warning hover:bg-status-warning/10'
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
          onApplyFilterPreset={handleApplyFilterPreset}
          exportEnabled
          exportFilename="certificates"
          toolbarFilters={[
            {
              key: 'status',
              value: filterStatus,
              onChange: setFilterStatus,
              placeholder: LABELS.FILTERS.ALL_STATUS,
              options: [
                { value: 'valid', label: t('common.valid') },
                { value: 'expiring', label: t('common.expiring') },
                { value: 'expired', label: t('common.expired') },
                { value: 'revoked', label: t('common.revoked') }
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
          toolbarActions={
            <div className="flex items-center gap-2">
              {!isMobile && (
                <Button size="sm" variant="secondary" onClick={() => setShowCompareModal(true)}>
                  <ArrowsLeftRight size={14} />
                  {t('common.compare') || 'Compare'}
                </Button>
              )}
              {canWrite('certificates') && (
                isMobile ? (
                  <>
                    <Button size="lg" variant="secondary" onClick={() => setShowImportModal(true)} className="w-11 h-11 p-0">
                      <UploadSimple size={22} weight="bold" />
                    </Button>
                    <Button size="lg" onClick={() => setShowIssueModal(true)} className="w-11 h-11 p-0">
                      <Plus size={22} weight="bold" />
                    </Button>
                  </>
                ) : (
                  <>
                    <Button size="sm" variant="secondary" onClick={() => setShowImportModal(true)}>
                      <UploadSimple size={14} />
                      {t('common.import')}
                    </Button>
                    <Button size="sm" onClick={() => setShowIssueModal(true)}>
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
            <Button onClick={() => setShowIssueModal(true)}>
              <Plus size={16} /> {t('certificates.issueCertificate')}
            </Button>
          )}
        />
      </ResponsiveLayout>

      {/* Issue Certificate Modal */}
      <Modal
        open={showIssueModal}
        onOpenChange={setShowIssueModal}
        title={t('certificates.issueCertificate')}
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
              showError(error.message || t('common.operationFailed'))
            }
          }}
          onCancel={() => setShowIssueModal(false)}
          t={t}
        />
      </Modal>

      {/* Upload Private Key Modal */}
      <Modal
        open={showKeyModal}
        onOpenChange={() => { setShowKeyModal(false); setKeyPem(''); setKeyPassphrase('') }}
        title={t('common.upload')}
      >
        <div className="p-4 space-y-4">
          <p className="text-sm text-text-secondary">
            {t('common.upload')} <strong>{selectedCert?.cn || selectedCert?.common_name}</strong>
          </p>
          <Textarea
            label={t('common.privateKeyPEM')}
            value={keyPem}
            onChange={(e) => setKeyPem(e.target.value)}
            placeholder="-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQE...
-----END PRIVATE KEY-----"
            rows={8}
            className="font-mono text-xs"
          />
          <Input
            label={t('common.password')}
            type="password"
            value={keyPassphrase}
            onChange={(e) => setKeyPassphrase(e.target.value)}
            placeholder={t('common.optional')}
          />
          <div className="flex justify-end gap-2 pt-2 border-t border-border">
            <Button variant="secondary" onClick={() => { setShowKeyModal(false); setKeyPem(''); setKeyPassphrase('') }}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleUploadKey} disabled={!keyPem.trim()}>
              <UploadSimple size={16} /> {t('common.upload')}
            </Button>
          </div>
        </div>
      </Modal>

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
    </>
  )
}

// Issue Certificate Form
function IssueCertificateForm({ cas, onSubmit, onCancel, t }) {
  const [formData, setFormData] = useState({
    ca_id: '',
    cn: '',
    san: '',
    key_type: 'rsa',
    key_size: '2048',
    validity_days: '365'
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    onSubmit({
      ...formData,
      validity_days: parseInt(formData.validity_days, 10) || 365
    })
  }

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
      <Select
        label={t('common.certificateAuthority')}
        value={formData.ca_id}
        onChange={(val) => setFormData(prev => ({ ...prev, ca_id: val }))}
        placeholder={t('certificates.selectCA')}
        options={cas.map(ca => ({ value: String(ca.id), label: ca.descr || ca.common_name }))}
      />
      
      <Input 
        label={t('common.commonName')} 
        placeholder={t('common.commonNamePlaceholder')}
        value={formData.cn}
        onChange={(e) => setFormData(prev => ({ ...prev, cn: e.target.value }))}
        required
      />
      
      <Textarea 
        label={t('common.subjectAltNames')} 
        placeholder={t('certificates.sanPlaceholder')} 
        rows={3}
        value={formData.san}
        onChange={(e) => setFormData(prev => ({ ...prev, san: e.target.value }))}
      />
      
      <div className="grid grid-cols-2 gap-4">
        <Select
          label={t('common.keyType')}
          value={formData.key_type}
          onChange={(val) => setFormData(prev => ({ ...prev, key_type: val }))}
          options={[
            { value: 'rsa', label: 'RSA' },
            { value: 'ecdsa', label: 'ECDSA' },
          ]}
        />
        
        <Select
          label={t('common.keySize')}
          value={formData.key_size}
          onChange={(val) => setFormData(prev => ({ ...prev, key_size: val }))}
          options={formData.key_type === 'rsa'
            ? [{ value: '2048', label: '2048 bits' }, { value: '4096', label: '4096 bits' }]
            : [{ value: '256', label: 'P-256' }, { value: '384', label: 'P-384' }]
          }
        />
      </div>
      
      <Input 
        label={t('common.validityPeriod') + ' (' + t('common.days') + ')'} 
        type="number"
        placeholder={t('common.validityPlaceholder')}
        value={formData.validity_days}
        onChange={(e) => setFormData(prev => ({ ...prev, validity_days: e.target.value }))}
      />
      
      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button type="submit">
          <Certificate size={16} />
          {t('certificates.issueCertificate')}
        </Button>
      </div>
    </form>
  )
}
