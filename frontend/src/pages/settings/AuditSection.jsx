import { useTranslation } from 'react-i18next'
import { PaperPlaneTilt, CheckCircle, WarningCircle, Question } from '@phosphor-icons/react'
import { Button, Input, Select } from '../../components'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import { FormGroup } from '../../components/sectioned'

export default function AuditSection({ settings, fieldErrors = {}, updateSetting, hasPermission, syslogConfig, updateSyslogConfig, syslogTesting, syslogTestResult, handleTestSyslog }) {
  const { t } = useTranslation()
  // The backend accepts a retention from admins only: shortening it deletes history.
  const canAdminSettings = Boolean(hasPermission('admin:settings'))
  return (
    <>
      <FormGroup title={t('settings.auditLogging')}>
        <div className="space-y-4">
          <Input
            className="sf-short"
            label={t('settings.logRetention')}
            type="number"
            value={settings.audit_retention_days ?? 0}
            onChange={(e) => updateSetting('audit_retention_days', parseInt(e.target.value, 10) || 0)}
            min="0"
            max="1825"
            helperText={t('settings.logRetentionHelp')}
            disabled={canAdminSettings === false}
          />
        </div>
      </FormGroup>
      <FormGroup title={t('settings.remoteSyslog')} description={t('settings.remoteSyslogDesc')}>
        <div className="space-y-4">
          <ToggleSwitch
            checked={syslogConfig.enabled}
            onChange={(val) => updateSyslogConfig('enabled', val)}
            label={t('settings.enableSyslog')}
          />
          <Input
            label={t('settings.syslogHost')}
            value={syslogConfig.host}
            onChange={(e) => updateSyslogConfig('host', e.target.value)}
            placeholder="syslog.example.com"
          />
          <Input
            className="sf-short"
            label={t('settings.syslogPort')}
            type="number"
            inputMode="numeric"
            value={syslogConfig.port ?? ''}
            onChange={(e) => updateSyslogConfig('port', e.target.value === '' ? '' : Number(e.target.value))}
            min="1"
            max="65535"
            error={fieldErrors['syslog.port']}
          />
          <Select
            className="sf-short"
            label={t('settings.syslogProtocol')}
            value={syslogConfig.protocol}
            onChange={(value) => updateSyslogConfig('protocol', value)}
            options={[
              { value: 'udp', label: 'UDP' },
              { value: 'tcp', label: 'TCP' },
            ]}
          />
          {syslogConfig.protocol === 'tcp' && (
            <Select
              label={t('settings.syslogFraming')}
              value={syslogConfig.framing || 'line'}
              onChange={(value) => updateSyslogConfig('framing', value)}
              options={[
                { value: 'line', label: t('settings.syslogFramingLine') },
                { value: 'octet', label: t('settings.syslogFramingOctet') },
              ]}
            />
          )}
          {syslogConfig.protocol === 'tcp' && (
            <div>
              <ToggleSwitch
                checked={syslogConfig.tls}
                onChange={(val) => updateSyslogConfig('tls', val)}
                label={t('settings.syslogTls')}
              />
              {syslogConfig.tls && (
                <ToggleSwitch
                  checked={syslogConfig.tls_verify ?? true}
                  onChange={(val) => updateSyslogConfig('tls_verify', val)}
                  label={t('settings.syslogTlsVerify')}
                />
              )}
              {syslogConfig.tls && syslogConfig.tls_verify === false && (
                <p className="ui-error">{t('settings.syslogTlsVerifyWarning')}</p>
              )}
            </div>
          )}
          <fieldset className="sf-checks">
            <legend className="ui-label">{t('settings.syslogCategories')}</legend>
            <p className="ui-help">{t('settings.syslogCategoriesHelp')}</p>
            <div className="sf-checks-grid">
              {[
                { value: 'certificate', label: t('settings.syslogCatCertificates') },
                { value: 'ca', label: t('settings.syslogCatCAs') },
                { value: 'csr', label: t('settings.syslogCatCSRs') },
                { value: 'user', label: t('settings.syslogCatUsers') },
                { value: 'acme', label: 'ACME' },
                { value: 'scep', label: 'SCEP' },
                { value: 'system', label: t('settings.syslogCatSystem') },
              ].map(cat => (
                <label key={cat.value} className="ui-check-line">
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
                  />
                  {cat.label}
                </label>
              ))}
            </div>
          </fieldset>
        </div>
        {/* Test of the saved forwarding: the button stays, its result on the same line */}
        {hasPermission('admin:system') && (
          <div className="sf-test sf-under-group">
            <Button type="button" variant="secondary" onClick={handleTestSyslog} loading={syslogTesting}>
              <PaperPlaneTilt size={16} />
              {t('settings.syslogTest')}
            </Button>
            {syslogTestResult ? (
              <p className={`sf-test-result ${syslogTestResult.ok ? 'is-good' : 'is-bad'}`} role="status">
                {syslogTestResult.ok ? <CheckCircle aria-hidden="true" /> : <WarningCircle aria-hidden="true" />}
                <span>{syslogTestResult.text}</span>
              </p>
            ) : (
              <p className="sf-test-result">
                <Question aria-hidden="true" />
                <span>{t('settings.syslogTestSavedHint')}</span>
              </p>
            )}
          </div>
        )}
      </FormGroup>
    </>
  )
}
