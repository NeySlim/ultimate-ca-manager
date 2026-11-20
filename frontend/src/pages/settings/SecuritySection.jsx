import { useTranslation } from 'react-i18next'
import { Lock, LockKey, ArrowsClockwise, Download } from '@phosphor-icons/react'
import { Button, Input, Select, Textarea, Badge, LoadingSpinner, ExperimentalBadge } from '../../components'
import { HelpCard } from '../../components/HelpCard'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import { formatDate } from '../../lib/utils'
import { anchorPickerCas } from '../../lib/caSelection'
import AdminLockLabel from './AdminLockLabel'
import { fieldBounds } from './fieldChecks'
import { FormGroup, FormProps } from '../../components/sectioned'

// The API sends a list; the textarea edits one entry per line.
function networksText(value) {
  return Array.isArray(value) ? value.join('\n') : (value || '')
}

function networksList(value) {
  return networksText(value).split(/[\s,;]+/).filter(Boolean)
}

export default function SecuritySection({ settings, fieldErrors = {}, updateSetting, hasPermission, encryptionStatus, setShowEnableEncryptionModal, setShowDisableEncryptionModal, handleDownloadExistingMasterKey, handleEncryptRemainingKeys, handleRotateDataKey, encryptionLoading, secretsStatus, handleRotateSessionKey, sessionKeyLoading, anomalies, anomaliesLoading, loadAnomalies, mtlsSettings, setMtlsSettings, mtlsLoading, cas }) {
  const { t } = useTranslation()
  // Fields the API writes for admin:settings only are shown, but disabled.
  const canAdminSettings = Boolean(hasPermission('admin:settings'))
  const adminLocked = !canAdminSettings
  return (
    <>
      <FormGroup title={t('settings.keyEncryption')}>
        {encryptionStatus ? (
          <div className="sf-stack">
            <FormProps items={[
              [t('common.status'), encryptionStatus.disabling ? (
                <Badge variant="warning">{t('settings.encryptionDisabling')}</Badge>
              ) : (
                <Badge variant={encryptionStatus.enabled ? 'success' : 'warning'}>
                  {encryptionStatus.enabled ? t('common.enabled') : t('common.disabled')}
                </Badge>
              )],
              encryptionStatus.enabled && encryptionStatus.key_source
                && [t('settings.keySource'), encryptionStatus.key_file_path],
              encryptionStatus.enabled && encryptionStatus.kek_fingerprint
                && [t('settings.kekFingerprint'), encryptionStatus.kek_fingerprint],
              encryptionStatus.enabled && encryptionStatus.kek_fingerprint && [t('settings.dekVersion'), (
                <span className="sf-record-title">
                  <span>{encryptionStatus.dek_version}</span>
                  {encryptionStatus.rotation_in_progress && (
                    <Badge variant="warning">{t('settings.dekRotationInProgress')}</Badge>
                  )}
                  {encryptionStatus.rotation_available_after ? (
                    <Badge variant="secondary">
                      {t('settings.rotationAvailableAfter', { date: formatDate(encryptionStatus.rotation_available_after, { hour: '2-digit', minute: '2-digit' }) })}
                    </Badge>
                  ) : encryptionStatus.rotation_waits_for_nodes ? (
                    <Badge variant="secondary">{t('settings.rotationAvailableAfterNodesReload')}</Badge>
                  ) : encryptionStatus.rotation_available && !encryptionStatus.rotation_in_progress && (
                    <Badge variant="success">{t('settings.rotationAvailable')}</Badge>
                  )}
                </span>
              )],
              encryptionStatus.total_keys > 0 && [t('settings.encryptedKeys'), encryptionStatus.encrypted_count],
              encryptionStatus.total_keys > 0 && [t('settings.unencryptedKeys'), encryptionStatus.unencrypted_count],
              [t('settings.keyFilesOnDisk'), (
                <span className="sf-record-title">
                  <span>{encryptionStatus.key_files_on_disk ?? 0}</span>
                  {encryptionStatus.enabled && encryptionStatus.key_files_on_disk > 0 && (
                    <Badge variant="warning">{t('settings.keyFilesRemovalPending')}</Badge>
                  )}
                </span>
              )],
            ]} />

            {encryptionStatus.retained_keys?.length > 0 && (
              <div className="sf-hint">
                <p>{t('settings.retainedDataKeys')}</p>
                <ul className="list-disc pl-5">
                  {encryptionStatus.retained_keys.map((key) => (
                    <li key={key.version}>
                      {t('settings.retainedDataKey', { version: key.version, date: formatDate(key.retire_after, { hour: '2-digit', minute: '2-digit' }) })}
                    </li>
                  ))}
                </ul>
                {encryptionStatus.key_file_kept_for_retained_keys && (
                  <p>{t('settings.keyFileRemovedWithRetainedKeys')}</p>
                )}
              </div>
            )}

            <p className="sf-hint">{t('settings.encryptionDesc')}</p>

            {encryptionStatus.disabling && (
              <HelpCard variant="warning">{t('settings.encryptionDisablingHint')}</HelpCard>
            )}

            {encryptionStatus.enable_available_after ? (
              <p className="sf-hint">
                {t('settings.enableAvailableAfter', { date: formatDate(encryptionStatus.enable_available_after, { hour: '2-digit', minute: '2-digit' }) })}
              </p>
            ) : encryptionStatus.enable_waits_for_nodes && (
              <p className="sf-hint">{t('settings.enableAvailableAfterNodesReload')}</p>
            )}

            {hasPermission('admin:system') && (
              <div>
                {!encryptionStatus.enabled ? (
                  <Button
                    onClick={() => setShowEnableEncryptionModal(true)}
                    variant="primary"
                    disabled={!!encryptionStatus.enable_available_after || !!encryptionStatus.enable_waits_for_nodes}
                  >
                    <LockKey size={16} />
                    {t('settings.enableEncryption')}
                  </Button>
                ) : (
                  <div className="sf-actions-row">
                    {encryptionStatus.key_source === 'file' && handleDownloadExistingMasterKey && (
                      <Button
                        onClick={handleDownloadExistingMasterKey}
                        variant="primary"
                      >
                        <Download size={16} />
                        {t('settings.backupMasterKey')}
                      </Button>
                    )}
                    {!encryptionStatus.disabling && encryptionStatus.unencrypted_count > 0 && handleEncryptRemainingKeys && (
                      <Button
                        onClick={handleEncryptRemainingKeys}
                        variant="primary"
                        disabled={encryptionLoading}
                      >
                        <LockKey size={16} />
                        {t('settings.encryptRemainingKeys', { count: encryptionStatus.unencrypted_count })}
                      </Button>
                    )}
                    {!encryptionStatus.disabling && handleRotateDataKey && (
                      <Button
                        onClick={handleRotateDataKey}
                        variant="outline"
                        disabled={encryptionLoading || !!encryptionStatus.rotation_available_after || !!encryptionStatus.rotation_waits_for_nodes}
                      >
                        <LockKey size={16} />
                        {encryptionStatus.rotation_in_progress
                          ? t('settings.resumeDataKeyRotation')
                          : t('settings.rotateDataKey')}
                      </Button>
                    )}
                    {/* A key that stays configured (environment, HA) is kept unused */}
                    <Button
                      onClick={() => setShowDisableEncryptionModal(true)}
                      variant="outline"
                      data-write
                    >
                      <Lock size={16} />
                      {encryptionStatus.disabling ? t('settings.runDisableAgain') : t('settings.disableEncryption')}
                    </Button>
                  </div>
                )}
              </div>
            )}
          </div>
        ) : (
          <LoadingSpinner size="sm" />
        )}
      </FormGroup>
      {secretsStatus?.session_secret && (
        <FormGroup title={t('settings.sessionKeyTitle')}>
          <div className="sf-stack">
            <div className="sf-record-title">
              <Badge variant={secretsStatus.session_secret.source === 'database' ? 'success' : 'secondary'}>
                {secretsStatus.session_secret.source === 'database'
                  ? t('settings.sessionKeyFromDatabase')
                  : t('settings.sessionKeyFromEnvironment')}
              </Badge>
              {secretsStatus.session_secret.previous_accepted_until && (
                <Badge variant="secondary">
                  {t('settings.sessionKeyPreviousUntil', { date: formatDate(secretsStatus.session_secret.previous_accepted_until, { hour: '2-digit', minute: '2-digit' }) })}
                </Badge>
              )}
            </div>
            {/* What a rotation really does depends on whether the key can be stored encrypted;
                in HA the environment-file rotation is refused (409 ha_mode) */}
            <p className="sf-hint">
              {secretsStatus.session_secret.rotation === 'database'
                ? t('settings.sessionKeyRotateStoredDesc')
                : secretsStatus.session_secret.rotation === 'blocked'
                  ? t('settings.sessionKeyRotateBlocked')
                : secretsStatus.session_secret.ha
                  ? t('settings.sessionKeyRotateHaRefused')
                  : t('settings.sessionKeyRotateFileDesc')}
            </p>
            {hasPermission('admin:system') && handleRotateSessionKey && (
              <Button
                onClick={handleRotateSessionKey}
                variant="outline"
                disabled={sessionKeyLoading || !!secretsStatus.session_secret.previous_accepted_until
                  || secretsStatus.session_secret.rotation === 'blocked'
                  || (secretsStatus.session_secret.ha && secretsStatus.session_secret.rotation !== 'database')}
              >
                <ArrowsClockwise size={16} />
                {t('settings.rotateSessionKey')}
              </Button>
            )}
          </div>
        </FormGroup>
      )}
      <FormGroup title={t('settings.mfaGroup')}>
        <div className="space-y-4">
          <ToggleSwitch
            checked={settings.enforce_2fa || false}
            onChange={(val) => updateSetting('enforce_2fa', val)}
            label={t('settings.enforce2fa')}
            description={t('settings.enforce2faDesc')}
            disabled={adminLocked}
          />
        </div>
      </FormGroup>
      <FormGroup
        title={t('settings.adminAllowlistTitle')}
        badge={settings.admin_allowlist_disabled
          ? <Badge variant="warning">{t('settings.adminAllowlistDisabled')}</Badge>
          : (networksList(settings.admin_allowed_networks).length > 0
            ? <Badge variant="success">{t('settings.adminAllowlistActive')}</Badge>
            : null)}
      >
        <div className="space-y-4">
          <p className="sf-hint">{t('settings.adminAllowlistDesc')}</p>
          <FormProps items={[[t('settings.adminAllowlistYourIp'), settings.admin_client_ip || '—']]} />
          <Textarea
            label={t('settings.adminAllowlistNetworks')}
            value={networksText(settings.admin_allowed_networks)}
            onChange={(e) => updateSetting('admin_allowed_networks', e.target.value)}
            rows={4}
            placeholder={'192.168.10.0/24\n2001:db8:10::/64'}
            helperText={t('settings.adminAllowlistHelper')}
            disabled={settings.admin_allowed_networks_env_locked || !canAdminSettings}
            spellCheck={false}
          />
          {settings.admin_allowed_networks_env_locked && (
            <HelpCard variant="warning">{t('settings.adminAllowlistEnvLocked')}</HelpCard>
          )}
          {settings.admin_allowlist_disabled && (
            <HelpCard variant="warning">{t('settings.adminAllowlistDisabledNote')}</HelpCard>
          )}
        </div>
      </FormGroup>
      <FormGroup title={t('settings.hstsTitle')}>
        <div className="space-y-4">
          <ToggleSwitch
            checked={settings.hsts_enabled !== false}
            onChange={(val) => updateSetting('hsts_enabled', val)}
            label={t('settings.hstsEnabled')}
            description={t('settings.hstsEnabledDesc')}
            disabled={adminLocked || settings.hsts_env_locked?.includes('hsts_enabled')}
          />
          {settings.hsts_enabled !== false && (
            <>
              <ToggleSwitch
                checked={settings.hsts_include_subdomains !== false}
                onChange={(val) => updateSetting('hsts_include_subdomains', val)}
                label={t('settings.hstsIncludeSubdomains')}
                description={t('settings.hstsIncludeSubdomainsDesc')}
                disabled={adminLocked || settings.hsts_env_locked?.includes('hsts_include_subdomains')}
              />
              <Input
            className="sf-short"
                label={<AdminLockLabel text={t('settings.hstsMaxAge')} locked={adminLocked} />}
                type="number"
                value={settings.hsts_max_age ?? 31536000}
                onChange={(e) => updateSetting('hsts_max_age', parseInt(e.target.value))}
                helperText={t('settings.hstsMaxAgeDesc')}
                disabled={adminLocked || settings.hsts_env_locked?.includes('hsts_max_age')}
                {...fieldBounds('hsts_max_age')}
                error={fieldErrors['hsts_max_age']}
              />
            </>
          )}
          {settings.hsts_env_locked?.length > 0 && (
            <HelpCard variant="warning">{t('settings.hstsEnvLocked')}</HelpCard>
          )}
          {settings.hsts_env_locked?.length === 0 && (
            <HelpCard variant="info">{t('settings.hstsNote')}</HelpCard>
          )}

          <Input
            className="sf-short"
            label={t('settings.ocspResponseValidity')}
            type="number"
            value={settings.ocsp_response_validity_hours ?? 24}
            onChange={(e) => updateSetting('ocsp_response_validity_hours', parseInt(e.target.value))}
            helperText={t('settings.ocspResponseValidityDesc')}
            {...fieldBounds('ocsp_response_validity_hours')}
            error={fieldErrors['ocsp_response_validity_hours']}
          />
          <ToggleSwitch
            checked={settings.ocsp_responder_auto_renew ?? true}
            onChange={(val) => updateSetting('ocsp_responder_auto_renew', val)}
            label={t('settings.ocspResponderAutoRenew')}
            description={t('settings.ocspResponderAutoRenewDesc')}
            disabled={canAdminSettings === false}
          />
          {(settings.ocsp_responder_auto_renew ?? true) && (
            <Input
            className="sf-short"
              label={t('settings.ocspResponderRenewDays')}
              type="number"
              value={settings.ocsp_responder_renew_days ?? 30}
              onChange={(e) => updateSetting('ocsp_responder_renew_days', parseInt(e.target.value))}
              helperText={t('settings.ocspResponderRenewDaysDesc')}
              disabled={canAdminSettings === false}
              {...fieldBounds('ocsp_responder_renew_days')}
              error={fieldErrors['ocsp_responder_renew_days']}
            />
          )}
          <ToggleSwitch
            checked={settings.crl_auto_delete_expired_revoked === true}
            onChange={(val) => updateSetting('crl_auto_delete_expired_revoked', val)}
            label={t('settings.crlAutoDeleteExpiredRevoked')}
            description={t('settings.crlAutoDeleteExpiredRevokedDesc')}
            disabled={adminLocked}
          />
          <ToggleSwitch
            checked={settings.crl_auto_purge_stale_serials === true}
            onChange={(val) => updateSetting('crl_auto_purge_stale_serials', val)}
            label={t('settings.crlAutoPurgeStaleSerials')}
            description={t('settings.crlAutoPurgeStaleSerialsDesc')}
            disabled={adminLocked}
          />
        </div>
      </FormGroup>
      <FormGroup title={t('settings.keyRecoveryTitle')}>
        <div className="space-y-3">
          <ToggleSwitch
            checked={settings.key_recovery_dual_control !== false}
            onChange={(val) => updateSetting('key_recovery_dual_control', val)}
            label={t('settings.keyRecoveryDualControl')}
            description={t('settings.keyRecoveryDualControlDesc')}
            disabled={adminLocked || settings.key_recovery_dual_control_locked}
          />
          {settings.key_recovery_dual_control_locked && (
            <HelpCard variant="warning">{t('settings.keyRecoveryDualControlLocked')}</HelpCard>
          )}
        </div>
      </FormGroup>
      <FormGroup title={t('settings.passwordPolicy')}>
        <div className="space-y-4">
          <Input
            className="sf-short"
            label={<AdminLockLabel text={t('settings.minPasswordLength')} locked={adminLocked} />}
            disabled={adminLocked}
            type="number"
            value={settings.min_password_length || 8}
            onChange={(e) => updateSetting('min_password_length', parseInt(e.target.value))}
            {...fieldBounds('min_password_length')}
            error={fieldErrors['min_password_length']}
          />
          <div className="space-y-2">
            <ToggleSwitch
              checked={settings.password_require_uppercase || false}
              onChange={(val) => updateSetting('password_require_uppercase', val)}
              label={t('settings.requireUppercase')}
              size="sm"
              disabled={adminLocked}
            />
            <ToggleSwitch
              checked={settings.password_require_numbers || false}
              onChange={(val) => updateSetting('password_require_numbers', val)}
              label={t('settings.requireNumbers')}
              size="sm"
              disabled={adminLocked}
            />
            <ToggleSwitch
              checked={settings.password_require_special || false}
              onChange={(val) => updateSetting('password_require_special', val)}
              label={t('settings.requireSpecial')}
              size="sm"
              disabled={adminLocked}
            />
          </div>
        </div>
      </FormGroup>
      <FormGroup title={t('settings.anomalyDetection')}
        badge={anomalies.length > 0 ? anomalies.length : null}
        badgeColor={anomalies.length > 0 ? 'warning' : undefined}
      >
        <div className="space-y-3">
          {anomaliesLoading ? (
            <LoadingSpinner size="sm" />
          ) : anomalies.length === 0 ? (
            <p className="sf-records-empty">{t('settings.noAnomalies')}. {t('settings.noAnomaliesDesc')}</p>
          ) : (
            <ul className="sf-records">
              {anomalies.map((anomaly, i) => (
                <li key={i}>
                  <div className="sf-record-main">
                    <span className="sf-record-title">
                      <strong>{anomaly.details?.type || t('settings.unknownAnomaly')}</strong>
                      <Badge variant={anomaly.details?.severity === 'high' ? 'danger' : 'warning'}>
                        {anomaly.details?.severity === 'high' ? t('settings.anomalyHigh') : t('settings.anomalyWarn')}
                      </Badge>
                    </span>
                    {anomaly.details?.message && <span className="sf-record-meta">{anomaly.details.message}</span>}
                    <span className="sf-record-meta">
                      {[formatDate(anomaly.timestamp), anomaly.details?.ip, anomaly.details?.user_id && `#${anomaly.details.user_id}`]
                        .filter(Boolean).join(' · ')}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <Button type="button" variant="secondary" onClick={loadAnomalies} loading={anomaliesLoading}>
            <ArrowsClockwise size={16} />
            {t('common.refresh')}
          </Button>
        </div>
      </FormGroup>
      <FormGroup title={t('settings.sessionRateLimits')}>
        <div className="sf-grid">
            <Input
            className="sf-short"
              label={<AdminLockLabel text={t('settings.sessionDuration')} locked={adminLocked} />}
              disabled={adminLocked}
              type="number"
              value={Math.round((settings.session_max_lifetime || 86400) / 3600)}
              onChange={(e) => updateSetting('session_max_lifetime', parseInt(e.target.value) * 3600)}
              helperText={t('settings.sessionDurationHelper')}
              {...fieldBounds('session_max_lifetime')}
              error={fieldErrors['session_max_lifetime']}
            />
        </div>
      </FormGroup>
      <FormGroup title={t('settings.mtls.title')} badge={<ExperimentalBadge />}>
        {mtlsLoading ? (
          <LoadingSpinner size="sm" />
        ) : (
          <div className="space-y-4">
            <ToggleSwitch
              checked={mtlsSettings.enabled || false}
              onChange={(val) => setMtlsSettings(prev => ({ ...prev, enabled: val }))}
              label={t('settings.mtls.enable')}
              size="sm"
            />
            {mtlsSettings.enabled && (
              <>
                <Select
                  label={t('settings.mtls.trustedCA')}
                  value={mtlsSettings.trusted_ca_id || ''}
                  onChange={(val) => setMtlsSettings(prev => ({ ...prev, trusted_ca_id: val }))}
                  placeholder={t('settings.mtls.selectCA')}
                  options={anchorPickerCas(cas, mtlsSettings.trusted_ca_id).map(ca => ({
                    value: ca.refid,
                    label: ca.descr || ca.subject || ca.refid,
                  }))}
                />
                <ToggleSwitch
                  checked={mtlsSettings.required || false}
                  onChange={(val) => setMtlsSettings(prev => ({ ...prev, required: val }))}
                  label={t('settings.mtls.required')}
                  size="sm"
                />
                {mtlsSettings.required && (
                  <HelpCard variant="warning">{t('settings.mtls.requiredWarning')}</HelpCard>
                )}
                <p className="sf-hint">{t('settings.mtls.restartNote')}</p>
              </>
            )}
          </div>
        )}
      </FormGroup>
    </>
  )
}
