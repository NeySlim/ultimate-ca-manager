/**
 * CAs Page — detail panel for selected CA (mobile slide-over)
 */
import { useState } from 'react'
import { Download, Trash, Certificate, Clock } from '@phosphor-icons/react'
import {
  Badge, Button,
  CompactSection, CompactGrid, CompactField, CompactStats,
  CATypeIcon
} from '../../components'
import { ExportModal } from '../../components/ExportModal'
import { formatDate } from '../../lib/utils'

// =============================================================================
// CA DETAILS PANEL
// =============================================================================

export function CADetailsPanel({ ca, canWrite, canDelete, onExport, onDelete, t }) {
  const [showExportModal, setShowExportModal] = useState(false)
  return (
    <>
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

      {/* Stats */}
      <CompactStats stats={[
        { icon: Certificate, value: t('cas.certificateCount', { count: ca.certs || 0 }) },
        { icon: Clock, value: ca.valid_to ? formatDate(ca.valid_to, 'short') : '—' },
        { badge: ca.status, badgeVariant: ca.status === 'Active' ? 'success' : 'danger' }
      ]} />

      {/* Export + Delete Actions */}
      <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
        <Button type="button" size="xs" variant="secondary" onClick={() => setShowExportModal(true)}>
          <Download size={14} /> {t('export.title')}
        </Button>
        {canDelete('cas') && (
          <Button type="button" size="xs" variant="danger" onClick={onDelete} className="sm:!h-8 sm:!px-3">
            <Trash size={12} className="sm:w-3.5 sm:h-3.5" />
          </Button>
        )}
      </div>

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
    </>
  )
}
