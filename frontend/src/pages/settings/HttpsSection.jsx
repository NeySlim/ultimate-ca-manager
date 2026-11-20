import { useTranslation } from 'react-i18next'
import { MagnifyingGlass, ShieldCheck, Key, UploadSimple, Warning, X } from '@phosphor-icons/react'
import { Button } from '../../components'
import { formatDate, certificateLabel } from '../../lib/utils'
import { FormGroup, FormProps } from '../../components/sectioned'

export default function HttpsSection({ httpsInfo, selectedHttpsCert, setSelectedHttpsCert, setShowCertPicker, handleApplyUcmCert, handleRegenerateHttpsCert, setShowHttpsImportModal, onUnbindHttpsCert }) {
  const { t } = useTranslation()
  return (
    <>
      <FormGroup title={t('settings.currentCertificate')}>
        <FormProps items={[
          [t('common.commonName'), httpsInfo?.common_name || window.location.hostname],
          [t('common.issuer'), httpsInfo?.issuer || '—'],
          [t('common.validFrom'), formatDate(httpsInfo?.valid_from)],
          [t('common.validUntil'), formatDate(httpsInfo?.valid_to)],
          [t('settings.fingerprintSha256'), httpsInfo?.fingerprint || '—'],
        ]} />
        {httpsInfo?.bound_certificate ? (
          <ul className="sf-records sf-under">
            <li>
              <div className="sf-record-main">
                <strong>
                  {t('settings.httpsBound')}{t('work.sep')}{certificateLabel(httpsInfo.bound_certificate) || httpsInfo.bound_certificate.refid}
                </strong>
                <span className="sf-record-meta">{t('settings.httpsBoundDesc')}</span>
              </div>
              {onUnbindHttpsCert && (
                <div className="sf-record-actions">
                  <Button type="button" variant="secondary" onClick={onUnbindHttpsCert}>
                    {t('settings.httpsUnbind')}
                  </Button>
                </div>
              )}
            </li>
          </ul>
        ) : (
          <p className="sf-hint sf-under">{t('settings.httpsNotBound')}</p>
        )}
        {httpsInfo?.bound_certificate?.needs_attention && (() => {
          const attention = httpsInfo.bound_certificate.needs_attention
          return (
            <div className="ui-notice is-bad sf-under" data-testid="https-left-behind">
              <Warning aria-hidden="true" />
              <div className="ui-notice-body">
                <strong>{t('settings.httpsLeftBehind')}</strong>{' '}
                {attention.successor_archived
                  ? t('settings.httpsLeftBehindSuperseded')
                  : attention.successor_has_key ? t('settings.httpsLeftBehindKeyed') : t('settings.httpsLeftBehindNoKey')}
                <div className="sf-actions-row sf-under">
                  {attention.successor_id && (
                    <a className="sf-link" href={`/certificates/${attention.successor_id}`}>
                      {t('settings.httpsOpenRenewed')}
                    </a>
                  )}
                  {attention.successor_has_key && !attention.successor_archived && attention.successor_id && (
                    <Button type="button" variant="secondary"
                      onClick={() => setSelectedHttpsCert({
                        id: attention.successor_id, common_name: attention.successor_descr || attention.successor_refid,
                      })}>
                      {t('settings.httpsSelectRenewed')}
                    </Button>
                  )}
                </div>
              </div>
            </div>
          )
        })()}
      </FormGroup>

      <FormGroup title={t('settings.useUCMCert')} description={t('settings.useUcmCertificateDesc')}>
        <div className="sf-stack">
          {selectedHttpsCert ? (
            <ul className="sf-records">
              <li>
                <div className="sf-record-main">
                  <strong>{selectedHttpsCert.common_name || t('common.certificate')}</strong>
                  <span className="sf-record-meta">{t('common.expires')} {formatDate(selectedHttpsCert.valid_to)}</span>
                </div>
                <div className="sf-record-actions">
                  <Button type="button" variant="secondary" onClick={() => setSelectedHttpsCert(null)}
                    aria-label={t('common.clear')} title={t('common.clear')}>
                    <X size={16} />
                  </Button>
                </div>
              </li>
            </ul>
          ) : null}
          <div className="sf-actions-row">
            <Button type="button" variant="secondary" onClick={() => setShowCertPicker(true)}>
              <MagnifyingGlass size={16} />
              {t('settings.chooseCertificate')}
            </Button>
            <Button variant="primary" onClick={handleApplyUcmCert} disabled={!selectedHttpsCert}>
              <ShieldCheck size={16} />
              {t('settings.applySelectedCertificate')}
            </Button>
          </div>
        </div>
      </FormGroup>

      <FormGroup title={t('settings.regenerateCert')} description={t('settings.regenerateCertificateDesc')}>
        <div className="sf-actions-row">
          <Button type="button" variant="secondary" onClick={handleRegenerateHttpsCert}>
            <Key size={16} />
            {t('settings.regenerateSelfSigned')}
          </Button>
        </div>
      </FormGroup>

      <FormGroup title={t('settings.applyCustomCert')} description={t('settings.applyCustomCertificateDesc')}>
        <div className="sf-actions-row">
          <Button variant="secondary" onClick={() => setShowHttpsImportModal(true)}>
            <UploadSimple size={16} />
            {t('common.importCertificate')}
          </Button>
        </div>
      </FormGroup>
    </>
  )
}
