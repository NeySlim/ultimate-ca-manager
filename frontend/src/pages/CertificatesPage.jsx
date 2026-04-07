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
  CheckCircle, Warning, UploadSimple, Clock, XCircle, ArrowClockwise, LinkBreak, Star, ArrowsLeftRight,
  CaretDown, CaretUp
} from '@phosphor-icons/react'
import {
  ResponsiveLayout, ResponsiveDataTable, Badge, Button, Modal, Select, Input, Textarea, DatePicker, HelpCard,
  CertificateDetails, CertificateCompareModal, KeyIndicator
} from '../components'
import { ExportModal } from '../components/ExportModal'
import { SmartImportModal } from '../components/SmartImport'
import { certificatesService, casService, truststoreService, templatesService } from '../services'
import { useNotification, useMobile, useWindowManager } from '../contexts'
import { usePermission, useRecentHistory, useFavorites, useWebSocket } from '../hooks'
import { formatDate, extractCN, cn } from '../lib/utils'

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
  
  const { showSuccess, showError, showConfirm, showPrompt, showWarning } = useNotification()
  const { canWrite, canDelete } = usePermission()
  const { muteToasts } = useWebSocket()

  // Load data - reload when filters or sort change
  useEffect(() => {
    loadData()
  }, [page, perPage, filterStatus, filterCA, sortBy, sortOrder])

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
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const ext = { pem: 'pem', der: 'der', pkcs7: 'p7b', pkcs12: 'p12', pfx: 'pfx', jks: 'jks' }[format] || format
      a.download = `${selectedCert.common_name || 'certificate'}.${ext}`
      a.click()
      URL.revokeObjectURL(url)
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
      showSuccess(t('messages.success.other.keyUploaded'))
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
    const caRefIds = new Set(cas.map(ca => ca.refid))
    
    let result = certificates.map(cert => ({
      ...cert,
      status: cert.revoked ? 'revoked' : cert.status,
      cn: cert.cn || cert.common_name || extractCN(cert.subject) || cert.descr || (cert.san_dns ? JSON.parse(cert.san_dns)[0] : null) || 'Certificate',
      isOrphan: cert.caref && !caRefIds.has(cert.caref)
    }))
    
    if (filterStatus) {
      result = result.filter(c => c.status === filterStatus)
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
            "w-6 h-6 rounded-lg flex items-center justify-center shrink-0",
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
          {row.source === 'msca' && <Badge variant="purple" size="sm" dot>ADCS</Badge>}
          {row.source === 'est' && <Badge variant="yellow" size="sm" dot>EST</Badge>}
        </div>
      ),
      // Mobile: Icon + CN left + status badge right
      mobileRender: (val, row) => (
        <div className="flex items-center justify-between gap-2 w-full">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <div className={cn(
              "w-6 h-6 rounded-lg flex items-center justify-center shrink-0",
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
      key: 'compliance_grade',
      header: t('compliance.grade'),
      priority: 2,
      sortable: true,
      hideOnMobile: true,
      render: (val, row) => {
        const grade = row.compliance_grade || 'F'
        const score = row.compliance_score ?? 0
        const config = {
          'A+': { variant: 'emerald', label: 'A+' },
          'A': { variant: 'success', label: 'A' },
          'B': { variant: 'blue', label: 'B' },
          'C': { variant: 'warning', label: 'C' },
          'D': { variant: 'orange', label: 'D' },
          'F': { variant: 'danger', label: 'F' },
        }
        const { variant, label } = config[grade] || config['F']
        return (
          <Badge variant={variant} size="sm" title={`${score}/100`}>
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
          {row.source === 'msca' && <Badge variant="purple" size="xs" dot>ADCS</Badge>}
          {row.source === 'est' && <Badge variant="yellow" size="xs" dot>EST</Badge>}
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
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const ext = { pkcs12: 'p12', pkcs7: 'p7b', jks: 'jks' }[format] || format
      a.download = `${cert.common_name || cert.cn || 'certificate'}.${ext}`
      a.click()
      URL.revokeObjectURL(url)
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
      type: 'select',
      value: filterStatus,
      onChange: setFilterStatus,
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
      type: 'select',
      value: filterCA,
      onChange: setFilterCA,
      placeholder: t('common.allCAs'),
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
          onApplyFilterPreset={handleApplyFilterPreset}
          exportEnabled
          exportFilename="certificates"
          toolbarFilters={[
            {
              key: 'status',
              value: filterStatus,
              onChange: setFilterStatus,
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
              value: filterCA,
              onChange: setFilterCA,
              placeholder: t('common.allCAs'),
              options: cas.map(ca => ({ 
                value: String(ca.id), 
                label: ca.descr || ca.common_name 
              }))
            }
          ]}
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
            noAutofill
            value={keyPassphrase}
            onChange={(e) => setKeyPassphrase(e.target.value)}
            placeholder={t('common.optional')}
          />
          <div className="flex justify-end gap-2 pt-2 border-t border-border">
            <Button type="button" variant="secondary" onClick={() => { setShowKeyModal(false); setKeyPem(''); setKeyPassphrase('') }}>
              {t('common.cancel')}
            </Button>
            <Button type="button" onClick={handleUploadKey} disabled={!keyPem.trim()}>
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

// Issue Certificate Form — full-featured with template, cert type, structured SANs, date picker
function IssueCertificateForm({ cas, initialData, onSubmit, onCancel, t }) {
  const [templates, setTemplates] = useState([])
  const [selectedTemplate, setSelectedTemplate] = useState('')
  const [showSubject, setShowSubject] = useState(false)
  const [validityMode, setValidityMode] = useState('days') // 'days' or 'date'

  const [formData, setFormData] = useState({
    ca_id: '',
    cn: '',
    cert_type: 'server',
    description: '',
    organization: '',
    organizational_unit: '',
    country: '',
    state: '',
    locality: '',
    email: '',
    key_type: 'rsa',
    key_size: '2048',
    validity_days: '365',
    expiry_date: '',
    ocsp_must_staple: false,
  })

  const [sans, setSans] = useState([{ type: 'dns', value: '' }])

  // Load templates on mount
  useEffect(() => {
    templatesService.getAll().then(res => {
      const list = res?.data || res || []
      setTemplates(Array.isArray(list) ? list : [])
    }).catch(() => {})
  }, [])

  // Apply re-key initial data
  useEffect(() => {
    if (initialData) {
      setFormData(prev => ({
        ...prev,
        cn: initialData.cn || '',
        organization: initialData.organization || '',
        organizational_unit: initialData.organizational_unit || '',
        country: initialData.country || '',
        state: initialData.state || '',
        locality: initialData.locality || '',
        email: initialData.email || '',
        key_type: initialData.key_type || 'rsa',
        key_size: initialData.key_size || '2048',
      }))
      if (initialData.sans?.length > 0) {
        setSans(initialData.sans.filter(s => s && typeof s.type === 'string' && typeof s.value === 'string'))
      }
      setShowSubject(true)
    }
  }, [initialData])

  // Get selected CA's expiry for max date
  const selectedCa = useMemo(() => 
    cas.find(ca => String(ca.id) === formData.ca_id),
    [cas, formData.ca_id]
  )

  const caExpiryDate = useMemo(() => {
    if (!selectedCa) return null
    const d = selectedCa.valid_to || selectedCa.expires || selectedCa.expiry
    if (!d) return null
    return typeof d === 'string' ? d.split('T')[0] : null
  }, [selectedCa])

  // Today as YYYY-MM-DD
  const today = useMemo(() => new Date().toISOString().split('T')[0], [])

  // Apply template when selected
  const handleTemplateChange = (templateId) => {
    setSelectedTemplate(templateId)
    if (!templateId) return
    const tpl = templates.find(t => String(t.id) === templateId)
    if (!tpl) return

    const updates = {}

    // Map template key_type to form fields
    if (tpl.key_type) {
      const [algo, size] = tpl.key_type.split('-')
      if (algo === 'RSA') {
        updates.key_type = 'rsa'
        updates.key_size = size || '2048'
      } else if (algo === 'EC') {
        updates.key_type = 'ecdsa'
        const curveMap = { 'P256': '256', 'P384': '384', 'P521': '521' }
        updates.key_size = curveMap[size] || '256'
      }
    }
    if (tpl.validity_days) updates.validity_days = String(tpl.validity_days)

    // Map template_type to cert_type
    const typeMap = {
      'web_server': 'server', 'vpn_server': 'server',
      'client_auth': 'client', 'vpn_client': 'client',
      'email': 'email', 'code_signing': 'code_signing',
    }
    if (tpl.template_type && typeMap[tpl.template_type]) {
      updates.cert_type = typeMap[tpl.template_type]
    }

    // Apply DN template
    if (tpl.dn_template) {
      const dn = typeof tpl.dn_template === 'string' ? JSON.parse(tpl.dn_template) : tpl.dn_template
      if (dn.O) updates.organization = dn.O
      if (dn.OU) updates.organizational_unit = dn.OU
      if (dn.C) updates.country = dn.C
      if (dn.ST) updates.state = dn.ST
      if (dn.L) updates.locality = dn.L
      // Show subject section if template has DN fields
      if (dn.O || dn.OU || dn.C || dn.ST || dn.L) setShowSubject(true)
    }

    setFormData(prev => ({ ...prev, ...updates }))
  }

  // SAN management
  const addSan = () => setSans(prev => [...prev, { type: 'dns', value: '' }])
  const removeSan = (idx) => setSans(prev => prev.filter((_, i) => i !== idx))
  const updateSan = (idx, field, val) => setSans(prev =>
    prev.map((s, i) => i === idx ? { ...s, [field]: val } : s)
  )

  // Suggested SAN types per cert_type
  const sanTypeOptions = useMemo(() => {
    const base = [
      { value: 'dns', label: t('certificates.sanDns') },
      { value: 'ip', label: t('certificates.sanIp') },
      { value: 'email', label: t('certificates.sanEmail') },
      { value: 'uri', label: t('certificates.sanUri') },
    ]
    return base
  }, [t])

  const sanPlaceholder = (type) => {
    const map = { dns: t('certificates.sanDnsPlaceholder'), ip: t('certificates.sanIpPlaceholder'), email: t('certificates.sanEmailPlaceholder'), uri: t('certificates.sanUriPlaceholder') }
    return map[type] || ''
  }

  // Auto-included SANs based on CN and cert type
  const autoSans = useMemo(() => {
    const items = []
    const cn = formData.cn.trim()
    if (!cn) return items
    const certType = formData.cert_type
    const isHostname = cn.includes('.') || cn.startsWith('*')
    const isEmail = cn.includes('@') && cn.split('@').pop()?.includes('.')

    if (['server', 'combined'].includes(certType) && isHostname) {
      items.push({ type: 'dns', value: cn })
    }
    if (['email', 'combined'].includes(certType) && isEmail) {
      items.push({ type: 'email', value: cn })
    }
    const subjectEmail = formData.email?.trim()
    if (['email', 'combined'].includes(certType) && subjectEmail && subjectEmail.includes('@')) {
      if (subjectEmail !== cn && !items.some(s => s.type === 'email' && s.value === subjectEmail)) {
        items.push({ type: 'email', value: subjectEmail })
      }
    }
    return items
  }, [formData.cn, formData.cert_type, formData.email])

  // Wildcard → suggest base domain
  const wildcardSuggestion = useMemo(() => {
    const cn = formData.cn.trim()
    if (!cn.startsWith('*.')) return null
    const baseDomain = cn.slice(2)
    if (!baseDomain || !baseDomain.includes('.')) return null
    if (sans.some(s => s.type === 'dns' && s.value === baseDomain)) return null
    return baseDomain
  }, [formData.cn, sans])

  const addWildcardBase = () => {
    if (!wildcardSuggestion) return
    setSans(prev => [...prev, { type: 'dns', value: wildcardSuggestion }])
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    // Build SAN arrays
    const san_dns = [], san_ip = [], san_email = [], san_uri = []
    sans.forEach(s => {
      const v = s.value.trim()
      if (!v) return
      if (s.type === 'dns') san_dns.push(v)
      else if (s.type === 'ip') san_ip.push(v)
      else if (s.type === 'email') san_email.push(v)
      else if (s.type === 'uri') san_uri.push(v)
    })

    // Calculate validity_days from date if in date mode
    let validity_days = parseInt(formData.validity_days, 10) || 365
    if (validityMode === 'date' && formData.expiry_date) {
      const expiry = new Date(formData.expiry_date)
      const now = new Date()
      validity_days = Math.max(1, Math.ceil((expiry - now) / (1000 * 60 * 60 * 24)))
    }

    const payload = {
      ca_id: formData.ca_id,
      cn: formData.cn,
      cert_type: formData.cert_type,
      description: formData.description || undefined,
      organization: formData.organization || undefined,
      organizational_unit: formData.organizational_unit || undefined,
      country: formData.country || undefined,
      state: formData.state || undefined,
      locality: formData.locality || undefined,
      email: formData.email || undefined,
      key_type: formData.key_type,
      key_size: formData.key_size,
      validity_days,
      ...(san_dns.length && { san_dns }),
      ...(san_ip.length && { san_ip }),
      ...(san_email.length && { san_email }),
      ...(san_uri.length && { san_uri }),
      ...(selectedTemplate && { template_id: parseInt(selectedTemplate) }),
      ...(formData.ocsp_must_staple && { ocsp_must_staple: true }),
    }
    onSubmit(payload)
  }

  const update = (field, val) => setFormData(prev => ({ ...prev, [field]: val }))

  // Cert type options
  const certTypeOptions = [
    { value: 'server', label: t('certificates.certTypeServer') },
    { value: 'client', label: t('certificates.certTypeClient') },
    { value: 'combined', label: t('certificates.certTypeCombined') },
    { value: 'code_signing', label: t('certificates.certTypeCodeSigning') },
    { value: 'email', label: t('certificates.certTypeEmail') },
  ]

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4 max-h-[70vh] overflow-y-auto">
      {/* Template selection */}
      {templates.length > 0 && (
        <Select
          label={t('certificates.templateOptional')}
          value={selectedTemplate}
          onChange={handleTemplateChange}
          placeholder={t('certificates.noTemplate')}
          options={[
            { value: '', label: t('certificates.noTemplate') },
            ...templates.map(tpl => ({ value: String(tpl.id), label: tpl.name }))
          ]}
        />
      )}

      {/* CA + Cert Type row */}
      <div className="grid grid-cols-2 gap-4">
        <Select
          label={t('common.certificateAuthority')}
          value={formData.ca_id}
          onChange={(val) => update('ca_id', val)}
          placeholder={t('certificates.selectCA')}
          options={cas.map(ca => ({ value: String(ca.id), label: ca.descr || ca.common_name }))}
        />
        <Select
          label={t('certificates.certType')}
          value={formData.cert_type}
          onChange={(val) => update('cert_type', val)}
          options={certTypeOptions}
        />
      </div>

      {/* CN + Description */}
      <Input 
        label={t('common.commonName')} 
        placeholder={formData.cert_type === 'email' ? t('certificates.sanEmailPlaceholder') : formData.cert_type === 'code_signing' ? 'John Doe' : 'example.com'}
        value={formData.cn}
        onChange={(e) => update('cn', e.target.value)}
        required
      />

      <Input
        label={t('common.description')}
        placeholder={t('certificates.descriptionPlaceholder')}
        value={formData.description}
        onChange={(e) => update('description', e.target.value)}
      />

      {/* Subject Details (collapsible) */}
      <div className="border border-border rounded-lg">
        <button
          type="button"
          onClick={() => setShowSubject(!showSubject)}
          className="w-full flex items-center justify-between p-3 text-sm font-medium text-text-secondary hover:text-text-primary transition-colors"
        >
          <span>{t('certificates.subjectDetails')}</span>
          {showSubject ? <CaretUp size={16} /> : <CaretDown size={16} />}
        </button>
        {showSubject && (
          <div className="px-3 pb-3 space-y-3 border-t border-border pt-3">
            <div className="grid grid-cols-3 gap-3">
              <Input
                label={t('common.country')}
                placeholder={t('common.countryPlaceholder')}
                value={formData.country}
                onChange={(e) => update('country', e.target.value)}
                maxLength={2}
              />
              <Input
                label={t('common.stateProvince')}
                placeholder={t('common.statePlaceholder')}
                value={formData.state}
                onChange={(e) => update('state', e.target.value)}
              />
              <Input
                label={t('common.locality')}
                placeholder="City"
                value={formData.locality}
                onChange={(e) => update('locality', e.target.value)}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Input
                label={t('common.organization')}
                placeholder={t('certificates.orgPlaceholder')}
                value={formData.organization}
                onChange={(e) => update('organization', e.target.value)}
              />
              <Input
                label={'OU'}
                placeholder={t('certificates.ouPlaceholder')}
                value={formData.organizational_unit}
                onChange={(e) => update('organizational_unit', e.target.value)}
              />
            </div>
            <Input
              label={t('common.email')}
              placeholder={t('certificates.emailPlaceholder')}
              value={formData.email}
              onChange={(e) => update('email', e.target.value)}
              type="email"
            />
          </div>
        )}
      </div>

      {/* Subject Alternative Names — structured */}
      <div className="space-y-2">
        <label className="block text-xs font-medium text-text-secondary">
          {t('common.subjectAltNames')}
        </label>

        {/* Auto-included SANs from CN */}
        {autoSans.length > 0 && (
          <div className="space-y-1">
            {autoSans.map((s, idx) => (
              <div key={`auto-${idx}`} className="flex items-center gap-2 px-2.5 py-1.5 bg-accent-primary-op10 border border-accent-primary-op20 rounded-md">
                <span className="text-[10px] font-medium uppercase tracking-wider text-accent-primary-op60 w-12">{s.type}</span>
                <span className="text-xs text-text-primary font-mono flex-1">{s.value}</span>
                <span className="text-[10px] text-accent-primary-op60 italic">{t('certificates.autoIncluded')}</span>
              </div>
            ))}
          </div>
        )}

        {/* Wildcard base domain suggestion */}
        {wildcardSuggestion && (
          <div className="flex items-center gap-2 px-2.5 py-1.5 bg-status-warning-op10 border border-status-warning-op20 rounded-md">
            <span className="text-[10px] font-medium uppercase tracking-wider status-warning-text w-12">dns</span>
            <span className="text-xs text-text-secondary font-mono flex-1">{wildcardSuggestion}</span>
            <Button type="button" variant="ghost" size="sm" onClick={addWildcardBase} className="text-[10px] status-warning-text !px-1.5 !py-0.5">
              <Plus size={10} /> {t('certificates.addBaseDomain')}
            </Button>
          </div>
        )}

        {/* Additional SANs label when auto-SANs present */}
        {autoSans.length > 0 && (
          <p className="text-[10px] text-text-tertiary">{t('certificates.additionalSans')}</p>
        )}

        <div className="space-y-2">
          {sans.map((san, idx) => (
            <div key={idx} className="flex items-center gap-2">
              <div className="w-28 flex-shrink-0">
                <Select
                  value={san.type}
                  onChange={(val) => updateSan(idx, 'type', val)}
                  options={sanTypeOptions}
                />
              </div>
              <div className="flex-1">
                <Input
                  placeholder={sanPlaceholder(san.type)}
                  value={san.value}
                  onChange={(e) => updateSan(idx, 'value', e.target.value)}
                />
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => removeSan(idx)}
                disabled={sans.length === 1 && !san.value}
                className="flex-shrink-0 text-text-tertiary hover:text-accent-danger"
              >
                <X size={14} />
              </Button>
            </div>
          ))}
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={addSan} className="text-xs">
          <Plus size={12} /> {t('certificates.addSan')}
        </Button>
      </div>

      {/* Key Settings */}
      <div className="grid grid-cols-2 gap-4">
        <Select
          label={t('common.keyType')}
          value={formData.key_type}
          onChange={(val) => {
            update('key_type', val)
            update('key_size', val === 'rsa' ? '2048' : '256')
          }}
          options={[
            { value: 'rsa', label: 'RSA' },
            { value: 'ecdsa', label: 'ECDSA' },
          ]}
        />
        <Select
          label={t('common.keySize')}
          value={formData.key_size}
          onChange={(val) => update('key_size', val)}
          options={formData.key_type === 'rsa'
            ? [{ value: '2048', label: '2048 bits' }, { value: '4096', label: '4096 bits' }]
            : [{ value: '256', label: 'P-256' }, { value: '384', label: 'P-384' }]
          }
        />
      </div>

      {/* Validity — days or calendar */}
      <div className="space-y-2">
        <div className="flex items-center gap-3">
          <label className="text-xs font-medium text-text-secondary">{t('common.validityPeriod')}</label>
          <div className="flex items-center gap-1 bg-bg-tertiary rounded-md p-0.5 border border-border">
            <button
              type="button"
              onClick={() => setValidityMode('days')}
              className={`px-2 py-0.5 text-xs rounded transition-colors ${validityMode === 'days' ? 'bg-bg-primary text-text-primary shadow-sm' : 'text-text-tertiary hover:text-text-secondary'}`}
            >
              {t('certificates.validityDays')}
            </button>
            <button
              type="button"
              onClick={() => setValidityMode('date')}
              className={`px-2 py-0.5 text-xs rounded transition-colors ${validityMode === 'date' ? 'bg-bg-primary text-text-primary shadow-sm' : 'text-text-tertiary hover:text-text-secondary'}`}
            >
              {t('certificates.validityDate')}
            </button>
          </div>
        </div>

        {validityMode === 'days' ? (
          <Input 
            type="number"
            placeholder={t('common.validityPlaceholder')}
            value={formData.validity_days}
            onChange={(e) => update('validity_days', e.target.value)}
            min="1"
            max={caExpiryDate ? Math.ceil((new Date(caExpiryDate) - new Date()) / (1000 * 60 * 60 * 24)) : undefined}
          />
        ) : (
          <DatePicker
            value={formData.expiry_date}
            onChange={(val) => update('expiry_date', val)}
            min={today}
            max={caExpiryDate || undefined}
          />
        )}
        {caExpiryDate && (
          <p className="text-xs text-text-tertiary">
            {t('certificates.maxValidityCa', { date: caExpiryDate })}
          </p>
        )}
      </div>

      {/* OCSP Must-Staple */}
      <div className="flex items-center gap-3 py-2">
        <input
          type="checkbox"
          id="ocsp_must_staple"
          checked={formData.ocsp_must_staple}
          onChange={(e) => update('ocsp_must_staple', e.target.checked)}
          className="w-4 h-4 rounded border-border accent-accent-primary"
        />
        <label htmlFor="ocsp_must_staple" className="text-sm text-text-secondary cursor-pointer">
          {t('certificates.ocspMustStaple')}
        </label>
      </div>

      {/* Actions */}
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
