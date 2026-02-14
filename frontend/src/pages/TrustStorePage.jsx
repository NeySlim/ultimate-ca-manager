/**
 * Trust Store Management Page
 * Manage trusted CA certificates for chain validation
 * Uses ResponsiveLayout for unified UI
 */
import { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { 
  ShieldCheck, Plus, Trash, Download, Certificate, Clock,
  CheckCircle, Warning, UploadSimple, ArrowsClockwise, Calendar,
  Globe, Buildings, Fingerprint, Key, Hash, Info
} from '@phosphor-icons/react'
import {
  Button, Input, Badge, Modal, Textarea, HelpCard,
  CompactSection, CompactGrid, CompactField, FormSelect
} from '../components'
import { SmartImportModal } from '../components/SmartImport'
import { ResponsiveLayout, ResponsiveDataTable } from '../components/ui/responsive'
import { truststoreService, casService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useModals } from '../hooks'
import { formatDate, cn } from '../lib/utils'
import { ERRORS, SUCCESS, CONFIRM } from '../lib/messages'

export default function TrustStorePage() {
  const { t } = useTranslation()
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canWrite, canDelete } = usePermission()
  const { modals, open: openModal, close: closeModal } = useModals(['add'])
  
  const [loading, setLoading] = useState(true)
  const [certificates, setCertificates] = useState([])
  const [certStats, setCertStats] = useState({ total: 0, root_ca: 0, intermediate_ca: 0, expired: 0, valid: 0 })
  const [selectedCert, setSelectedCert] = useState(null)
  const [syncing, setSyncing] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)
  
  // Add from managed CAs modal state
  const [managedCAs, setManagedCAs] = useState([])
  const [selectedCAIds, setSelectedCAIds] = useState([])
  const [adding, setAdding] = useState(false)
  const [loadingCAs, setLoadingCAs] = useState(false)

  useEffect(() => {
    loadCertificates()
  }, [])

  const loadCertificates = async () => {
    setLoading(true)
    try {
      const [certsRes, statsRes] = await Promise.all([
        truststoreService.getAll(),
        truststoreService.getStats()
      ])
      const rawCerts = certsRes.data || []
      // Add computed expiry status for filtering
      const now = new Date()
      const enrichedCerts = rawCerts.map(c => {
        const date = c.not_after ? new Date(c.not_after) : null
        const daysLeft = date ? Math.floor((date - now) / (1000 * 60 * 60 * 24)) : null
        return {
          ...c,
          _expiry_status: daysLeft === null ? 'valid' : daysLeft <= 0 ? 'expired' : daysLeft <= 90 ? 'expiring' : 'valid'
        }
      })
      setCertificates(enrichedCerts)
      setCertStats(statsRes.data || { total: 0, root_ca: 0, intermediate_ca: 0, expired: 0, valid: 0 })
    } catch (error) {
      showError(error.message || ERRORS.LOAD_FAILED.TRUSTSTORE)
    } finally {
      setLoading(false)
    }
  }

  const handleSelectCert = async (cert) => {
    try {
      const response = await truststoreService.getById(cert.id)
      setSelectedCert(response.data || cert)
    } catch (error) {
      setSelectedCert(cert)
    }
  }

  const loadManagedCAs = async () => {
    setLoadingCAs(true)
    try {
      const res = await casService.getAll()
      const cas = res.data || []
      // Filter out CAs already in truststore (by fingerprint match via subject)
      const existingSubjects = new Set(certificates.map(c => c.subject))
      setManagedCAs(cas.map(ca => ({ ...ca, alreadyInTruststore: existingSubjects.has(ca.subject) })))
    } catch (error) {
      showError(error.message)
    } finally {
      setLoadingCAs(false)
    }
  }

  const handleOpenAddModal = () => {
    setSelectedCAIds([])
    loadManagedCAs()
    openModal('add')
  }

  const handleAddFromCAs = async () => {
    if (selectedCAIds.length === 0) return
    setAdding(true)
    let added = 0
    try {
      for (const caId of selectedCAIds) {
        try {
          const exportRes = await casService.export(caId, 'pem')
          const pemText = typeof exportRes === 'string' ? exportRes : 
            exportRes instanceof Blob ? await exportRes.text() :
            exportRes?.data instanceof Blob ? await exportRes.data.text() :
            typeof exportRes?.data === 'string' ? exportRes.data : ''
          const ca = managedCAs.find(c => c.id === caId)
          await truststoreService.add({
            name: ca?.descr || ca?.common_name || `CA-${caId}`,
            description: ca?.organization || '',
            certificate_pem: pemText,
            purpose: ca?.is_root ? 'root_ca' : 'intermediate_ca',
            notes: t('trustStore.addedFromManaged')
          })
          added++
        } catch (err) {
          // Skip duplicates (409)
          if (!err.message?.includes('already')) {
            showError(`${managedCAs.find(c => c.id === caId)?.descr}: ${err.message}`)
          }
        }
      }
      if (added > 0) {
        showSuccess(t('trustStore.addedCount', { count: added }))
        loadCertificates()
      }
      closeModal('add')
    } finally {
      setAdding(false)
    }
  }

  const handleSyncFromSystem = async () => {
    const confirmed = await showConfirm(
      t('trustStore.syncConfirm'),
      { title: t('trustStore.syncTitle'), confirmText: t('trustStore.sync'), variant: 'primary' }
    )
    if (!confirmed) return
    
    setSyncing(true)
    try {
      const response = await truststoreService.syncFromSystem(50)
      showSuccess(response.message || t('trustStore.syncedCerts', { count: response.data?.new_count || 0 }))
      loadCertificates()
    } catch (error) {
      showError(error.message || t('trustStore.syncFailed'))
    } finally {
      setSyncing(false)
    }
  }

  const handleDelete = async (cert) => {
    const confirmed = await showConfirm(CONFIRM.DELETE.TRUSTSTORE, {
      title: t('trustStore.confirmRemove'),
      confirmText: t('common.delete'),
      variant: 'danger'
    })
    if (!confirmed) return
    
    try {
      await truststoreService.delete(cert.id)
      showSuccess(SUCCESS.DELETE.TRUSTSTORE)
      loadCertificates()
      if (selectedCert?.id === cert.id) {
        setSelectedCert(null)
      }
    } catch (error) {
      showError(error.message || ERRORS.DELETE_FAILED.TRUSTSTORE)
    }
  }

  const handleExport = (cert) => {
    if (!cert?.certificate_pem) return
    
    const blob = new Blob([cert.certificate_pem], { type: 'application/x-pem-file' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${cert.name.replace(/\s+/g, '_')}.pem`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleExportBundle = async (format = 'pem') => {
    try {
      const response = await truststoreService.exportBundle(format, 'all')
      const blob = response instanceof Blob ? response : response?.data instanceof Blob ? response.data : new Blob([response?.data || response], { type: 'application/x-pem-file' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `truststore-bundle.${format}`
      a.click()
      URL.revokeObjectURL(url)
      showSuccess(t('trustStore.bundleExported'))
    } catch (error) {
      showError(error.message || t('trustStore.exportFailed'))
    }
  }

  // Stats - from backend API
  const stats = useMemo(() => [
    { icon: ShieldCheck, label: t('common.rootCA'), value: certStats.root_ca, variant: 'success' },
    { icon: Certificate, label: t('common.intermediate'), value: certStats.intermediate_ca, variant: 'primary' },
    { icon: Warning, label: t('common.expired'), value: certStats.expired, variant: 'danger' },
    { icon: CheckCircle, label: t('common.total'), value: certStats.total, variant: 'default' }
  ], [certStats, t])

  // Toolbar actions - next to search bar
  const toolbarActions = (
    <div className="flex gap-2">
      {certificates.length > 0 && (
        <Button size="sm" variant="ghost" onClick={() => handleExportBundle('pem')} title={t('trustStore.exportBundle')}>
          <Download size={14} />
          <span className="hidden sm:inline">{t('trustStore.exportBundle')}</span>
        </Button>
      )}
      {canWrite('truststore') && (
        <>
          <Button size="sm" variant="secondary" onClick={handleSyncFromSystem} disabled={syncing}>
            <ArrowsClockwise size={14} className={syncing ? 'animate-spin' : ''} />
            <span className="hidden sm:inline">{syncing ? t('trustStore.syncing') : t('trustStore.sync')}</span>
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setShowImportModal(true)}>
            <UploadSimple size={14} />
            <span className="hidden sm:inline">{t('common.import')}</span>
          </Button>
          <Button size="sm" onClick={handleOpenAddModal}>
            <Plus size={14} />
            <span className="hidden sm:inline">{t('trustStore.add')}</span>
          </Button>
        </>
      )}
    </div>
  )

  // Columns
  const columns = useMemo(() => [
    {
      key: 'name',
      header: t('common.certificate'),
      priority: 1,
      sortable: true,
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 icon-bg-blue">
            <Certificate size={14} weight="duotone" />
          </div>
          <span className="font-medium truncate">{val}</span>
        </div>
      ),
      mobileRender: (val, row) => {
        const date = row.not_after ? new Date(row.not_after) : null
        const isExpired = date && date < new Date()
        const daysLeft = date ? Math.floor((date - new Date()) / (1000 * 60 * 60 * 24)) : null
        const isExpiringSoon = daysLeft !== null && daysLeft > 0 && daysLeft <= 30
        return (
          <div className="flex items-center justify-between gap-2 w-full">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <div className={cn(
                "w-7 h-7 rounded-lg flex items-center justify-center shrink-0",
                isExpired ? 'icon-bg-red' : isExpiringSoon ? 'icon-bg-orange' : 'icon-bg-emerald'
              )}>
                <Certificate size={14} weight="duotone" />
              </div>
              <span className="font-medium truncate">{val}</span>
            </div>
            <Badge variant={isExpired ? 'danger' : isExpiringSoon ? 'orange' : 'success'} size="sm" dot>
              {row.purpose?.replace('_', ' ') || t('common.custom')}
            </Badge>
          </div>
        )
      }
    },
    {
      key: 'purpose',
      header: t('common.purpose'),
      priority: 2,
      hideOnMobile: true,
      render: (val) => {
        const variants = {
          root_ca: 'amber',
          intermediate_ca: 'primary',
          client_auth: 'violet',
          code_signing: 'orange',
          system: 'teal',
          custom: 'secondary'
        }
        return <Badge variant={variants[val] || 'secondary'} size="sm" dot>{val?.replace('_', ' ')}</Badge>
      }
    },
    {
      key: 'not_after',
      header: t('common.expires'),
      priority: 2,
      mono: true,
      render: (val) => {
        if (!val) return <span className="text-text-tertiary">—</span>
        const date = new Date(val)
        const isExpired = date < new Date()
        const daysLeft = Math.floor((date - new Date()) / (1000 * 60 * 60 * 24))
        const isExpiringSoon = daysLeft > 0 && daysLeft <= 30
        return (
          <Badge variant={isExpired ? 'danger' : isExpiringSoon ? 'orange' : 'success'} size="sm" dot pulse={isExpired || isExpiringSoon}>
            {formatDate(val)}
          </Badge>
        )
      },
      mobileRender: (val) => {
        if (!val) return null
        return (
          <div className="flex items-center gap-2 text-xs">
            <span className="text-text-tertiary">{t('common.expires')}:</span>
            <span className="text-text-secondary">{formatDate(val)}</span>
          </div>
        )
      }
    }
  ], [t])

  // Row actions
  const rowActions = (row) => [
    { label: t('common.export'), icon: Download, onClick: () => handleExport(row) },
    ...(canDelete('truststore') ? [
      { label: t('common.delete'), icon: Trash, variant: 'danger', onClick: () => handleDelete(row) }
    ] : [])
  ]

  // Calculate days remaining for expiry indicator
  const getDaysRemaining = (cert) => {
    if (!cert?.not_after) return null
    const expiryDate = new Date(cert.not_after)
    return Math.ceil((expiryDate - new Date()) / (1000 * 60 * 60 * 24))
  }

  // Detail panel content - same design as CertificateDetails
  const detailContent = selectedCert && (() => {
    const daysRemaining = getDaysRemaining(selectedCert)
    const isExpired = daysRemaining !== null && daysRemaining <= 0
    const isExpiring = daysRemaining !== null && daysRemaining > 0 && daysRemaining <= 30
    
    return (
      <div className="space-y-4 p-4">
        {/* Header */}
        <div className="flex items-start gap-3">
          <div className={cn(
            "p-2.5 rounded-lg shrink-0",
            isExpired ? "bg-status-danger/10" : "bg-accent-primary/10"
          )}>
            <Certificate size={24} className={isExpired ? "text-status-danger" : "text-accent-primary"} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-lg font-semibold text-text-primary truncate">
                {selectedCert.name || selectedCert.subject_cn || t('common.certificate')}
              </h3>
              <Badge variant={isExpired ? 'danger' : isExpiring ? 'warning' : 'success'} size="sm">
                {isExpired ? t('common.expired') : isExpiring ? t('common.detailsExpiring') : t('common.valid')}
              </Badge>
              <Badge variant={selectedCert.purpose === 'root_ca' ? 'info' : 'default'} size="sm">
                {selectedCert.purpose?.replace('_', ' ') || 'trusted'}
              </Badge>
            </div>
            <p className="text-xs text-text-tertiary truncate mt-0.5">{selectedCert.subject || selectedCert.issuer}</p>
          </div>
        </div>

        {/* Expiry Indicator */}
        {daysRemaining !== null && (
          <div className={cn(
            "flex items-center gap-2 px-3 py-2 rounded-lg",
            isExpired && "bg-status-danger/10",
            isExpiring && "bg-status-warning/10",
            !isExpired && !isExpiring && "bg-status-success/10"
          )}>
            <Clock size={16} className={cn(
              isExpired && "text-status-danger",
              isExpiring && "text-status-warning",
              !isExpired && !isExpiring && "text-status-success"
            )} />
            <div>
              <div className={cn(
                "text-sm font-medium",
                isExpired && "text-status-danger",
                isExpiring && "text-status-warning",
                !isExpired && !isExpiring && "text-status-success"
              )}>
                {isExpired ? t('common.expired') : t('trustStore.daysRemaining', { count: daysRemaining })}
              </div>
              <div className="text-xs text-text-tertiary">
                {t('common.expires')} {formatDate(selectedCert.not_after)}
              </div>
            </div>
          </div>
        )}

        {/* Quick Stats Grid */}
        <div className="grid grid-cols-3 gap-2">
          <div className="bg-bg-tertiary/50 rounded-lg p-2.5 text-center">
            <Key size={16} className="mx-auto text-text-tertiary mb-1" />
            <div className="text-xs font-medium text-text-primary">{selectedCert.key_type || 'RSA'}</div>
            <div className="text-2xs text-text-tertiary">{t('common.keyType')}</div>
          </div>
          <div className="bg-bg-tertiary/50 rounded-lg p-2.5 text-center">
            <ShieldCheck size={16} className="mx-auto text-text-tertiary mb-1" />
            <div className="text-xs font-medium text-text-primary truncate">{selectedCert.signature_algorithm || 'SHA256'}</div>
            <div className="text-2xs text-text-tertiary">{t('common.signature')}</div>
          </div>
          <div className="bg-bg-tertiary/50 rounded-lg p-2.5 text-center">
            <Certificate size={16} className="mx-auto text-text-tertiary mb-1" />
            <div className="text-xs font-medium text-text-primary">{selectedCert.is_ca ? t('common.ca') : t('common.endEntity')}</div>
            <div className="text-2xs text-text-tertiary">{t('common.type')}</div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-2 flex-wrap">
          <Button size="sm" variant="secondary" onClick={() => handleExport(selectedCert)}>
            <Download size={14} /> {t('common.export')}
          </Button>
          {canDelete('truststore') && (
            <Button size="sm" variant="danger" onClick={() => handleDelete(selectedCert)}>
              <Trash size={14} /> {t('common.delete')}
            </Button>
          )}
        </div>

        {/* Subject Section */}
        <CompactSection title={t('common.subject')} icon={Globe}>
          <CompactGrid>
            <CompactField icon={Globe} label={t('common.commonName')} value={selectedCert.subject_cn || selectedCert.name} />
            <CompactField icon={Buildings} label={t('common.organization')} value={selectedCert.organization} />
          </CompactGrid>
        </CompactSection>

        {/* Issuer Section */}
        <CompactSection title={t('common.issuer')} icon={ShieldCheck}>
          <CompactField autoIcon="issuer" label={t('common.issuer')} value={selectedCert.issuer || selectedCert.issuer_cn} mono />
        </CompactSection>

        {/* Validity Section */}
        <CompactSection title={t('common.validity')} icon={Calendar}>
          <CompactGrid>
            <CompactField icon={Calendar} label={t('common.validFrom')} value={selectedCert.not_before ? formatDate(selectedCert.not_before) : '—'} />
            <CompactField icon={Calendar} label={t('common.validUntil')} value={selectedCert.not_after ? formatDate(selectedCert.not_after) : '—'} />
          </CompactGrid>
        </CompactSection>

        {/* Technical Details */}
        <CompactSection title={t('common.technicalDetails')} icon={Info}>
          <CompactGrid>
            <CompactField icon={Hash} label={t('common.serial')} value={selectedCert.serial_number} mono copyable />
            <CompactField icon={Key} label={t('common.keyType')} value={selectedCert.key_type} />
          </CompactGrid>
        </CompactSection>

        {/* Fingerprints */}
        {selectedCert.fingerprint_sha256 && (
          <CompactSection title={t('common.fingerprints')} icon={Fingerprint} collapsible defaultOpen={false}>
            <CompactField icon={Fingerprint} label={t('common.sha256')} value={selectedCert.fingerprint_sha256} mono copyable />
          </CompactSection>
        )}

        {/* Notes */}
        {selectedCert.notes && (
          <CompactSection title={t('common.notes')} icon={Warning}>
            <p className="text-sm text-text-secondary">{selectedCert.notes}</p>
          </CompactSection>
        )}
      </div>
    )
  })()

  // Help content
  const helpContent = (
    <div className="space-y-3">
      <HelpCard variant="info" title={t('common.aboutTrustStore')}>
        {t('trustStore.aboutTrustStoreDesc')}
      </HelpCard>
      
      <HelpCard variant="tip" title={t('common.bestPractices')}>
        {t('trustStore.bestPracticesDesc')}
      </HelpCard>

      <HelpCard variant="warning" title={t('common.securityNote')}>
        {t('trustStore.securityNoteDesc')}
      </HelpCard>
    </div>
  )

  return (
    <>
      <ResponsiveLayout
        title={t('common.trustStore')}
        subtitle={t('trustStore.subtitle', { count: certificates.length })}
        icon={ShieldCheck}
        stats={stats}
        helpPageKey="truststore"
        splitView={true}
        splitEmptyContent={
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
              <Certificate size={24} className="text-text-tertiary" />
            </div>
            <p className="text-sm text-text-secondary">{t('trustStore.selectToView')}</p>
          </div>
        }
        slideOverOpen={!!selectedCert}
        slideOverTitle={selectedCert?.name || t('common.certificate')}
        slideOverContent={detailContent}
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
          searchPlaceholder={t('common.searchCertificates')}
          searchKeys={['name', 'subject_cn', 'issuer_cn', 'purpose']}
          toolbarFilters={[
            {
              key: 'purpose',
              placeholder: t('trustStore.allPurposes'),
              options: [
                { value: 'root_ca', label: t('common.rootCA') },
                { value: 'intermediate_ca', label: t('common.intermediate') },
                { value: 'client_auth', label: t('trustStore.clientAuth') },
                { value: 'code_signing', label: t('common.codeSigning') },
                { value: 'system', label: t('common.system') },
                { value: 'custom', label: t('common.custom') }
              ]
            },
            {
              key: '_expiry_status',
              placeholder: t('trustStore.allStatuses'),
              options: [
                { value: 'valid', label: t('common.valid') },
                { value: 'expiring', label: t('trustStore.expiringSoon') },
                { value: 'expired', label: t('common.expired') }
              ]
            }
          ]}
          toolbarActions={toolbarActions}
          sortable
          defaultSort={{ key: 'name', direction: 'asc' }}
          pagination={true}
          emptyIcon={ShieldCheck}
          emptyTitle={t('trustStore.noCertificates')}
          emptyDescription={t('trustStore.addCertificatesForChain')}
          emptyAction={canWrite('truststore') && (
            <Button onClick={handleOpenAddModal}>
              <Plus size={16} /> {t('trustStore.addCertificate')}
            </Button>
          )}
        />
      </ResponsiveLayout>

      {/* Add from Managed CAs Modal */}
      <Modal
        open={modals.add}
        onClose={() => closeModal('add')}
        title={t('trustStore.addFromManagedCAs')}
      >
        <div className="p-4 space-y-4">
          {loadingCAs ? (
            <div className="flex items-center justify-center py-8">
              <ArrowsClockwise size={20} className="animate-spin text-text-tertiary" />
            </div>
          ) : managedCAs.length === 0 ? (
            <p className="text-sm text-text-secondary text-center py-8">{t('trustStore.noManagedCAs')}</p>
          ) : (
            <>
              <p className="text-sm text-text-secondary">{t('trustStore.selectCAsToAdd')}</p>
              <div className="border border-border rounded-lg overflow-hidden">
                <div className="flex items-center justify-between px-3 py-2 bg-bg-secondary border-b border-border">
                  <label className="flex items-center gap-2 text-sm font-medium cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedCAIds.length === managedCAs.filter(ca => !ca.alreadyInTruststore).length && selectedCAIds.length > 0}
                      onChange={(e) => setSelectedCAIds(e.target.checked ? managedCAs.filter(ca => !ca.alreadyInTruststore).map(ca => ca.id) : [])}
                      className="w-4 h-4 rounded border-border text-accent-primary"
                    />
                    {t('common.selectAll')} ({selectedCAIds.length}/{managedCAs.filter(ca => !ca.alreadyInTruststore).length})
                  </label>
                </div>
                <div className="max-h-64 overflow-y-auto divide-y divide-border">
                  {managedCAs.map(ca => (
                    <label key={ca.id} className={cn(
                      "flex items-center gap-3 px-3 py-2.5 transition-colors",
                      ca.alreadyInTruststore ? "opacity-50 cursor-not-allowed" : "hover:bg-bg-secondary cursor-pointer"
                    )}>
                      <input
                        type="checkbox"
                        checked={selectedCAIds.includes(ca.id)}
                        onChange={() => {
                          if (ca.alreadyInTruststore) return
                          setSelectedCAIds(prev => prev.includes(ca.id) ? prev.filter(id => id !== ca.id) : [...prev, ca.id])
                        }}
                        disabled={ca.alreadyInTruststore}
                        className="w-4 h-4 rounded border-border text-accent-primary shrink-0"
                      />
                      <ShieldCheck size={16} className={ca.is_root ? 'text-accent-primary shrink-0' : 'text-status-info shrink-0'} />
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium truncate">{ca.descr || ca.common_name}</div>
                        {ca.organization && <div className="text-xs text-text-tertiary truncate">{ca.organization}</div>}
                      </div>
                      <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase shrink-0 ${ca.is_root ? 'bg-accent-primary/15 text-accent-primary' : 'bg-status-info/15 text-status-info'}`}>
                        {ca.is_root ? 'Root' : 'Inter'}
                      </span>
                      {ca.alreadyInTruststore && (
                        <CheckCircle size={16} weight="fill" className="text-status-success shrink-0" title={t('trustStore.alreadyInTruststore')} />
                      )}
                    </label>
                  ))}
                </div>
              </div>
            </>
          )}
          <div className="flex justify-end gap-2 pt-4 border-t border-border">
            <Button variant="secondary" onClick={() => closeModal('add')}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleAddFromCAs} disabled={adding || selectedCAIds.length === 0}>
              {adding ? t('trustStore.adding') : t('trustStore.addSelected', { count: selectedCAIds.length })}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Smart Import Modal */}
      <SmartImportModal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        onImportComplete={() => {
          setShowImportModal(false)
          loadCertificates()
        }}
      />
    </>
  )
}
