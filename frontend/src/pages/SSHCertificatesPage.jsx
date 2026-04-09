/**
 * SSHCertificatesPage - SSH Certificate management
 * Pattern: ResponsiveLayout + ResponsiveDataTable + Modal actions
 *
 * CRUD + Issue page for SSH certificates (sign public key or generate key pair)
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Certificate, Key, Terminal, User, ShieldCheck,
  Plus, Trash, Warning, Download, Copy,
  Clock, CheckCircle, XCircle,
  CaretDown, CaretUp, Info
} from '@phosphor-icons/react'
import {
  ResponsiveLayout, ResponsiveDataTable, Badge, Button, Modal, Input, Select, Textarea,
  CompactSection, CompactGrid, CompactField, CompactHeader
} from '../components'
import { sshCertificatesService, sshCasService } from '../services'
import { useNotification, useMobile } from '../contexts'
import { usePermission, useWebSocket } from '../hooks'
import { formatDate } from '../lib/utils'

// ============= CONSTANTS =============

const VALIDITY_PRESETS = [
  { value: '1h', seconds: 3600 },
  { value: '8h', seconds: 28800 },
  { value: '24h', seconds: 86400 },
  { value: '7d', seconds: 604800 },
  { value: '30d', seconds: 2592000 },
  { value: '90d', seconds: 7776000 },
  { value: '365d', seconds: 31536000 },
  { value: 'custom', seconds: 0 },
]

const KEY_ALGORITHMS = [
  { value: 'ed25519', label: 'Ed25519' },
  { value: 'rsa', label: 'RSA (4096)' },
  { value: 'ecdsa-p256', label: 'ECDSA P-256' },
]

const DEFAULT_EXTENSIONS = [
  'permit-pty',
  'permit-agent-forwarding',
  'permit-X11-forwarding',
  'permit-port-forwarding',
  'permit-user-rc',
]

// ============= STATUS HELPER =============

function getStatus(cert, t) {
  if (cert.revoked) return { key: 'revoked', label: t('sshCertificates.statusRevoked'), variant: 'danger', icon: XCircle }
  const now = Date.now() / 1000
  if (cert.valid_to && now > cert.valid_to) return { key: 'expired', label: t('sshCertificates.statusExpired'), variant: 'warning', icon: Clock }
  return { key: 'valid', label: t('sshCertificates.statusValid'), variant: 'success', icon: CheckCircle }
}

// ============= MAIN COMPONENT =============

export default function SSHCertificatesPage() {
  const { t } = useTranslation()
  const { isMobile } = useMobile()
  const navigate = useNavigate()
  const { id: urlCertId } = useParams()
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canWrite, canDelete } = usePermission()
  const { muteToasts } = useWebSocket()

  // Data
  const [certificates, setCertificates] = useState([])
  const [cas, setCas] = useState([])
  const [loading, setLoading] = useState(true)
  const [certStats, setCertStats] = useState({ valid: 0, expired: 0, revoked: 0, total: 0 })

  // Selection
  const [selectedCert, setSelectedCert] = useState(null)

  // Modals
  const [showIssueModal, setShowIssueModal] = useState(false)
  const [showRevokeModal, setShowRevokeModal] = useState(false)
  const [revokingCert, setRevokingCert] = useState(null)

  // Pagination & Sort
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  const [total, setTotal] = useState(0)
  const [sortBy, setSortBy] = useState('id')
  const [sortOrder, setSortOrder] = useState('desc')

  // Filters
  const [filterStatus, setFilterStatus] = useState('')
  const [filterType, setFilterType] = useState('')
  const [filterCA, setFilterCA] = useState('')

  // ============= DATA LOADING =============

  useEffect(() => {
    loadData()
  }, [page, perPage, sortBy, sortOrder, filterStatus, filterType, filterCA])

  const loadData = async () => {
    try {
      setLoading(true)
      const params = {
        page,
        per_page: perPage,
        sort_by: sortBy,
        sort_order: sortOrder,
      }
      if (filterStatus) params.status = filterStatus
      if (filterType) params.type = filterType
      if (filterCA) params.ca_id = filterCA

      const [certsRes, casRes, statsRes] = await Promise.all([
        sshCertificatesService.getAll(params),
        sshCasService.getAll(),
        sshCertificatesService.getStats(),
      ])

      setCertificates(certsRes.data || [])
      setCas(casRes.data || [])
      setCertStats(statsRes.data || { valid: 0, expired: 0, revoked: 0, total: 0 })
      setTotal(certsRes.meta?.total || certsRes.pagination?.total || (certsRes.data || []).length)
    } catch (error) {
      showError(error.message || t('messages.errors.loadFailed.sshCertificates'))
    } finally {
      setLoading(false)
    }
  }

  // Reload on external data changes
  useEffect(() => {
    const handler = (e) => {
      if (e.detail?.type === 'ssh-certificate') loadData()
    }
    window.addEventListener('ucm:data-changed', handler)
    return () => window.removeEventListener('ucm:data-changed', handler)
  }, [])

  // Deep-link URL handling
  useEffect(() => {
    if (urlCertId && !loading && certificates.length > 0) {
      const id = parseInt(urlCertId, 10)
      if (!isNaN(id)) {
        const found = certificates.find(c => c.id === id)
        if (found) setSelectedCert(found)
        navigate('/ssh-certificates', { replace: true })
      }
    }
  }, [urlCertId, loading, certificates.length])

  // ============= STATS =============

  const stats = useMemo(() => [
    { icon: CheckCircle, label: t('sshCertificates.stats.active'), value: certStats.valid || 0, variant: 'success', filterValue: 'valid' },
    { icon: Clock, label: t('sshCertificates.stats.expired'), value: certStats.expired || 0, variant: 'warning', filterValue: 'expired' },
    { icon: XCircle, label: t('sshCertificates.stats.revoked'), value: certStats.revoked || 0, variant: 'danger', filterValue: 'revoked' },
    { icon: Certificate, label: t('sshCertificates.stats.total'), value: certStats.total || 0, variant: 'primary', filterValue: '' },
  ], [certStats, t])

  const handleStatClick = useCallback((filterValue) => {
    setPage(1)
    setFilterStatus(filterValue === filterStatus ? '' : filterValue)
  }, [filterStatus])

  // ============= ACTIONS =============

  const handleSelectCert = useCallback(async (cert) => {
    try {
      const res = await sshCertificatesService.getById(cert.id)
      setSelectedCert(res.data || cert)
    } catch {
      setSelectedCert(cert)
    }
  }, [])

  const handleRevoke = useCallback((cert) => {
    setRevokingCert(cert)
    setShowRevokeModal(true)
  }, [])

  const handleRevokeSubmit = async (reason) => {
    if (!revokingCert) return
    try {
      muteToasts()
      await sshCertificatesService.revoke(revokingCert.id, reason)
      showSuccess(t('messages.success.create.sshCertificate').replace('issued', 'revoked'))
      setShowRevokeModal(false)
      setRevokingCert(null)
      if (selectedCert?.id === revokingCert.id) setSelectedCert(null)
      loadData()
    } catch (error) {
      showError(error.message || t('common.operationFailed'))
    }
  }

  const handleDelete = async (cert) => {
    const confirmed = await showConfirm(t('sshCertificates.deleteConfirm'), {
      title: t('sshCertificates.deleteCertificate'),
      confirmText: t('common.delete'),
      variant: 'danger',
    })
    if (!confirmed) return
    try {
      muteToasts()
      await sshCertificatesService.delete(cert.id)
      showSuccess(t('messages.success.delete.sshCertificate'))
      if (selectedCert?.id === cert.id) setSelectedCert(null)
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.deleteFailed.sshCertificate'))
    }
  }

  const handleExport = async (cert) => {
    try {
      const res = await sshCertificatesService.export(cert.id)
      const text = typeof res === 'string' ? res : (res.data?.certificate || res.data || JSON.stringify(res))
      const blob = new Blob([text], { type: 'text/plain' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${cert.key_id || t('sshCertificates.export.filename')}-cert.pub`
      a.click()
      URL.revokeObjectURL(url)
      showSuccess(t('sshCertificates.export.success'))
    } catch (error) {
      showError(error.message || t('common.operationFailed'))
    }
  }

  const handleCopyText = useCallback((text) => {
    navigator.clipboard.writeText(text).then(() => {
      showSuccess(t('common.copy') + ' ✓')
    }).catch(() => {})
  }, [showSuccess, t])

  const handleIssueSubmit = async (data) => {
    try {
      muteToasts()
      let res
      if (data.mode === 'generate') {
        res = await sshCertificatesService.generate(data)
      } else {
        res = await sshCertificatesService.sign(data)
      }
      showSuccess(t('messages.success.create.sshCertificate'))
      setShowIssueModal(false)
      loadData()
      return res
    } catch (error) {
      showError(error.message || t('common.operationFailed'))
      throw error
    }
  }

  // ============= SORT HANDLER =============

  const handleSortChange = useCallback((newSort) => {
    setPage(1)
    if (newSort) {
      setSortBy(newSort.key)
      setSortOrder(newSort.direction)
    } else {
      setSortBy('id')
      setSortOrder('desc')
    }
  }, [])

  // ============= FILTER PRESETS =============

  const handleApplyFilterPreset = useCallback((filters) => {
    setPage(1)
    setFilterStatus(filters.status || '')
    setFilterType(filters.type || '')
    setFilterCA(filters.ca || '')
  }, [])

  // ============= COLUMNS =============

  const columns = useMemo(() => [
    {
      key: 'key_id',
      header: t('sshCertificates.keyId'),
      priority: 1,
      sortable: true,
      render: (val, row) => {
        const status = getStatus(row, t)
        return (
          <div className="flex items-center gap-2">
            <div className={`w-6 h-6 rounded-lg flex items-center justify-center shrink-0 ${
              row.cert_type === 'host' ? 'icon-bg-violet' : 'icon-bg-blue'
            }`}>
              {row.cert_type === 'host'
                ? <Terminal size={14} weight="duotone" />
                : <User size={14} weight="duotone" />}
            </div>
            <span className="font-medium truncate">{val || t('common.unnamed')}</span>
          </div>
        )
      },
      mobileRender: (val, row) => {
        const status = getStatus(row, t)
        return (
          <div className="flex items-center justify-between gap-2 w-full">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <div className={`w-6 h-6 rounded-lg flex items-center justify-center shrink-0 ${
                row.cert_type === 'host' ? 'icon-bg-violet' : 'icon-bg-blue'
              }`}>
                {row.cert_type === 'host'
                  ? <Terminal size={14} weight="duotone" />
                  : <User size={14} weight="duotone" />}
              </div>
              <span className="font-medium truncate">{val || t('common.unnamed')}</span>
            </div>
            <Badge variant={status.variant} size="sm" dot>
              {status.label}
            </Badge>
          </div>
        )
      },
    },
    {
      key: 'cert_type',
      header: t('sshCertificates.certType'),
      priority: 2,
      sortable: true,
      hideOnMobile: true,
      render: (val) => (
        <Badge
          variant={val === 'host' ? 'violet' : 'cyan'}
          size="sm"
          icon={val === 'host' ? Terminal : User}
        >
          {val === 'host' ? t('sshCertificates.typeHost') : t('sshCertificates.typeUser')}
        </Badge>
      ),
    },
    {
      key: 'principals',
      header: t('sshCertificates.principals'),
      priority: 3,
      hideOnMobile: true,
      render: (val) => {
        const principals = Array.isArray(val) ? val : (val ? String(val).split(',') : [])
        if (principals.length === 0) return <span className="text-xs text-text-tertiary">—</span>
        return (
          <div className="flex items-center gap-1">
            <span className="text-xs text-text-secondary truncate max-w-[160px]">
              {principals.slice(0, 2).join(', ')}
            </span>
            {principals.length > 2 && (
              <Badge variant="secondary" size="sm">+{principals.length - 2}</Badge>
            )}
          </div>
        )
      },
    },
    {
      key: 'valid_to',
      header: t('sshCertificates.validTo'),
      priority: 4,
      sortable: true,
      hideOnMobile: true,
      render: (val, row) => {
        const status = getStatus(row, t)
        return (
          <span className={`text-xs whitespace-nowrap ${
            status.key === 'expired' ? 'text-status-warning' : 'text-text-secondary'
          }`}>
            {val ? formatDate(val) : '—'}
          </span>
        )
      },
    },
    {
      key: 'status_display',
      header: t('common.status'),
      priority: 2,
      sortable: false,
      hideOnMobile: true,
      render: (_, row) => {
        const status = getStatus(row, t)
        const Icon = status.icon
        return (
          <Badge variant={status.variant} size="sm" icon={Icon} dot pulse={status.key === 'valid'}>
            {status.label}
          </Badge>
        )
      },
    },
    {
      key: 'ca_name',
      header: t('sshCertificates.caName'),
      priority: 5,
      hideOnMobile: true,
      render: (val) => (
        <span className="text-xs text-text-secondary truncate">
          {val || '—'}
        </span>
      ),
    },
  ], [t])

  // ============= ROW ACTIONS =============

  const rowActions = useCallback((row) => {
    const status = getStatus(row, t)
    return [
      { label: t('common.details'), icon: Info, onClick: () => handleSelectCert(row) },
      { label: t('common.export'), icon: Download, onClick: () => handleExport(row) },
      ...(canWrite('ssh') && status.key === 'valid' ? [
        { label: t('sshCertificates.revokeCertificate'), icon: Warning, variant: 'danger', onClick: () => handleRevoke(row) },
      ] : []),
      ...(canDelete('ssh') ? [
        { label: t('common.delete'), icon: Trash, variant: 'danger', onClick: () => handleDelete(row) },
      ] : []),
    ]
  }, [canWrite, canDelete, t])

  // ============= DETAIL PANEL =============

  const detailContent = selectedCert && (
    <div className="p-3 space-y-4">
      <CompactHeader
        icon={selectedCert.cert_type === 'host' ? Terminal : User}
        iconClass={selectedCert.cert_type === 'host' ? 'icon-bg-violet' : 'icon-bg-blue'}
        title={selectedCert.key_id || t('common.unnamed')}
        subtitle={selectedCert.ca_name || t('sshCertificates.caName')}
        badge={(() => {
          const status = getStatus(selectedCert, t)
          return <Badge variant={status.variant} size="sm" icon={status.icon}>{status.label}</Badge>
        })()}
      />

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        <Button type="button" size="sm" variant="secondary" onClick={() => handleExport(selectedCert)}>
          <Download size={14} /> {t('common.export')}
        </Button>
        {canWrite('ssh') && getStatus(selectedCert, t).key === 'valid' && (
          <Button type="button" size="sm" variant="danger" onClick={() => handleRevoke(selectedCert)}>
            <Warning size={14} /> {t('sshCertificates.revokeCertificate')}
          </Button>
        )}
        {canDelete('ssh') && (
          <Button type="button" size="sm" variant="danger" onClick={() => handleDelete(selectedCert)}>
            <Trash size={14} /> {t('common.delete')}
          </Button>
        )}
      </div>

      {/* Certificate Information */}
      <CompactSection title={t('sshCertificates.certInformation')} icon={Certificate}>
        <CompactGrid columns={2}>
          <CompactField autoIcon="type" label={t('sshCertificates.certType')} value={
            selectedCert.cert_type === 'host' ? t('sshCertificates.typeHost') : t('sshCertificates.typeUser')
          } />
          <CompactField autoIcon="serial" label={t('sshCertificates.serial')} value={selectedCert.serial || '—'} mono />
          <CompactField autoIcon="key" label={t('sshCertificates.keyId')} value={selectedCert.key_id || '—'} />
          <CompactField autoIcon="keyType" label={t('common.keyType')} value={selectedCert.key_type || '—'} />
        </CompactGrid>
        {selectedCert.fingerprint && (
          <div className="mt-2">
            <div className="text-xs text-text-tertiary mb-0.5">{t('sshCertificates.fingerprint')}</div>
            <div
              className="font-mono text-2xs text-text-secondary break-all bg-tertiary-op50 p-1.5 rounded cursor-pointer hover:bg-tertiary-op80 transition-colors"
              onClick={() => handleCopyText(selectedCert.fingerprint)}
              title={t('common.copy')}
            >
              {selectedCert.fingerprint}
            </div>
          </div>
        )}
      </CompactSection>

      {/* Validity */}
      <CompactSection title={t('sshCertificates.validityInfo')} icon={Clock}>
        <CompactGrid columns={2}>
          <CompactField
            autoIcon="validFrom"
            label={t('sshCertificates.validFrom')}
            value={selectedCert.valid_from ? formatDate(selectedCert.valid_from) : '—'}
          />
          <CompactField
            autoIcon="validUntil"
            label={t('sshCertificates.validTo')}
            value={selectedCert.valid_to ? formatDate(selectedCert.valid_to) : '—'}
          />
        </CompactGrid>
      </CompactSection>

      {/* CA Information */}
      <CompactSection title={t('sshCertificates.caInfo')} icon={ShieldCheck}>
        <CompactGrid columns={1}>
          <CompactField autoIcon="ca" label={t('sshCertificates.caName')} value={selectedCert.ca_name || '—'} />
          {selectedCert.ca_fingerprint && (
            <CompactField autoIcon="fingerprint" label={t('sshCertificates.caFingerprint')} value={selectedCert.ca_fingerprint} mono />
          )}
        </CompactGrid>
      </CompactSection>

      {/* Principals */}
      {(() => {
        const principals = Array.isArray(selectedCert.principals)
          ? selectedCert.principals
          : (selectedCert.principals ? String(selectedCert.principals).split(',') : [])
        if (principals.length === 0) return null
        return (
          <CompactSection title={t('sshCertificates.principals')} icon={User}>
            <div className="flex flex-wrap gap-1">
              {principals.map(p => (
                <Badge key={p} variant="cyan" size="sm">{p.trim()}</Badge>
              ))}
            </div>
          </CompactSection>
        )
      })()}

      {/* Extensions */}
      {(() => {
        const extensions = Array.isArray(selectedCert.extensions)
          ? selectedCert.extensions
          : (selectedCert.extensions ? Object.keys(selectedCert.extensions) : [])
        if (extensions.length === 0) return null
        return (
          <CompactSection title={t('sshCertificates.extensions')} icon={ShieldCheck} collapsible defaultOpen={false}>
            <div className="flex flex-wrap gap-1">
              {extensions.map(ext => (
                <Badge key={ext} variant="emerald" size="sm">{ext}</Badge>
              ))}
            </div>
          </CompactSection>
        )
      })()}

      {/* Critical Options */}
      {(() => {
        const opts = selectedCert.critical_options
        if (!opts || (typeof opts === 'object' && Object.keys(opts).length === 0)) return null
        const entries = typeof opts === 'object' ? Object.entries(opts) : []
        if (entries.length === 0) return null
        return (
          <CompactSection title={t('sshCertificates.criticalOptions')} icon={Warning} collapsible defaultOpen={false}>
            <CompactGrid columns={1}>
              {entries.map(([key, value]) => (
                <CompactField key={key} autoIcon="config" label={key} value={String(value)} mono />
              ))}
            </CompactGrid>
          </CompactSection>
        )
      })()}

      {/* Certificate Text */}
      {selectedCert.certificate && (
        <CompactSection title={t('sshCertificates.certificateText')} icon={Key} collapsible defaultOpen={false}>
          <div className="relative">
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="absolute top-1 right-1 z-10"
              onClick={() => handleCopyText(selectedCert.certificate)}
            >
              <Copy size={12} />
            </Button>
            <pre className="font-mono text-2xs text-text-secondary break-all bg-tertiary-op50 p-2 rounded overflow-x-auto max-h-48 whitespace-pre-wrap">
              {selectedCert.certificate}
            </pre>
          </div>
        </CompactSection>
      )}
    </div>
  )

  // ============= RENDER =============

  return (
    <>
      <ResponsiveLayout
        title={t('sshCertificates.title')}
        subtitle={t('sshCertificates.subtitle', { count: total })}
        icon={Certificate}
        stats={stats}
        onStatClick={handleStatClick}
        activeStatFilter={filterStatus}
        helpPageKey="sshCertificates"
        splitView={true}
        splitEmptyContent={
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
              <Certificate size={24} className="text-text-tertiary" weight="duotone" />
            </div>
            <p className="text-sm text-text-secondary">{t('sshCertificates.noData')}</p>
          </div>
        }
        slideOverOpen={!!selectedCert}
        slideOverTitle={selectedCert?.key_id || t('common.details')}
        slideOverContent={detailContent}
        slideOverWidth="lg"
        onSlideOverClose={() => setSelectedCert(null)}
      >
        <ResponsiveDataTable
          data={certificates}
          columns={columns}
          loading={loading}
          onRowClick={handleSelectCert}
          selectedId={selectedCert?.id}
          searchable
          searchPlaceholder={`${t('common.search')} ${t('sshCertificates.title').toLowerCase()}...`}
          searchKeys={['key_id', 'principals', 'ca_name', 'serial', 'fingerprint']}
          toolbarFilters={[
            {
              key: 'type',
              value: filterType,
              onChange: (v) => { setFilterType(v); setPage(1) },
              placeholder: t('common.allTypes'),
              options: [
                { value: 'user', label: t('sshCertificates.typeUser') },
                { value: 'host', label: t('sshCertificates.typeHost') },
              ],
            },
            {
              key: 'status',
              value: filterStatus,
              onChange: (v) => { setFilterStatus(v); setPage(1) },
              placeholder: t('common.allStatus'),
              options: [
                { value: 'valid', label: t('sshCertificates.statusValid') },
                { value: 'expired', label: t('sshCertificates.statusExpired') },
                { value: 'revoked', label: t('sshCertificates.statusRevoked') },
              ],
            },
            ...(cas.length > 0 ? [{
              key: 'ca',
              value: filterCA,
              onChange: (v) => { setFilterCA(v); setPage(1) },
              placeholder: t('common.allCAs'),
              options: cas.map(ca => ({ value: String(ca.id), label: ca.name })),
            }] : []),
          ]}
          toolbarActions={canWrite('ssh') && (
            isMobile ? (
              <Button type="button" size="lg" onClick={() => setShowIssueModal(true)} className="w-11 h-11 p-0">
                <Plus size={22} weight="bold" />
              </Button>
            ) : (
              <Button type="button" size="sm" onClick={() => setShowIssueModal(true)}>
                <Plus size={14} weight="bold" />
                {t('sshCertificates.issueCertificate')}
              </Button>
            )
          )}
          sortable
          defaultSort={{ key: 'id', direction: 'desc' }}
          onSortChange={handleSortChange}
          rowActions={rowActions}
          pagination={{
            page,
            total,
            perPage,
            onChange: setPage,
            onPerPageChange: (v) => { setPerPage(v); setPage(1) },
          }}
          emptyIcon={Certificate}
          emptyTitle={t('sshCertificates.noData')}
          emptyDescription={t('sshCertificates.noDataDescription')}
          emptyAction={canWrite('ssh') && (
            <Button type="button" onClick={() => setShowIssueModal(true)}>
              <Plus size={16} /> {t('sshCertificates.issueCertificate')}
            </Button>
          )}
          onApplyFilterPreset={handleApplyFilterPreset}
        />
      </ResponsiveLayout>

      {/* Issue Certificate Modal */}
      <Modal
        open={showIssueModal}
        onOpenChange={(open) => { setShowIssueModal(open) }}
        title={t('sshCertificates.issueCertificate')}
        size="xl"
      >
        <IssueCertificateForm
          cas={cas}
          onSubmit={handleIssueSubmit}
          onCancel={() => setShowIssueModal(false)}
        />
      </Modal>

      {/* Revoke Certificate Modal */}
      <Modal
        open={showRevokeModal}
        onOpenChange={(open) => { setShowRevokeModal(open); if (!open) setRevokingCert(null) }}
        title={t('sshCertificates.revokeCertificate')}
        size="md"
      >
        <RevokeCertificateForm
          cert={revokingCert}
          onSubmit={handleRevokeSubmit}
          onCancel={() => { setShowRevokeModal(false); setRevokingCert(null) }}
        />
      </Modal>
    </>
  )
}

// ============= ISSUE CERTIFICATE FORM =============

function IssueCertificateForm({ cas, onSubmit, onCancel }) {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)

  // Form state
  const [mode, setMode] = useState('sign')
  const [caId, setCaId] = useState('')
  const [certType, setCertType] = useState('user')
  const [keyId, setKeyId] = useState('')
  const [publicKey, setPublicKey] = useState('')
  const [keyAlgorithm, setKeyAlgorithm] = useState('ed25519')
  const [principalsText, setPrincipalsText] = useState('')
  const [validityPreset, setValidityPreset] = useState('24h')
  const [customFrom, setCustomFrom] = useState('')
  const [customTo, setCustomTo] = useState('')
  const [extensions, setExtensions] = useState([...DEFAULT_EXTENSIONS])
  const [showCriticalOptions, setShowCriticalOptions] = useState(false)
  const [forceCommand, setForceCommand] = useState('')
  const [sourceAddress, setSourceAddress] = useState('')

  // Set first CA as default
  useEffect(() => {
    if (cas.length > 0 && !caId) {
      setCaId(String(cas[0].id))
    }
  }, [cas])

  const toggleExtension = (ext) => {
    setExtensions(prev =>
      prev.includes(ext) ? prev.filter(e => e !== ext) : [...prev, ext]
    )
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!keyId.trim() || !caId) return
    if (mode === 'sign' && !publicKey.trim()) return

    setLoading(true)
    try {
      const principals = principalsText.split(',').map(p => p.trim()).filter(Boolean)

      const data = {
        mode,
        ca_id: parseInt(caId, 10),
        cert_type: certType,
        key_id: keyId.trim(),
        principals,
        validity_preset: validityPreset,
        extensions: certType === 'user' ? extensions : [],
      }

      if (mode === 'sign') {
        data.public_key = publicKey.trim()
      } else {
        data.key_type = keyAlgorithm
      }

      if (validityPreset === 'custom') {
        if (customFrom) data.valid_from = customFrom
        if (customTo) data.valid_to = customTo
      }

      const criticalOptions = {}
      if (forceCommand.trim()) criticalOptions['force-command'] = forceCommand.trim()
      if (sourceAddress.trim()) criticalOptions['source-address'] = sourceAddress.trim()
      if (Object.keys(criticalOptions).length > 0) {
        data.critical_options = criticalOptions
      }

      const res = await onSubmit(data)
      if (mode === 'generate' && res?.data) {
        setResult(res.data)
      } else {
        onCancel()
      }
    } catch {
      // error handled by parent
    } finally {
      setLoading(false)
    }
  }

  // Show generated result after successful key pair generation
  if (result) {
    return <GeneratedResultView result={result} onClose={onCancel} />
  }

  const caOptions = cas.map(ca => ({ value: String(ca.id), label: ca.name }))

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4 max-h-[70vh] overflow-y-auto">
      {/* Issue Mode */}
      <div>
        <label className="block text-xs font-medium text-text-primary mb-2">
          {t('sshCertificates.issueMode')}
        </label>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setMode('sign')}
            className={`flex-1 px-3 py-2 text-sm rounded-lg border transition-colors ${
              mode === 'sign'
                ? 'border-accent-primary bg-accent-primary-op10 text-accent-primary font-medium'
                : 'border-border bg-bg-secondary text-text-secondary hover:bg-bg-tertiary'
            }`}
          >
            <Key size={16} className="inline-block mr-1.5 -mt-0.5" />
            {t('sshCertificates.signPublicKey')}
          </button>
          <button
            type="button"
            onClick={() => setMode('generate')}
            className={`flex-1 px-3 py-2 text-sm rounded-lg border transition-colors ${
              mode === 'generate'
                ? 'border-accent-primary bg-accent-primary-op10 text-accent-primary font-medium'
                : 'border-border bg-bg-secondary text-text-secondary hover:bg-bg-tertiary'
            }`}
          >
            <Certificate size={16} className="inline-block mr-1.5 -mt-0.5" />
            {t('sshCertificates.generateKeyPair')}
          </button>
        </div>
      </div>

      {/* SSH CA Selection */}
      <div>
        <label className="block text-xs font-medium text-text-primary mb-1">
          {t('sshCertificates.selectCa')} <span className="text-status-danger">*</span>
        </label>
        <Select
          value={caId}
          onChange={setCaId}
          options={caOptions}
          placeholder={t('sshCertificates.selectCa')}
        />
      </div>

      {/* Certificate Type */}
      <div>
        <label className="block text-xs font-medium text-text-primary mb-1">
          {t('sshCertificates.certType')} <span className="text-status-danger">*</span>
        </label>
        <Select
          value={certType}
          onChange={setCertType}
          options={[
            { value: 'user', label: t('sshCertificates.typeUser') },
            { value: 'host', label: t('sshCertificates.typeHost') },
          ]}
        />
      </div>

      {/* Key ID */}
      <div>
        <label className="block text-xs font-medium text-text-primary mb-1">
          {t('sshCertificates.keyId')} <span className="text-status-danger">*</span>
        </label>
        <Input
          value={keyId}
          onChange={(e) => setKeyId(e.target.value)}
          placeholder={t('sshCertificates.modal.keyIdPlaceholder')}
          required
        />
      </div>

      {/* Public Key (Sign mode) */}
      {mode === 'sign' && (
        <div>
          <label className="block text-xs font-medium text-text-primary mb-1">
            {t('sshCertificates.publicKey')} <span className="text-status-danger">*</span>
          </label>
          <Textarea
            value={publicKey}
            onChange={(e) => setPublicKey(e.target.value)}
            placeholder={t('sshCertificates.modal.publicKeyPlaceholder')}
            rows={3}
            className="font-mono text-xs"
            required
          />
        </div>
      )}

      {/* Key Algorithm (Generate mode) */}
      {mode === 'generate' && (
        <div>
          <label className="block text-xs font-medium text-text-primary mb-1">
            {t('common.keyAlgorithm')}
          </label>
          <Select
            value={keyAlgorithm}
            onChange={setKeyAlgorithm}
            options={KEY_ALGORITHMS}
          />
        </div>
      )}

      {/* Principals */}
      <div>
        <label className="block text-xs font-medium text-text-primary mb-1">
          {t('sshCertificates.principals')}
        </label>
        <Input
          value={principalsText}
          onChange={(e) => setPrincipalsText(e.target.value)}
          placeholder={t('sshCertificates.modal.principalsPlaceholder')}
        />
      </div>

      {/* Validity Preset */}
      <div>
        <label className="block text-xs font-medium text-text-primary mb-1">
          {t('sshCertificates.validityPreset')}
        </label>
        <Select
          value={validityPreset}
          onChange={setValidityPreset}
          options={VALIDITY_PRESETS.map(p => ({
            value: p.value,
            label: t(`sshCertificates.presets.${p.value}`),
          }))}
        />
      </div>

      {/* Custom Validity */}
      {validityPreset === 'custom' && (
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-text-primary mb-1">
              {t('sshCertificates.validFrom')}
            </label>
            <Input
              type="datetime-local"
              value={customFrom}
              onChange={(e) => setCustomFrom(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-text-primary mb-1">
              {t('sshCertificates.validTo')}
            </label>
            <Input
              type="datetime-local"
              value={customTo}
              onChange={(e) => setCustomTo(e.target.value)}
            />
          </div>
        </div>
      )}

      {/* Extensions (user certs only) */}
      {certType === 'user' && (
        <div>
          <label className="block text-xs font-medium text-text-primary mb-2">
            {t('sshCertificates.extensions')}
          </label>
          <div className="space-y-1.5">
            {DEFAULT_EXTENSIONS.map(ext => (
              <label key={ext} className="flex items-center gap-2 text-sm text-text-primary cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={extensions.includes(ext)}
                  onChange={() => toggleExtension(ext)}
                  className="rounded border-border"
                />
                <span className="font-mono text-xs">{ext}</span>
              </label>
            ))}
          </div>
        </div>
      )}

      {/* Critical Options (collapsible) */}
      <div>
        <button
          type="button"
          onClick={() => setShowCriticalOptions(!showCriticalOptions)}
          className="flex items-center gap-1.5 text-xs font-medium text-text-secondary hover:text-text-primary transition-colors"
        >
          {showCriticalOptions ? <CaretUp size={12} /> : <CaretDown size={12} />}
          {t('sshCertificates.criticalOptions')}
        </button>
        {showCriticalOptions && (
          <div className="mt-2 space-y-3 pl-4 border-l-2 border-border">
            <div>
              <label className="block text-xs font-medium text-text-primary mb-1">
                {t('sshCertificates.forceCommand')}
              </label>
              <Input
                value={forceCommand}
                onChange={(e) => setForceCommand(e.target.value)}
                placeholder="e.g. /usr/bin/rsync"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-text-primary mb-1">
                {t('sshCertificates.sourceAddress')}
              </label>
              <Input
                value={sourceAddress}
                onChange={(e) => setSourceAddress(e.target.value)}
                placeholder="e.g. 10.0.0.0/8,192.168.1.0/24"
              />
            </div>
          </div>
        )}
      </div>

      {/* Submit */}
      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button type="submit" disabled={loading || !keyId.trim() || !caId || (mode === 'sign' && !publicKey.trim())}>
          {loading ? (
            <span className="flex items-center gap-2">
              <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              {t('sshCertificates.issueCertificate')}
            </span>
          ) : (
            <>
              <Certificate size={14} />
              {t('sshCertificates.issueCertificate')}
            </>
          )}
        </Button>
      </div>
    </form>
  )
}

// ============= GENERATED RESULT VIEW =============

function GeneratedResultView({ result, onClose }) {
  const { t } = useTranslation()
  const { showSuccess } = useNotification()

  const handleCopy = (text) => {
    navigator.clipboard.writeText(text).then(() => {
      showSuccess(t('common.copy') + ' ✓')
    }).catch(() => {})
  }

  return (
    <div className="p-4 space-y-4 max-h-[70vh] overflow-y-auto">
      {/* Warning about private key */}
      <div className="p-3 rounded-lg bg-status-warning-op10 border border-status-warning-op30">
        <div className="flex items-center gap-2 text-status-warning text-xs font-medium">
          <Warning size={16} />
          {t('sshCertificates.privateKeyWarning')}
        </div>
      </div>

      {/* Private Key */}
      {result.private_key && (
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs font-medium text-text-primary">
              {t('sshCertificates.generatedPrivateKey')}
            </label>
            <Button type="button" size="sm" variant="ghost" onClick={() => handleCopy(result.private_key)}>
              <Copy size={12} /> {t('common.copy')}
            </Button>
          </div>
          <pre className="font-mono text-2xs text-text-secondary bg-tertiary-op50 p-2 rounded overflow-x-auto max-h-40 whitespace-pre-wrap break-all">
            {result.private_key}
          </pre>
        </div>
      )}

      {/* Certificate */}
      {result.certificate && (
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs font-medium text-text-primary">
              {t('sshCertificates.generatedCertificate')}
            </label>
            <Button type="button" size="sm" variant="ghost" onClick={() => handleCopy(result.certificate)}>
              <Copy size={12} /> {t('common.copy')}
            </Button>
          </div>
          <pre className="font-mono text-2xs text-text-secondary bg-tertiary-op50 p-2 rounded overflow-x-auto max-h-40 whitespace-pre-wrap break-all">
            {result.certificate}
          </pre>
        </div>
      )}

      {/* Public Key */}
      {result.public_key && (
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs font-medium text-text-primary">
              {t('sshCertificates.publicKey')}
            </label>
            <Button type="button" size="sm" variant="ghost" onClick={() => handleCopy(result.public_key)}>
              <Copy size={12} /> {t('common.copy')}
            </Button>
          </div>
          <pre className="font-mono text-2xs text-text-secondary bg-tertiary-op50 p-2 rounded overflow-x-auto max-h-20 whitespace-pre-wrap break-all">
            {result.public_key}
          </pre>
        </div>
      )}

      <div className="flex justify-end pt-4 border-t border-border">
        <Button type="button" onClick={onClose}>
          {t('common.close')}
        </Button>
      </div>
    </div>
  )
}

// ============= REVOKE CERTIFICATE FORM =============

function RevokeCertificateForm({ cert, onSubmit, onCancel }) {
  const { t } = useTranslation()
  const [reason, setReason] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      await onSubmit(reason)
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
      <div className="p-3 rounded-lg bg-status-danger-op10 border border-status-danger-op30">
        <div className="flex items-center gap-2 text-status-danger text-xs font-medium">
          <Warning size={16} />
          {t('sshCertificates.revokeConfirm')}
        </div>
      </div>

      {cert && (
        <div className="text-sm text-text-secondary">
          <span className="font-medium text-text-primary">{t('sshCertificates.keyId')}:</span>{' '}
          <span className="font-mono">{cert.key_id}</span>
        </div>
      )}

      <div>
        <label className="block text-xs font-medium text-text-primary mb-1">
          {t('sshCertificates.revokeReason')}
        </label>
        <Textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder={t('sshCertificates.revokeReasonPlaceholder')}
          rows={3}
        />
      </div>

      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button type="submit" variant="danger" disabled={loading}>
          {loading ? (
            <span className="flex items-center gap-2">
              <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              {t('sshCertificates.revokeCertificate')}
            </span>
          ) : (
            <>
              <Warning size={14} />
              {t('sshCertificates.revokeCertificate')}
            </>
          )}
        </Button>
      </div>
    </form>
  )
}
