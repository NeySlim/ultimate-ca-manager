import { useTranslation } from 'react-i18next'
import { ListBullets, Eye, Globe, FloppyDisk, Lightning } from '@phosphor-icons/react'
import { Button, Input, Select, DetailHeader, DetailSection, DetailContent } from '../../components'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'

export default function AuditSection({ settings, updateSetting, handleSave, saving, hasPermission, syslogConfig, updateSyslogConfig, syslogSaving, syslogTesting, handleSaveSyslog, handleTestSyslog }) {
  const { t } = useTranslation()
  return (
    <DetailContent>
      <DetailHeader
        icon={ListBullets}
        title={t('settings.auditTitle')}
        subtitle={t('settings.auditSubtitle')}
      />
      <DetailSection title={t('settings.auditLogging')} icon={ListBullets} iconClass="icon-bg-orange">
        <div className="space-y-4">
          <ToggleSwitch
            checked={settings.audit_enabled || true}
            onChange={(val) => updateSetting('audit_enabled', val)}
            label={t('settings.enableAuditLogging')}
            description={t('settings.enableAuditLoggingDesc')}
          />

          <Input
            label={t('settings.logRetention')}
            type="number"
            value={settings.audit_retention_days || 90}
            onChange={(e) => updateSetting('audit_retention_days', parseInt(e.target.value))}
            min="7"
            max="730"
            disabled={!settings.audit_enabled}
          />
        </div>
      </DetailSection>
      <DetailSection title={t('settings.eventsToLog')} icon={Eye} iconClass="icon-bg-orange">
        <div className="space-y-2">
          {[
            { key: 'userLoginLogout', label: t('settings.eventUserLoginLogout') },
            { key: 'certIssueRevoke', label: t('settings.eventCertIssueRevoke') },
            { key: 'caCreateDelete', label: t('settings.eventCaCreateDelete') },
            { key: 'settingsChanges', label: t('settings.eventSettingsChanges') },
            { key: 'userManagement', label: t('common.eventUserManagement') },
          ].map(event => (
            <label key={event.key} className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={true}
                disabled={!settings.audit_enabled}
                className="rounded border-border bg-bg-tertiary"
              />
              <span className="text-sm text-text-primary">{event.label}</span>
            </label>
          ))}
          {hasPermission('admin:system') && (
            <div className="pt-4">
              <Button type="button" onClick={() => handleSave('audit')} disabled={saving}>
                <FloppyDisk size={16} />
                {t('common.saveChanges')}
              </Button>
            </div>
          )}
        </div>
      </DetailSection>
      <DetailSection title={t('settings.remoteSyslog')} icon={Globe} iconClass="icon-bg-purple">
        <div className="space-y-4">
          <p className="text-xs text-text-secondary">{t('settings.remoteSyslogDesc')}</p>
          <ToggleSwitch
            checked={syslogConfig.enabled}
            onChange={(val) => updateSyslogConfig('enabled', val)}
            label={t('settings.enableSyslog')}
          />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label={t('settings.syslogHost')}
              value={syslogConfig.host}
              onChange={(e) => updateSyslogConfig('host', e.target.value)}
              placeholder="syslog.example.com"
            />
            <Input
              label={t('settings.syslogPort')}
              type="number"
              value={syslogConfig.port}
              onChange={(e) => updateSyslogConfig('port', parseInt(e.target.value) || 514)}
              min="1"
              max="65535"
            />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Select
              label={t('settings.syslogProtocol')}
              value={syslogConfig.protocol}
              onChange={(e) => updateSyslogConfig('protocol', e.target.value)}
              options={[
                { value: 'udp', label: 'UDP' },
                { value: 'tcp', label: 'TCP' },
              ]}
            />
            <div>
              <p className="text-sm font-medium text-text-primary mb-2">{t('settings.syslogCategories')}</p>
              <p className="text-xs text-text-tertiary mb-3">{t('settings.syslogCategoriesHelp')}</p>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                {[
                  { value: 'certificate', label: t('settings.syslogCatCertificates') },
                  { value: 'ca', label: t('settings.syslogCatCAs') },
                  { value: 'csr', label: t('settings.syslogCatCSRs') },
                  { value: 'user', label: t('settings.syslogCatUsers') },
                  { value: 'acme', label: 'ACME' },
                  { value: 'scep', label: 'SCEP' },
                  { value: 'system', label: t('settings.syslogCatSystem') },
                ].map(cat => (
                  <label key={cat.value} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={(syslogConfig.categories || []).includes(cat.value)}
                      onChange={(e) => {
                        const cats = syslogConfig.categories || []
                        updateSyslogConfig('categories', e.target.checked
                          ? [...cats, cat.value]
                          : cats.filter(c => c !== cat.value)
                        )
                      }}
                      className="rounded border-border bg-bg-tertiary"
                    />
                    <span className="text-sm text-text-primary">{cat.label}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>
          {syslogConfig.protocol === 'tcp' && (
            <ToggleSwitch
              checked={syslogConfig.tls}
              onChange={(val) => updateSyslogConfig('tls', val)}
              label={t('settings.syslogTls')}
              size="sm"
            />
          )}
          {hasPermission('admin:system') && (
            <div className="flex gap-2">
              <Button type="button" onClick={handleSaveSyslog} loading={syslogSaving}>
                <FloppyDisk size={16} />
                {t('common.saveChanges')}
              </Button>
              {syslogConfig.enabled && syslogConfig.host && (
                <Button type="button" variant="secondary" onClick={handleTestSyslog} loading={syslogTesting}>
                  <Lightning size={16} />
                  {t('settings.syslogTest')}
                </Button>
              )}
            </div>
          )}
        </div>
      </DetailSection>
    </DetailContent>
  )
}
