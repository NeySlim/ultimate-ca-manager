import { useTranslation } from 'react-i18next'
import { ShieldCheck, Lock, LockKey, Warning, Timer, Globe, Clock, CheckCircle, ArrowsClockwise, WarningCircle, FloppyDisk, User } from '@phosphor-icons/react'
import { Button, Input, Select, Badge, LoadingSpinner, ExperimentalBadge, DetailHeader, DetailSection, DetailGrid, DetailContent } from '../../components'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import { formatDate } from '../../lib/utils'

export default function SecuritySection({ settings, updateSetting, handleSave, saving, hasPermission, encryptionStatus, setShowEnableEncryptionModal, setShowDisableEncryptionModal, anomalies, anomaliesLoading, loadAnomalies, mtlsSettings, setMtlsSettings, mtlsLoading, mtlsSaving, handleMtlsSave, cas }) {
  const { t } = useTranslation()
  return (
    <DetailContent>
      <DetailHeader
        icon={ShieldCheck}
        title={t('common.securitySettings')}
        subtitle={t('settings.securitySubtitle')}
      />
      <DetailSection title={t('settings.keyEncryption')} icon={LockKey} iconClass="icon-bg-rose">
        {encryptionStatus ? (
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <Badge variant={encryptionStatus.enabled ? 'success' : 'warning'}>
                {encryptionStatus.enabled ? t('common.enabled') : t('common.disabled')}
              </Badge>
              {encryptionStatus.enabled && encryptionStatus.key_source && (
                <span className="text-xs text-text-tertiary">
                  {t('settings.keySource')}: {encryptionStatus.key_file_path}
                </span>
              )}
            </div>
            
            {encryptionStatus.total_keys > 0 && (
              <div className="flex gap-4 text-sm">
                <span className="text-text-secondary">
                  {t('settings.encryptedKeys')}: <strong className="text-text-primary">{encryptionStatus.encrypted_count}</strong>
                </span>
                <span className="text-text-secondary">
                  {t('settings.unencryptedKeys')}: <strong className="text-text-primary">{encryptionStatus.unencrypted_count}</strong>
                </span>
              </div>
            )}

            <p className="text-xs text-text-secondary">{t('settings.encryptionDesc')}</p>

            {hasPermission('admin:system') && (
              <div>
                {!encryptionStatus.enabled ? (
                  <Button 
                    onClick={() => setShowEnableEncryptionModal(true)}
                    variant="primary"
                  >
                    <LockKey size={16} />
                    {t('settings.enableEncryption')}
                  </Button>
                ) : (
                  <Button 
                    onClick={() => setShowDisableEncryptionModal(true)}
                    variant="outline"
                  >
                    <Lock size={16} />
                    {t('settings.disableEncryption')}
                  </Button>
                )}
              </div>
            )}
          </div>
        ) : (
          <LoadingSpinner size="sm" />
        )}
      </DetailSection>
      <DetailSection title={t('common.twoFactorAuth')} icon={ShieldCheck} iconClass="icon-bg-emerald">
        <ToggleSwitch
          checked={settings.enforce_2fa || false}
          onChange={(val) => updateSetting('enforce_2fa', val)}
          label={t('settings.enforce2fa')}
          description={t('settings.enforce2faDesc')}
        />
      </DetailSection>
      <DetailSection title={t('settings.passwordPolicy')} icon={Lock} iconClass="icon-bg-violet">
        <div className="space-y-4">
          <Input
            label={t('settings.minPasswordLength')}
            type="number"
            value={settings.min_password_length || 8}
            onChange={(e) => updateSetting('min_password_length', parseInt(e.target.value))}
            min="6"
            max="32"
          />
          <div className="space-y-2">
            <ToggleSwitch
              checked={settings.password_require_uppercase || false}
              onChange={(val) => updateSetting('password_require_uppercase', val)}
              label={t('settings.requireUppercase')}
              size="sm"
            />
            <ToggleSwitch
              checked={settings.password_require_numbers || false}
              onChange={(val) => updateSetting('password_require_numbers', val)}
              label={t('settings.requireNumbers')}
              size="sm"
            />
            <ToggleSwitch
              checked={settings.password_require_special || false}
              onChange={(val) => updateSetting('password_require_special', val)}
              label={t('settings.requireSpecial')}
              size="sm"
            />
          </div>
        </div>
      </DetailSection>
      <DetailSection title={t('settings.anomalyDetection')} icon={Warning} iconClass="icon-bg-orange"
        badge={anomalies.length > 0 ? anomalies.length : null}
        badgeColor={anomalies.length > 0 ? 'warning' : undefined}
      >
        <div className="space-y-3">
          {anomaliesLoading ? (
            <LoadingSpinner size="sm" />
          ) : anomalies.length === 0 ? (
            <div className="flex items-center gap-3 p-3 rounded-lg bg-status-success-op10">
              <CheckCircle size={20} weight="fill" className="text-status-success" />
              <div>
                <div className="text-sm font-medium text-text-primary">{t('settings.noAnomalies')}</div>
                <div className="text-xs text-text-secondary">{t('settings.noAnomaliesDesc')}</div>
              </div>
            </div>
          ) : (
            anomalies.map((anomaly, i) => (
              <div key={i} className={`p-3 rounded-lg flex items-start gap-3 ${anomaly.details?.severity === 'high' ? 'bg-status-danger-op10' : 'bg-status-warning-op10'}`}>
                <Warning size={18} weight="fill" className={anomaly.details?.severity === 'high' ? 'text-status-danger' : 'text-status-warning'} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-text-primary">{anomaly.details?.type || t('settings.unknownAnomaly')}</div>
                  <div className="text-xs text-text-secondary">{anomaly.details?.message}</div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-text-tertiary">
                    <span className="flex items-center gap-1">
                      <Clock size={12} />
                      {formatDate(anomaly.timestamp)}
                    </span>
                    {anomaly.details?.ip && (
                      <span className="flex items-center gap-1">
                        <Globe size={12} />
                        {anomaly.details.ip}
                      </span>
                    )}
                    {anomaly.details?.user_id && (
                      <span className="flex items-center gap-1">
                        <User size={12} />
                        #{anomaly.details.user_id}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
          <Button type="button" variant="secondary" size="sm" onClick={loadAnomalies} loading={anomaliesLoading}>
            <ArrowsClockwise size={14} />
            {t('common.refresh')}
          </Button>
        </div>
      </DetailSection>
      <DetailSection title={t('settings.sessionRateLimits')} icon={Timer} iconClass="icon-bg-teal">
        <DetailGrid>
          <div className="col-span-full md:col-span-1">
            <Input
              label={t('settings.sessionDuration')}
              type="number"
              value={Math.round((settings.session_max_lifetime || 86400) / 3600)}
              onChange={(e) => updateSetting('session_max_lifetime', parseInt(e.target.value) * 3600)}
              min="1"
              max="720"
              helperText={t('settings.sessionDurationHelper')}
            />
          </div>
          <div className="col-span-full md:col-span-1">
            <Input
              label={t('settings.apiRateLimit')}
              type="number"
              value={settings.api_rate_limit || 60}
              onChange={(e) => updateSetting('api_rate_limit', parseInt(e.target.value))}
              min="10"
              max="1000"
            />
          </div>
        </DetailGrid>
        {hasPermission('admin:system') && (
          <div className="pt-4">
            <Button type="button" onClick={() => handleSave('security')} disabled={saving}>
              <FloppyDisk size={16} />
              {t('common.saveChanges')}
            </Button>
          </div>
        )}
      </DetailSection>
      <DetailSection title={t('settings.mtls.title')} icon={ShieldCheck} iconClass="icon-bg-violet" badge={<ExperimentalBadge />}>
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
                  options={cas.filter(ca => ca.has_private_key !== false).map(ca => ({
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
                  <div className="flex items-start gap-2 p-3 rounded-lg bg-status-warning-op10 text-xs text-status-warning">
                    <WarningCircle size={16} weight="fill" className="flex-shrink-0 mt-0.5" />
                    <span>{t('settings.mtls.requiredWarning')}</span>
                  </div>
                )}
                <p className="text-xs text-text-tertiary">{t('settings.mtls.restartNote')}</p>
              </>
            )}
            {hasPermission('admin:system') && (
              <Button type="button" onClick={handleMtlsSave} disabled={mtlsSaving} loading={mtlsSaving}>
                <FloppyDisk size={16} />
                {t('common.saveChanges')}
              </Button>
            )}
          </div>
        )}
      </DetailSection>
    </DetailContent>
  )
}
