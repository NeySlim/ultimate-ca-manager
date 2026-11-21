/**
 * Audit: the retention of the log, then the mockup's « Export du journal » (its syslog section):
 * the switch, the server, the port and the transport (TLS is TCP with TLS on), then what the
 * product adds (framing, certificate check, categories), and the test of the saved forwarding.
 */
import { useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Notice } from '../../components/atelier'
import { Input, NumberInput, Select, ToggleSwitch, SegmentedField } from '../../components/atelier/Form'
import { SettingsGroup, SettingsTest } from '../../components/atelier/SettingsView'
import { useRefocusAfter } from '../../components/sectioned/useRefocus'
import AdminLockLabel from './AdminLockLabel'
import { shownNumber, typedNumber } from './numberFields'

const CATEGORIES = [
  ['certificate', 'settings.syslogCatCertificates'], ['ca', 'settings.syslogCatCAs'], ['csr', 'settings.syslogCatCSRs'],
  ['user', 'settings.syslogCatUsers'], ['acme', null, 'ACME'], ['scep', null, 'SCEP'], ['system', 'settings.syslogCatSystem'],
]

// The mockup's transport: TLS, TCP or UDP; the server keeps TLS as a switch of TCP
const transportOf = (c) => (c.protocol === 'tcp' && c.tls ? 'tls' : c.protocol || 'udp')

export default function AuditSection({ settings, fieldErrors = {}, updateSetting, hasPermission, syslogConfig, updateSyslogConfig, syslogTesting, syslogTestResult, handleTestSyslog }) {
  const { t } = useTranslation()
  const testButton = useRef(null)
  useRefocusAfter(Boolean(syslogTesting), testButton)
  // The backend accepts a retention from admins only: shortening it deletes history.
  const canAdminSettings = Boolean(hasPermission('admin:settings'))
  const transport = transportOf(syslogConfig)
  const overTcp = transport !== 'udp'
  const categories = syslogConfig.categories || []

  const pickTransport = (value) => {
    updateSyslogConfig('protocol', value === 'udp' ? 'udp' : 'tcp')
    updateSyslogConfig('tls', value === 'tls')
  }

  return (
    <>
      <SettingsGroup legend={t('settings.auditLogging')}>
        <NumberInput id="set-audit_retention_days" label={<AdminLockLabel text={t('settings.logRetention')} locked={!canAdminSettings} mockup />}
          value={shownNumber(settings.audit_retention_days ?? 0)} onChange={(e) => updateSetting('audit_retention_days', typedNumber(e))}
          hint={t('settings.logRetentionHelp')} disabled={!canAdminSettings} error={fieldErrors.audit_retention_days} />
      </SettingsGroup>

      <SettingsGroup legend={t('settings.remoteSyslog')} hint={t('settings.remoteSyslogDesc')}>
        <ToggleSwitch id="set-syslog_enabled" checked={!!syslogConfig.enabled} label={t('settings.enableSyslog')}
          onChange={(val) => updateSyslogConfig('enabled', val)} />
        <Input id="set-syslog_host" label={t('settings.syslogHost')} value={syslogConfig.host || ''} placeholder="syslog.example.com"
          onChange={(e) => updateSyslogConfig('host', e.target.value)} error={fieldErrors['syslog.host']} />
        <NumberInput id="set-syslog_port" label={t('settings.syslogPort')} value={shownNumber(syslogConfig.port)}
          onChange={(e) => updateSyslogConfig('port', typedNumber(e))} hint={t('settings.syslogPortHint')} error={fieldErrors['syslog.port']} />
        <Select id="set-syslog_protocol" short label={t('settings.syslogProtocol')} value={transport} onChange={pickTransport}
          options={[
            { value: 'tls', label: t('settings.syslogTransportTls') },
            { value: 'tcp', label: 'TCP' },
            { value: 'udp', label: 'UDP' },
          ]} />
        {overTcp && (
          <Select id="set-syslog_framing" label={t('settings.syslogFraming')} value={syslogConfig.framing || 'line'}
            onChange={(value) => updateSyslogConfig('framing', value)}
            options={[
              { value: 'line', label: t('settings.syslogFramingLine') },
              { value: 'octet', label: t('settings.syslogFramingOctet') },
            ]} />
        )}
        {transport === 'tls' && (
          <ToggleSwitch id="set-syslog_tls_verify" checked={syslogConfig.tls_verify ?? true} label={t('settings.syslogTlsVerify')}
            onChange={(val) => updateSyslogConfig('tls_verify', val)} />
        )}
        {transport === 'tls' && syslogConfig.tls_verify === false && <Notice tone="bad">{t('settings.syslogTlsVerifyWarning')}</Notice>}
        <SegmentedField id="set-syslog_categories" label={t('settings.syslogCategories')} hint={t('settings.syslogCategoriesHelp')}
          options={CATEGORIES.map(([value, key, name]) => ({ value, label: key ? t(key) : name }))}
          pressed={(value) => categories.includes(value)}
          onPick={(value) => updateSyslogConfig('categories', categories.includes(value) ? categories.filter((c) => c !== value) : [...categories, value])} />
      </SettingsGroup>

      {/* Test of the saved forwarding, last in the frame as in the mockup: the button and its result */}
      {hasPermission('admin:system') && (
        <SettingsTest id="syslog" label={t('settings.syslogTest')} onTest={handleTestSyslog} busy={Boolean(syslogTesting)} buttonRef={testButton}
          result={syslogTestResult ? { ok: syslogTestResult.ok, text: syslogTestResult.text } : null} hint={t('settings.syslogTestSavedHint')} />
      )}
    </>
  )
}
