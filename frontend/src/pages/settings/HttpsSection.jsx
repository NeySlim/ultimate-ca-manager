import { useTranslation } from 'react-i18next'
import { Btn, IconBtn, Notice, Props, RecordList, RecordRow } from '../../components/atelier'
import { SettingsGroup } from '../../components/atelier/SettingsView'
import { formatDate, certificateLabel } from '../../lib/utils'

export default function HttpsSection({ httpsInfo, selectedHttpsCert, setSelectedHttpsCert, setShowCertPicker, handleApplyUcmCert, handleRegenerateHttpsCert, setShowHttpsImportModal, onUnbindHttpsCert }) {
  const { t } = useTranslation()
  const bound = httpsInfo?.bound_certificate
  const attention = bound?.needs_attention
  return (
    <>
      <SettingsGroup legend={t('settings.currentCertificate')} grid={false}>
        <Props items={[
          [t('common.commonName'), httpsInfo?.common_name || window.location.hostname],
          [t('common.issuer'), httpsInfo?.issuer || '—'],
          [t('common.validFrom'), formatDate(httpsInfo?.valid_from)],
          [t('common.validUntil'), formatDate(httpsInfo?.valid_to)],
          [t('settings.fingerprintSha256'), httpsInfo?.fingerprint ? <span className="mono">{httpsInfo.fingerprint}</span> : '—'],
        ]} />
        {bound ? (
          <RecordList>
            <RecordRow title={<>{t('settings.httpsBound')}{t('work.sep')}{certificateLabel(bound) || bound.refid}</>}
              meta={t('settings.httpsBoundDesc')}
              action={onUnbindHttpsCert && <Btn onClick={onUnbindHttpsCert}>{t('settings.httpsUnbind')}</Btn>} />
          </RecordList>
        ) : (
          <p className="group-hint">{t('settings.httpsNotBound')}</p>
        )}
        {attention && (
          <Notice tone="bad" id="https-left-behind">
            <strong>{t('settings.httpsLeftBehind')}</strong>{' '}
            {attention.successor_archived
              ? t('settings.httpsLeftBehindSuperseded')
              : attention.successor_has_key ? t('settings.httpsLeftBehindKeyed') : t('settings.httpsLeftBehindNoKey')}
            {attention.successor_id && (
              <span className="row-actions notice-actions">
                <a className="text-link" href={`/certificates/${attention.successor_id}`}>{t('settings.httpsOpenRenewed')}</a>
                {attention.successor_has_key && !attention.successor_archived && (
                  <Btn onClick={() => setSelectedHttpsCert({ id: attention.successor_id, common_name: attention.successor_descr || attention.successor_refid })}>
                    {t('settings.httpsSelectRenewed')}
                  </Btn>
                )}
              </span>
            )}
          </Notice>
        )}
      </SettingsGroup>

      <SettingsGroup legend={t('settings.useUCMCert')} hint={t('settings.useUcmCertificateDesc')} grid={false}>
        {selectedHttpsCert && (
          <RecordList>
            <RecordRow title={selectedHttpsCert.common_name || t('common.certificate')}
              meta={`${t('common.expires')} ${formatDate(selectedHttpsCert.valid_to)}`}
              action={<IconBtn icon="block" label={t('common.clear')} onClick={() => setSelectedHttpsCert(null)} />} />
          </RecordList>
        )}
        <div className="settings-actions">
          <Btn icon="search" onClick={() => setShowCertPicker(true)}>{t('settings.chooseCertificate')}</Btn>
          <Btn tone="primary" icon="shield" onClick={handleApplyUcmCert} disabled={!selectedHttpsCert}>{t('settings.applySelectedCertificate')}</Btn>
        </div>
      </SettingsGroup>

      <SettingsGroup legend={t('settings.regenerateCert')} hint={t('settings.regenerateCertificateDesc')} grid={false}>
        <div className="settings-actions">
          <Btn icon="key" onClick={handleRegenerateHttpsCert}>{t('settings.regenerateSelfSigned')}</Btn>
        </div>
      </SettingsGroup>

      <SettingsGroup legend={t('settings.applyCustomCert')} hint={t('settings.applyCustomCertificateDesc')} grid={false}>
        <div className="settings-actions">
          <Btn icon="upload" write onClick={() => setShowHttpsImportModal(true)}>{t('common.importCertificate')}</Btn>
        </div>
      </SettingsGroup>
    </>
  )
}
