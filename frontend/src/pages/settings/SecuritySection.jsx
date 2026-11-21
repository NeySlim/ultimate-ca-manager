import { useTranslation } from 'react-i18next'
import { Btn, Pill, Props, Notice, RecordList, RecordRow, Section, SkeletonPanel } from '../../components/atelier'
import { NumberInput, Select, Textarea, ToggleSwitch } from '../../components/atelier/Form'
import { SettingsGroup } from '../../components/atelier/SettingsView'
import { formatDate } from '../../lib/utils'
import { anchorPickerCas } from '../../lib/caSelection'
import AdminLockLabel from './AdminLockLabel'
import { shownNumber, typedNumber } from './numberFields'

// The API sends a list; the textarea edits one entry per line.
function networksText(value) {
  return Array.isArray(value) ? value.join('\n') : (value || '')
}

function networksList(value) {
  return networksText(value).split(/[\s,;]+/).filter(Boolean)
}

const withTime = { hour: '2-digit', minute: '2-digit' }

export default function SecuritySection({ settings, fieldErrors = {}, updateSetting, hasPermission, encryptionStatus, setShowEnableEncryptionModal, setShowDisableEncryptionModal, handleDownloadExistingMasterKey, handleEncryptRemainingKeys, handleRotateDataKey, encryptionLoading, secretsStatus, handleRotateSessionKey, sessionKeyLoading, anomalies, anomaliesLoading, loadAnomalies, mtlsSettings, setMtlsSettings, mtlsLoading, cas }) {
  const { t } = useTranslation()
  // Fields the API writes for admin:settings only are shown, but disabled.
  const canAdminSettings = Boolean(hasPermission('admin:settings'))
  const adminLocked = !canAdminSettings
  const lockedLabel = (key) => <AdminLockLabel text={t(key)} locked={adminLocked} mockup />
  const enc = encryptionStatus
  const session = secretsStatus?.session_secret
  return (
    <>
      <SettingsGroup legend={t('settings.keyEncryption')} grid={false}>
        {enc ? (
          <>
            <Props items={[
              [t('common.status'), enc.disabling ? <Pill tone="warn" label={t('settings.encryptionDisabling')} />
                : <Pill tone={enc.enabled ? 'good' : 'warn'} label={enc.enabled ? t('common.enabled') : t('common.disabled')} />],
              enc.enabled && enc.key_source && [t('settings.keySource'), enc.key_file_path],
              enc.enabled && enc.kek_fingerprint && [t('settings.kekFingerprint'), <span className="mono">{enc.kek_fingerprint}</span>],
              enc.enabled && enc.kek_fingerprint && [t('settings.dekVersion'), (
                <span className="row-actions">
                  <span>{enc.dek_version}</span>
                  {enc.rotation_in_progress && <Pill tone="warn" label={t('settings.dekRotationInProgress')} />}
                  {enc.rotation_available_after ? (
                    <Pill tone="muted" icon="clock" label={t('settings.rotationAvailableAfter', { date: formatDate(enc.rotation_available_after, withTime) })} />
                  ) : enc.rotation_waits_for_nodes ? (
                    <Pill tone="muted" icon="clock" label={t('settings.rotationAvailableAfterNodesReload')} />
                  ) : enc.rotation_available && !enc.rotation_in_progress && (
                    <Pill tone="good" label={t('settings.rotationAvailable')} />
                  )}
                </span>
              )],
              enc.total_keys > 0 && [t('settings.encryptedKeys'), enc.encrypted_count],
              enc.total_keys > 0 && [t('settings.unencryptedKeys'), enc.unencrypted_count],
              [t('settings.keyFilesOnDisk'), (
                <span className="row-actions">
                  <span>{enc.key_files_on_disk ?? 0}</span>
                  {enc.enabled && enc.key_files_on_disk > 0 && <Pill tone="warn" label={t('settings.keyFilesRemovalPending')} />}
                </span>
              )],
            ]} />
            {enc.retained_keys?.length > 0 && (
              <Section title={t('settings.retainedDataKeys')}>
                <RecordList>
                  {enc.retained_keys.map((key) => (
                    <RecordRow key={key.version} title={t('settings.retainedDataKey', { version: key.version, date: formatDate(key.retire_after, withTime) })} />
                  ))}
                </RecordList>
                {enc.key_file_kept_for_retained_keys && <p className="group-hint">{t('settings.keyFileRemovedWithRetainedKeys')}</p>}
              </Section>
            )}
            <p className="group-hint">{t('settings.encryptionDesc')}</p>
            {enc.disabling && <Notice tone="warn">{t('settings.encryptionDisablingHint')}</Notice>}
            {enc.enable_available_after ? (
              <p className="group-hint">{t('settings.enableAvailableAfter', { date: formatDate(enc.enable_available_after, withTime) })}</p>
            ) : enc.enable_waits_for_nodes && (
              <p className="group-hint">{t('settings.enableAvailableAfterNodesReload')}</p>
            )}
            {hasPermission('admin:system') && (
              <div className="settings-actions">
                {!enc.enabled ? (
                  <Btn tone="primary" icon="lock" onClick={() => setShowEnableEncryptionModal(true)}
                    disabled={!!enc.enable_available_after || !!enc.enable_waits_for_nodes}>
                    {t('settings.enableEncryption')}
                  </Btn>
                ) : (
                  <>
                    {enc.key_source === 'file' && handleDownloadExistingMasterKey && (
                      <Btn tone="primary" icon="download" write={false} onClick={handleDownloadExistingMasterKey}>{t('settings.backupMasterKey')}</Btn>
                    )}
                    {!enc.disabling && enc.unencrypted_count > 0 && handleEncryptRemainingKeys && (
                      <Btn tone="primary" icon="lock" onClick={handleEncryptRemainingKeys} disabled={encryptionLoading}>
                        {t('settings.encryptRemainingKeys', { count: enc.unencrypted_count })}
                      </Btn>
                    )}
                    {!enc.disabling && handleRotateDataKey && (
                      <Btn icon="key" onClick={handleRotateDataKey}
                        disabled={encryptionLoading || !!enc.rotation_available_after || !!enc.rotation_waits_for_nodes}>
                        {enc.rotation_in_progress ? t('settings.resumeDataKeyRotation') : t('settings.rotateDataKey')}
                      </Btn>
                    )}
                    {/* A key that stays configured (environment, HA) is kept unused */}
                    <Btn icon="lock" write onClick={() => setShowDisableEncryptionModal(true)}>
                      {enc.disabling ? t('settings.runDisableAgain') : t('settings.disableEncryption')}
                    </Btn>
                  </>
                )}
              </div>
            )}
          </>
        ) : (
          <SkeletonPanel label={t('common.loading')} />
        )}
      </SettingsGroup>
      {session && (
        <SettingsGroup legend={t('settings.sessionKeyTitle')} grid={false}>
          <div className="row-actions">
            <Pill tone={session.source === 'database' ? 'good' : 'muted'}
              label={session.source === 'database' ? t('settings.sessionKeyFromDatabase') : t('settings.sessionKeyFromEnvironment')} />
            {session.previous_accepted_until && (
              <Pill tone="muted" icon="clock" label={t('settings.sessionKeyPreviousUntil', { date: formatDate(session.previous_accepted_until, withTime) })} />
            )}
          </div>
          {/* What a rotation really does depends on whether the key can be stored encrypted;
              in HA the environment-file rotation is refused (409 ha_mode) */}
          <p className="group-hint">
            {session.rotation === 'database' ? t('settings.sessionKeyRotateStoredDesc')
              : session.rotation === 'blocked' ? t('settings.sessionKeyRotateBlocked')
                : session.ha ? t('settings.sessionKeyRotateHaRefused') : t('settings.sessionKeyRotateFileDesc')}
          </p>
          {hasPermission('admin:system') && handleRotateSessionKey && (
            <div className="settings-actions">
              <Btn icon="refresh" onClick={handleRotateSessionKey}
                disabled={sessionKeyLoading || !!session.previous_accepted_until || session.rotation === 'blocked'
                  || (session.ha && session.rotation !== 'database')}>
                {t('settings.rotateSessionKey')}
              </Btn>
            </div>
          )}
        </SettingsGroup>
      )}
      <SettingsGroup legend={t('settings.mfaGroup')}>
        <ToggleSwitch id="set-enforce_2fa" checked={settings.enforce_2fa || false} onChange={(val) => updateSetting('enforce_2fa', val)}
          label={t('settings.enforce2fa')} description={t('settings.enforce2faDesc')} disabled={adminLocked} />
      </SettingsGroup>
      <SettingsGroup
        legend={<>{t('settings.adminAllowlistTitle')}{settings.admin_allowlist_disabled
          ? <>{' '}<Pill tone="warn" label={t('settings.adminAllowlistDisabled')} /></>
          : networksList(settings.admin_allowed_networks).length > 0 && <>{' '}<Pill tone="good" label={t('settings.adminAllowlistActive')} /></>}</>}
        hint={t('settings.adminAllowlistDesc')}
      >
        <div className="field full"><Props items={[[t('settings.adminAllowlistYourIp'), settings.admin_client_ip || '—']]} /></div>
        <Textarea id="set-admin_allowed_networks" mono label={t('settings.adminAllowlistNetworks')} value={networksText(settings.admin_allowed_networks)}
          onChange={(e) => updateSetting('admin_allowed_networks', e.target.value)} rows={4} placeholder={'192.168.10.0/24\n2001:db8:10::/64'}
          hint={t('settings.adminAllowlistHelper')} disabled={settings.admin_allowed_networks_env_locked || !canAdminSettings} spellCheck={false} />
        {settings.admin_allowed_networks_env_locked && <Notice tone="warn">{t('settings.adminAllowlistEnvLocked')}</Notice>}
        {settings.admin_allowlist_disabled && <Notice tone="warn">{t('settings.adminAllowlistDisabledNote')}</Notice>}
      </SettingsGroup>
      <SettingsGroup legend={t('settings.hstsTitle')}>
        <ToggleSwitch id="set-hsts_enabled" checked={settings.hsts_enabled !== false} onChange={(val) => updateSetting('hsts_enabled', val)}
          label={t('settings.hstsEnabled')} description={t('settings.hstsEnabledDesc')}
          disabled={adminLocked || settings.hsts_env_locked?.includes('hsts_enabled')} />
        {settings.hsts_enabled !== false && (
          <>
            <ToggleSwitch id="set-hsts_include_subdomains" checked={settings.hsts_include_subdomains !== false}
              onChange={(val) => updateSetting('hsts_include_subdomains', val)} label={t('settings.hstsIncludeSubdomains')}
              description={t('settings.hstsIncludeSubdomainsDesc')} disabled={adminLocked || settings.hsts_env_locked?.includes('hsts_include_subdomains')} />
            <NumberInput id="set-hsts_max_age" label={lockedLabel('settings.hstsMaxAge')} value={shownNumber(settings.hsts_max_age ?? 31536000)}
              onChange={(e) => updateSetting('hsts_max_age', typedNumber(e))} hint={t('settings.hstsMaxAgeDesc')}
              disabled={adminLocked || settings.hsts_env_locked?.includes('hsts_max_age')} error={fieldErrors.hsts_max_age} />
          </>
        )}
        {settings.hsts_env_locked?.length > 0 && <Notice tone="warn">{t('settings.hstsEnvLocked')}</Notice>}
        {settings.hsts_env_locked?.length === 0 && <Notice>{t('settings.hstsNote')}</Notice>}
        <NumberInput id="set-ocsp_response_validity_hours" label={t('settings.ocspResponseValidity')}
          value={shownNumber(settings.ocsp_response_validity_hours ?? 24)} onChange={(e) => updateSetting('ocsp_response_validity_hours', typedNumber(e))}
          hint={t('settings.ocspResponseValidityDesc')} error={fieldErrors.ocsp_response_validity_hours} />
        <ToggleSwitch id="set-ocsp_responder_auto_renew" checked={settings.ocsp_responder_auto_renew ?? true}
          onChange={(val) => updateSetting('ocsp_responder_auto_renew', val)} label={t('settings.ocspResponderAutoRenew')}
          description={t('settings.ocspResponderAutoRenewDesc')} disabled={canAdminSettings === false} />
        {(settings.ocsp_responder_auto_renew ?? true) && (
          <NumberInput id="set-ocsp_responder_renew_days" label={t('settings.ocspResponderRenewDays')}
            value={shownNumber(settings.ocsp_responder_renew_days ?? 30)} onChange={(e) => updateSetting('ocsp_responder_renew_days', typedNumber(e))}
            hint={t('settings.ocspResponderRenewDaysDesc')} disabled={canAdminSettings === false} error={fieldErrors.ocsp_responder_renew_days} />
        )}
        <ToggleSwitch id="set-crl_auto_delete_expired_revoked" checked={settings.crl_auto_delete_expired_revoked === true}
          onChange={(val) => updateSetting('crl_auto_delete_expired_revoked', val)} label={t('settings.crlAutoDeleteExpiredRevoked')}
          description={t('settings.crlAutoDeleteExpiredRevokedDesc')} disabled={adminLocked} />
        <ToggleSwitch id="set-crl_auto_purge_stale_serials" checked={settings.crl_auto_purge_stale_serials === true}
          onChange={(val) => updateSetting('crl_auto_purge_stale_serials', val)} label={t('settings.crlAutoPurgeStaleSerials')}
          description={t('settings.crlAutoPurgeStaleSerialsDesc')} disabled={adminLocked} />
      </SettingsGroup>
      <SettingsGroup legend={t('settings.keyRecoveryTitle')}>
        <ToggleSwitch id="set-key_recovery_dual_control" checked={settings.key_recovery_dual_control !== false}
          onChange={(val) => updateSetting('key_recovery_dual_control', val)} label={t('settings.keyRecoveryDualControl')}
          description={t('settings.keyRecoveryDualControlDesc')} disabled={adminLocked || settings.key_recovery_dual_control_locked} />
        {settings.key_recovery_dual_control_locked && <Notice tone="warn">{t('settings.keyRecoveryDualControlLocked')}</Notice>}
      </SettingsGroup>
      <SettingsGroup legend={t('settings.passwordPolicy')}>
        <NumberInput id="set-min_password_length" label={lockedLabel('settings.minPasswordLength')} disabled={adminLocked}
          value={shownNumber(settings.min_password_length ?? 8, (n) => n || 8)} onChange={(e) => updateSetting('min_password_length', typedNumber(e))}
          error={fieldErrors.min_password_length} />
        <ToggleSwitch id="set-password_require_uppercase" checked={settings.password_require_uppercase || false}
          onChange={(val) => updateSetting('password_require_uppercase', val)} label={t('settings.requireUppercase')} disabled={adminLocked} />
        <ToggleSwitch id="set-password_require_numbers" checked={settings.password_require_numbers || false}
          onChange={(val) => updateSetting('password_require_numbers', val)} label={t('settings.requireNumbers')} disabled={adminLocked} />
        <ToggleSwitch id="set-password_require_special" checked={settings.password_require_special || false}
          onChange={(val) => updateSetting('password_require_special', val)} label={t('settings.requireSpecial')} disabled={adminLocked} />
      </SettingsGroup>
      <SettingsGroup grid={false}
        legend={<>{t('settings.anomalyDetection')}{anomalies.length > 0 && <>{' '}<Pill tone="warn" label={String(anomalies.length)} /></>}</>}>
        {anomaliesLoading ? (
          <SkeletonPanel label={t('common.loading')} />
        ) : (
          <RecordList empty={`${t('settings.noAnomalies')}. ${t('settings.noAnomaliesDesc')}`}>
            {anomalies.map((anomaly, i) => (
              <RecordRow key={i} title={anomaly.details?.type || t('settings.unknownAnomaly')}
                meta={[formatDate(anomaly.timestamp), anomaly.details?.ip, anomaly.details?.user_id && `#${anomaly.details.user_id}`].filter(Boolean).join(' · ')}
                extra={anomaly.details?.message && <span className="rl-meta">{anomaly.details.message}</span>}
                badge={<Pill tone={anomaly.details?.severity === 'high' ? 'bad' : 'warn'}
                  label={anomaly.details?.severity === 'high' ? t('settings.anomalyHigh') : t('settings.anomalyWarn')} />} />
            ))}
          </RecordList>
        )}
        <div className="settings-actions">
          <Btn icon="refresh" onClick={loadAnomalies} disabled={anomaliesLoading}>{t('common.refresh')}</Btn>
        </div>
      </SettingsGroup>
      <SettingsGroup legend={t('settings.sessionRateLimits')}>
        <NumberInput id="set-session_max_lifetime" label={lockedLabel('settings.sessionDuration')} disabled={adminLocked}
          value={shownNumber(settings.session_max_lifetime ?? 86400, (s) => Math.round((s || 86400) / 3600))}
          onChange={(e) => updateSetting('session_max_lifetime', typedNumber(e, (h) => h * 3600))}
          hint={t('settings.sessionDurationHelper')} error={fieldErrors.session_max_lifetime} />
      </SettingsGroup>
      <SettingsGroup legend={<>{t('settings.mtls.title')}{' '}<Pill tone="warn" icon="sparkles" label={t('common.experimental')} /></>}>
        {mtlsLoading ? (
          <div className="field full"><SkeletonPanel label={t('common.loading')} /></div>
        ) : (
          <>
            <ToggleSwitch id="set-mtls_enabled" checked={mtlsSettings.enabled || false}
              onChange={(val) => setMtlsSettings((prev) => ({ ...prev, enabled: val }))} label={t('settings.mtls.enable')} />
            {mtlsSettings.enabled && (
              <>
                <Select id="set-mtls_trusted_ca_id" label={t('settings.mtls.trustedCA')} value={mtlsSettings.trusted_ca_id || ''}
                  onChange={(val) => setMtlsSettings((prev) => ({ ...prev, trusted_ca_id: val }))} placeholder={t('settings.mtls.selectCA')}
                  options={anchorPickerCas(cas, mtlsSettings.trusted_ca_id).map((ca) => ({ value: ca.refid, label: ca.descr || ca.subject || ca.refid }))} />
                <ToggleSwitch id="set-mtls_required" checked={mtlsSettings.required || false}
                  onChange={(val) => setMtlsSettings((prev) => ({ ...prev, required: val }))} label={t('settings.mtls.required')} />
                {mtlsSettings.required && <Notice tone="warn">{t('settings.mtls.requiredWarning')}</Notice>}
                <Notice>{t('settings.mtls.restartNote')}</Notice>
              </>
            )}
          </>
        )}
      </SettingsGroup>
    </>
  )
}
