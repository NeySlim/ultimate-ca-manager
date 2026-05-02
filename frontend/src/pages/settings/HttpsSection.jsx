import { useTranslation } from 'react-i18next'
import { Lock, Certificate, MagnifyingGlass, ShieldCheck, ArrowsClockwise, Key, UploadSimple } from '@phosphor-icons/react'
import { Button, Badge, DetailHeader, DetailSection, DetailGrid, DetailField, DetailContent } from '../../components'
import { formatDate } from '../../lib/utils'

export default function HttpsSection({ httpsInfo, selectedHttpsCert, setSelectedHttpsCert, setShowCertPicker, handleApplyUcmCert, handleRegenerateHttpsCert, setShowHttpsImportModal }) {
  const { t } = useTranslation()
  return (
    <DetailContent>
      <DetailHeader
        icon={Lock}
        title={t('settings.httpsTitle')}
        subtitle={t('settings.httpsSubtitle')}
        badge={httpsInfo?.type && (
          <Badge variant={httpsInfo?.type === 'CA-Signed' ? 'success' : httpsInfo?.type === 'Self-Signed' ? 'warning' : 'secondary'}>
            {httpsInfo?.type}
          </Badge>
        )}
      />
      <DetailSection title={t('settings.currentCertificate')} icon={Certificate} iconClass="icon-bg-emerald">
        <DetailGrid>
          <DetailField
            label={t('common.commonName')}
            value={httpsInfo?.common_name || window.location.hostname}
          />
          <DetailField
            label={t('common.issuer')}
            value={httpsInfo?.issuer || '-'}
          />
          <DetailField
            label={t('common.validFrom')}
            value={formatDate(httpsInfo?.valid_from)}
          />
          <DetailField
            label={t('common.validUntil')}
            value={formatDate(httpsInfo?.valid_to)}
          />
          <DetailField
            label={t('settings.fingerprintSha256')}
            value={httpsInfo?.fingerprint || '-'}
            mono
            copyable
            fullWidth
          />
        </DetailGrid>
      </DetailSection>

      <DetailSection title={t('settings.useUCMCert')} icon={Certificate} iconClass="icon-bg-violet">
        <div className="space-y-4">
          <p className="text-xs text-text-secondary">
            {t('settings.useUcmCertificateDesc')}
          </p>
          {selectedHttpsCert ? (
            <div className="flex items-center gap-3 p-3 rounded-lg border border-accent-primary-op30 bg-accent-primary-op5">
              <Certificate size={20} className="text-accent-primary shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-text-primary truncate">
                  {selectedHttpsCert.common_name || t('common.certificate')}
                </div>
                <div className="text-xs text-text-secondary">
                  {t('common.expires')} {formatDate(selectedHttpsCert.valid_to)}
                </div>
              </div>
              <Button type="button" variant="ghost" size="xs" onClick={() => setSelectedHttpsCert(null)} aria-label={t('common.clear')}>
                ×
              </Button>
            </div>
          ) : null}
          <div className="flex gap-2">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => setShowCertPicker(true)}
            >
              <MagnifyingGlass size={16} />
              {t('settings.chooseCertificate')}
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleApplyUcmCert}
              disabled={!selectedHttpsCert}
            >
              <ShieldCheck size={16} />
              {t('settings.applySelectedCertificate')}
            </Button>
          </div>
        </div>
      </DetailSection>

      <DetailSection title={t('settings.regenerateCert')} icon={ArrowsClockwise} iconClass="icon-bg-emerald">
        <div className="space-y-3">
          <p className="text-xs text-text-secondary">
            {t('settings.regenerateCertificateDesc')}
          </p>
          <Button type="button" variant="secondary" size="sm" onClick={handleRegenerateHttpsCert}>
            <Key size={16} />
            {t('settings.regenerateSelfSigned')}
          </Button>
        </div>
      </DetailSection>

      <DetailSection title={t('settings.applyCustomCert')} icon={Lock} iconClass="icon-bg-amber">
        <div className="space-y-3">
          <p className="text-xs text-text-secondary">
            {t('settings.applyCustomCertificateDesc')}
          </p>
          <Button
            variant="secondary"
            onClick={() => setShowHttpsImportModal(true)}
          >
            <UploadSimple size={16} className="mr-2" />
            {t('common.importCertificate')}
          </Button>
        </div>
      </DetailSection>
    </DetailContent>
  )
}
