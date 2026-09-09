/**
 * CAs Page — detail panel for selected CA (mobile slide-over)
 */
import { useState } from 'react'
import { Download, Trash, Certificate, Clock, ShieldWarning, ShieldCheck, PushPin, FileArrowDown, UploadSimple, ArrowsClockwise, Prohibit } from '@phosphor-icons/react'
import {
  Badge, Button,
  CompactSection, CompactGrid, CompactField, CompactStats,
  CATypeIcon
} from '../../components'
import { ExportModal } from '../../components/ExportModal'
import { TakeOfflineModal } from '../../components/cas/TakeOfflineModal'
import { RestoreModal } from '../../components/cas/RestoreModal'
import { RevokeCertificateModal } from '../../components/RevokeCertificateModal'
import { ManageTemplatePinsModal } from '../../components/cas/ManageTemplatePinsModal'
import { CACrlSection } from '../../components/cas/CACrlSection'
import { UploadCACertModal } from './UploadCACertModal'
import { casService } from '../../services'
import { formatDate, downloadBlob } from '../../lib/utils'
import { useNotification } from '../../contexts/NotificationContext'

// =============================================================================
// CA DETAILS PANEL
// =============================================================================

export function CADetailsPanel({ ca, canWrite, canDelete, onExport, onDelete, onChanged, t }) {
  const [showExportModal, setShowExportModal] = useState(false)
  const [showOfflineModal, setShowOfflineModal] = useState(false)
  const [showRestoreModal, setShowRestoreModal] = useState(false)
  const [showPinsModal, setShowPinsModal] = useState(false)
  const [showUploadCertModal, setShowUploadCertModal] = useState(false)
  const [showRevokeModal, setShowRevokeModal] = useState(false)
  const [revoking, setRevoking] = useState(false)
  const { showSuccess, showError, showWarning } = useNotification()

  const isExternal = ca.imported_from === 'external_csr'
  const isRoot = ca.type === 'root' || ca.is_root
  // Revocation is done by the parent CA, so it needs one held in UCM (#343)
  const canRevoke = canWrite('cas') && !isRoot && !!ca.parent_id && !ca.pending && !ca.revoked

  const handleRevoke = async (reason) => {
    setRevoking(true)
    try {
      const res = await casService.revoke(ca.id, { reason })
      const updated = res?.data || res
      showSuccess(t('cas.revokeSuccess'))
      // The parent could not publish the revocation (offline parent, CDP off)
      for (const w of updated?.warnings || []) showWarning(w)
      setShowRevokeModal(false)
      // The list reloads on the event; the panel shows this CA's new state now
      if (updated?.id) onChanged?.(updated)
      window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'ca' } }))
    } catch (err) {
      showError(err?.message || t('cas.revokeFailed'))
    } finally {
      setRevoking(false)
    }
  }

  const handleDownloadCsr = async () => {
    try {
      const blob = await casService.downloadCsr(ca.id)
      const name = (ca.name || ca.common_name || 'ca').replace(/[^a-zA-Z0-9._-]+/g, '_')
      downloadBlob(blob, `${name}.csr`)
    } catch (err) {
      showError(err?.message || t('cas.csrDownloadFailed'))
    }
  }

  const handleRenewCsr = async () => {
    try {
      const response = await casService.renewCsr(ca.id)
      showSuccess(t('cas.csrDownloadStarted'))
      window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'ca' } }))
      await handleDownloadCsr()
    } catch (err) {
      showError(err?.message || t('cas.csrDownloadFailed'))
    }
  }

  return (
    <>
    <ManageTemplatePinsModal
      open={showPinsModal}
      onOpenChange={setShowPinsModal}
      ca={ca}
      t={t}
    />
    <div className="p-3 space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2">
        <CATypeIcon isRoot={ca.type === 'root' || ca.is_root} size="lg" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-text-primary truncate">
              {ca.name || ca.common_name || t('common.certificateAuthority')}
            </h3>
            <Badge variant={ca.type === 'root' || ca.is_root ? 'warning' : 'primary'} size="sm">
              {ca.type === 'root' || ca.is_root ? t('common.rootCA') : t('common.intermediateCA')}
            </Badge>
            {ca.uses_hsm && (
              <Badge variant="info" size="sm" title={[ca.hsm_provider_name, ca.hsm_key_label].filter(Boolean).join(' / ')}>
                {t('cas.detail.hsmBacked')}
              </Badge>
            )}
          </div>
          {ca.subject && (
            <p className="text-xs text-text-secondary truncate">{ca.subject}</p>
          )}
        </div>
      </div>

      {/* Awaiting-certificate banner (external-CSR mode, #298) */}
      {ca.pending && (
        <div className="rounded-lg px-3 py-2 bg-status-warning/20 border border-status-warning/40">
          <div className="flex items-center gap-2 text-status-warning">
            <Clock size={16} />
            <span className="text-xs font-medium">{t('cas.awaitingCertificate')}</span>
          </div>
          <p className="text-2xs text-text-secondary mt-1">{t('cas.awaitingBannerText')}</p>
          <div className="flex gap-1.5 mt-1.5">
            <Button type="button" size="xs" variant="secondary" onClick={handleDownloadCsr}>
              <FileArrowDown size={12} /> {t('cas.downloadCsr')}
            </Button>
            {canWrite('cas') && (
              <Button type="button" size="xs" variant="primary" onClick={() => setShowUploadCertModal(true)}>
                <UploadSimple size={12} /> {t('cas.uploadCertificate')}
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Revoked banner (#343) */}
      {ca.revoked && (
        <div className="rounded-lg px-3 py-2 bg-status-danger/20 border border-status-danger/40">
          <div className="flex items-center gap-2 text-status-danger">
            <Prohibit size={16} />
            <span className="text-xs font-medium">{t('common.revoked')}</span>
          </div>
          <p className="text-xs text-text-secondary mt-1">
            {t('cas.revokedBanner', {
              date: ca.revoked_at ? formatDate(ca.revoked_at, 'short') : '—',
              reason: t(`revocation.reasons.${ca.revoke_reason || 'unspecified'}`),
            })}
          </p>
        </div>
      )}

      {/* Offline banner */}
      {ca.offline && (
        <div className="rounded-lg px-3 py-2 bg-status-warning/20 border border-status-warning/40">
          <div className="flex items-center gap-2 text-status-warning">
            <ShieldWarning size={16} />
            <span className="text-xs font-medium">{t('cas.offline')}</span>
          </div>
          {canWrite('cas') && (
            <Button
              type="button"
              size="xs"
              variant="secondary"
              className="mt-1.5"
              onClick={() => setShowRestoreModal(true)}
            >
              {t('cas.restore')}
            </Button>
          )}
        </div>
      )}

      {/* Stats */}
      <CompactStats stats={[
        { icon: Certificate, value: t('cas.certificateCount', { count: ca.certs || 0 }) },
        { icon: Clock, value: ca.valid_to ? formatDate(ca.valid_to, 'short') : '—' },
        ca.pending
          ? { badge: t('cas.awaitingCertificate'), badgeVariant: 'warning' }
          : ca.revoked
            ? { badge: t('common.revoked'), badgeVariant: 'danger' }
            : ca.offline
              ? { badge: t('cas.offline'), badgeVariant: 'warning' }
              : { badge: ca.status, badgeVariant: ca.status === 'Active' ? 'success' : 'danger' }
      ]} />

      {/* Export + Delete Actions */}
      <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
        {!ca.pending && (
          <Button type="button" size="xs" variant="secondary" onClick={() => setShowExportModal(true)}>
            <Download size={14} /> {t('export.title')}
          </Button>
        )}
        {canWrite('cas') && !ca.pending && (
          <Button type="button" size="xs" variant="secondary" onClick={() => setShowPinsModal(true)}>
            <PushPin size={14} /> {t('templates.managePins')}
          </Button>
        )}
        {isExternal && !ca.pending && canWrite('cas') && !ca.offline && !ca.revoked && (
          <Button type="button" size="xs" variant="secondary" onClick={handleRenewCsr}>
            <ArrowsClockwise size={14} /> {t('cas.renewViaCsr')}
          </Button>
        )}
        {isExternal && !ca.pending && ca.has_csr && canWrite('cas') && (
          <Button type="button" size="xs" variant="secondary" onClick={() => setShowUploadCertModal(true)}>
            <UploadSimple size={14} /> {t('cas.uploadCertificate')}
          </Button>
        )}
        {canWrite('cas') && !ca.offline && !ca.pending && (
          <Button
            type="button"
            size="xs"
            variant="danger"
            onClick={() => setShowOfflineModal(true)}
          >
            <ShieldWarning size={12} className="sm:w-3.5 sm:h-3.5" /> {t('cas.takeOffline')}
          </Button>
        )}
        {canRevoke && (
          <Button type="button" size="xs" variant="danger" onClick={() => setShowRevokeModal(true)}>
            <Prohibit size={12} className="sm:w-3.5 sm:h-3.5" /> {t('cas.revoke')}
          </Button>
        )}
        {canDelete('cas') && (
          <Button type="button" size="xs" variant="danger" onClick={onDelete} className="sm:!h-8 sm:!px-3">
            <Trash size={12} className="sm:w-3.5 sm:h-3.5" />
          </Button>
        )}
      </div>

      {/* Revocation list — key-less/offline CA served from an external CRL (#302) */}
      <CACrlSection ca={ca} />

      {/* Subject Info */}
      <CompactSection title={t('common.subject')}>
        <CompactGrid>
          <CompactField autoIcon="commonName" label={t('common.commonName')} value={ca.common_name} copyable className="col-span-2" />
          <CompactField autoIcon="organization" label={t('common.organization')} value={ca.organization} copyable />
          <CompactField autoIcon="country" label={t('common.country')} value={ca.country} />
          <CompactField autoIcon="stateProvince" label={t('common.stateProvince')} value={ca.state} />
          <CompactField autoIcon="locality" label={t('cas.locality')} value={ca.locality} />
        </CompactGrid>
      </CompactSection>

      {/* Key Info */}
      <CompactSection title={t('common.keyInformation')}>
        <CompactGrid>
          <CompactField autoIcon="algorithm" label={t('common.algorithm')} value={ca.key_algorithm || 'RSA'} />
          <CompactField autoIcon="keySize" label={t('common.keySize')} value={ca.key_size} />
          <CompactField autoIcon="signature" label={t('common.signature')} value={ca.signature_algorithm} />
          {ca.uses_hsm && (
            <>
              <CompactField label={t('cas.create.hsmProvider')} value={ca.hsm_provider_name || '—'} />
              <CompactField label={t('cas.detail.hsmKey')} value={ca.hsm_key_label || '—'} mono />
            </>
          )}
        </CompactGrid>
      </CompactSection>

      {/* Validity */}
      <CompactSection title={t('common.validity')}>
        <CompactGrid>
          <CompactField autoIcon="validFrom" label={t('common.validFrom')} value={ca.valid_from ? formatDate(ca.valid_from) : '—'} />
          <CompactField autoIcon="validTo" label={t('common.validTo')} value={ca.valid_to ? formatDate(ca.valid_to) : '—'} />
          <CompactField autoIcon="serialNumber" label={t('common.serialNumber')} value={ca.serial_number} copyable mono className="col-span-2" />
        </CompactGrid>
      </CompactSection>

      {/* Fingerprints */}
      {(ca.thumbprint_sha1 || ca.thumbprint_sha256) && (
        <CompactSection title={t('common.fingerprints')}>
          <CompactGrid>
            {ca.thumbprint_sha1 && (
              <CompactField autoIcon="sha1" label="SHA-1" value={ca.thumbprint_sha1} copyable mono className="col-span-2" />
            )}
            {ca.thumbprint_sha256 && (
              <CompactField autoIcon="sha256" label="SHA-256" value={ca.thumbprint_sha256} copyable mono className="col-span-2" />
            )}
          </CompactGrid>
        </CompactSection>
      )}
    </div>

    <ExportModal
      open={showExportModal}
      onClose={() => setShowExportModal(false)}
      entityType="ca"
      entityName={ca.name || ca.common_name || ''}
      hasPrivateKey={!!ca.has_private_key && !ca.uses_hsm}
      canExportKey={canWrite('cas') && !ca.uses_hsm}
      isHsmBacked={!!ca.uses_hsm}
      onExport={onExport}
    />

    <TakeOfflineModal
      open={showOfflineModal}
      onClose={() => setShowOfflineModal(false)}
      ca={ca}
    />

    <RevokeCertificateModal

      open={showRevokeModal}

      onClose={() => setShowRevokeModal(false)}

      onConfirm={handleRevoke}

      certificate={{ name: ca.name || ca.common_name }}

      loading={revoking}

      title={t('cas.revoke')}

      warning={t('cas.revokeWarning')}

    />

    <RestoreModal
      open={showRestoreModal}
      onClose={() => setShowRestoreModal(false)}
      ca={ca}
    />

    <UploadCACertModal
      open={showUploadCertModal}
      onClose={() => setShowUploadCertModal(false)}
      ca={ca}
    />
    </>
  )
}
