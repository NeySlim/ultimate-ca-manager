import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, Pill, Notice } from '../../components/atelier'
import { Input, NumberInput, Select, ToggleSwitch } from '../../components/atelier/Form'
import { SettingsGroup } from '../../components/atelier/SettingsView'
import { useNotification } from '../../contexts'
import { certificatesService, settingsService } from '../../services'
import { certificateLabel } from '../../lib/utils'
import { fetchAllPages } from '../../lib/fetchAllPages'
import ServiceStatusWidget from './ServiceStatusWidget'
import PublicEndpointsPanel from './PublicEndpointsPanel'
import AdminLockLabel from './AdminLockLabel'
import { shownNumber, typedNumber } from './numberFields'

const TIMEZONES = [
  ['UTC', 'UTC (GMT+0)'], ['Europe/London', 'Europe/London (GMT+0/+1)'], ['Europe/Paris', 'Europe/Paris (GMT+1/+2)'],
  ['Europe/Berlin', 'Europe/Berlin (GMT+1/+2)'], ['Europe/Zurich', 'Europe/Zurich (GMT+1/+2)'], ['Europe/Brussels', 'Europe/Brussels (GMT+1/+2)'],
  ['Europe/Amsterdam', 'Europe/Amsterdam (GMT+1/+2)'], ['Europe/Rome', 'Europe/Rome (GMT+1/+2)'], ['Europe/Madrid', 'Europe/Madrid (GMT+1/+2)'],
  ['Europe/Helsinki', 'Europe/Helsinki (GMT+2/+3)'], ['Europe/Athens', 'Europe/Athens (GMT+2/+3)'], ['Europe/Moscow', 'Europe/Moscow (GMT+3)'],
  ['America/New_York', 'America/New York (GMT-5/-4)'], ['America/Chicago', 'America/Chicago (GMT-6/-5)'], ['America/Denver', 'America/Denver (GMT-7/-6)'],
  ['America/Los_Angeles', 'America/Los Angeles (GMT-8/-7)'], ['America/Toronto', 'America/Toronto (GMT-5/-4)'], ['America/Sao_Paulo', 'America/São Paulo (GMT-3)'],
  ['Asia/Dubai', 'Asia/Dubai (GMT+4)'], ['Asia/Kolkata', 'Asia/Kolkata (GMT+5:30)'], ['Asia/Shanghai', 'Asia/Shanghai (GMT+8)'],
  ['Asia/Tokyo', 'Asia/Tokyo (GMT+9)'], ['Asia/Seoul', 'Asia/Seoul (GMT+9)'], ['Asia/Singapore', 'Asia/Singapore (GMT+8)'],
  ['Australia/Sydney', 'Australia/Sydney (GMT+10/+11)'], ['Pacific/Auckland', 'Pacific/Auckland (GMT+12/+13)'],
].map(([value, label]) => ({ value, label }))

export default function GeneralSection({ settings, fieldErrors = {}, updateSetting, canWrite, hasPermission, savedVersion = 0 }) {
  const { t, i18n } = useTranslation()
  // The short and long samples in the reader's language, as the dates will read
  const sampleDate = (month) => {
    try { return new Intl.DateTimeFormat(i18n?.resolvedLanguage || i18n?.language, { year: 'numeric', month, day: 'numeric' }).format(new Date(2026, 0, 6)) } catch { return '' }
  }
  const { showSuccess, showError } = useNotification()
  const [metricsToken, setMetricsToken] = useState('')
  const [metricsBusy, setMetricsBusy] = useState(false)
  const [tlsCertOptions, setTlsCertOptions] = useState([])
  const [savedTlsCert, setSavedTlsCert] = useState(null)

  // The API drops these keys without admin:settings; the other fields still save.
  const adminLocked = !(typeof hasPermission === 'function' && hasPermission('admin:settings'))
  const lockedLabel = (key) => <AdminLockLabel text={t(key)} locked={adminLocked} mockup />
  // HTTP_PROTOCOL_PORT in the service environment sets the port: the value shown is the one bound
  const portPinned = settings.env_locked?.http_protocol_port_env === true
  // The ACME public vhost TLS selector loads its certificates when it is first used, not with the page
  const tlsCertLoad = useRef(null)
  const certOption = (c) => ({ value: String(c.id), label: `${certificateLabel(c) || c.refid} (#${c.id})` })
  const loadTlsCertOptions = () => {
    if (tlsCertLoad.current) return
    tlsCertLoad.current = fetchAllPages((query) => certificatesService.getAll({ ...query, has_private_key: true }))
      .then((all) => setTlsCertOptions(all.filter((c) => !c.revoked).map(certOption)))
      .catch(() => { tlsCertLoad.current = null })
  }
  // The saved choice is named by one certificate read, so the closed selector shows it
  const savedTlsCertId = settings.acme_public_tls_cert_id ? String(settings.acme_public_tls_cert_id) : ''
  useEffect(() => {
    if (!savedTlsCertId || tlsCertOptions.some((o) => o.value === savedTlsCertId)) return undefined
    let cancelled = false
    certificatesService.getById(savedTlsCertId)
      .then((res) => { if (!cancelled && res?.data) setSavedTlsCert(certOption(res.data)) })
      .catch(() => {})
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [savedTlsCertId])
  const tlsSelectOptions = [{ value: '', label: t('common.none') }, ...tlsCertOptions]
  if (savedTlsCertId && !tlsCertOptions.some((o) => o.value === savedTlsCertId)) {
    tlsSelectOptions.push(savedTlsCert?.value === savedTlsCertId ? savedTlsCert : { value: savedTlsCertId, label: `#${savedTlsCertId}` })
  }

  const generateToken = () => {
    const a = new Uint8Array(24)
    crypto.getRandomValues(a)
    setMetricsToken(Array.from(a, (b) => b.toString(16).padStart(2, '0')).join(''))
  }
  const saveMetricsToken = async () => {
    if (!metricsToken) return
    setMetricsBusy(true)
    try {
      await settingsService.updateBulk({ metrics_token: metricsToken })
      updateSetting('metrics_enabled', true)
      setMetricsToken('')
      showSuccess(t('settings.metrics.enabled'))
    } catch (e) {
      showError(e.message || t('messages.errors.updateFailed.settings'))
    } finally {
      setMetricsBusy(false)
    }
  }
  const disableMetrics = async () => {
    setMetricsBusy(true)
    try {
      await settingsService.updateBulk({ metrics_token: '__disable__' })
      updateSetting('metrics_enabled', false)
      setMetricsToken('')
      showSuccess(t('settings.metrics.disabled'))
    } catch (e) {
      showError(e.message || t('messages.errors.updateFailed.settings'))
    } finally {
      setMetricsBusy(false)
    }
  }

  return (
    <>
      <SettingsGroup legend={t('settings.subtitle')}>
        <Input id="set-system_name" label={t('settings.systemName')} value={settings.system_name || ''}
          onChange={(e) => updateSetting('system_name', e.target.value)} hint={t('settings.systemNameHelper')} />
        <Input id="set-base_url" full label={lockedLabel('settings.baseUrl')} disabled={adminLocked} value={settings.base_url || ''}
          error={fieldErrors.base_url} onChange={(e) => updateSetting('base_url', e.target.value)}
          placeholder={t('settings.baseUrlPlaceholder')} hint={t('settings.baseUrlHelper')} />
        <Input id="set-protocol_base_url" full label={lockedLabel('settings.protocolBaseUrl')} disabled={adminLocked}
          value={settings.protocol_base_url || ''} error={fieldErrors.protocol_base_url}
          onChange={(e) => updateSetting('protocol_base_url', e.target.value)} placeholder="http://admin.ucm.example.com:8080"
          hint={t('settings.protocolBaseUrlHelper')} />
        <NumberInput id="set-http_protocol_port" label={t('settings.httpProtocolPort')} disabled={portPinned}
          value={shownNumber(settings.http_protocol_port ?? 8080)} placeholder="8080"
          onChange={(e) => updateSetting('http_protocol_port', Math.min(65535, Math.max(0, parseInt(e.target.value, 10) || 0)))}
          hint={portPinned ? t('settings.httpProtocolPortEnvLocked') : t('settings.httpProtocolPortHelper')} />
        <Input id="set-acme_public_vhost" label={lockedLabel('settings.acmePublicVhost')} disabled={adminLocked}
          value={settings.acme_public_vhost || ''} onChange={(e) => updateSetting('acme_public_vhost', e.target.value)}
          placeholder="acme.ucm.example.com" hint={t('settings.acmePublicVhostHelper')} />
        <NumberInput id="set-acme_public_port" label={lockedLabel('settings.acmePublicPort')} disabled={adminLocked}
          value={shownNumber(settings.acme_public_port ?? 443)} error={fieldErrors.acme_public_port}
          onChange={(e) => updateSetting('acme_public_port', typedNumber(e))} hint={t('settings.acmePublicPortHelper')} />
        <Select id="set-acme_public_tls_cert_id" label={lockedLabel('settings.acmePublicTlsCertId')} disabled={adminLocked}
          value={savedTlsCertId} onFocus={loadTlsCertOptions} onMouseDown={loadTlsCertOptions}
          onChange={(val) => updateSetting('acme_public_tls_cert_id', val || '')}
          options={tlsSelectOptions} hint={t('settings.acmePublicTlsCertIdHelper')} />
        {canWrite('settings') && adminLocked && <Notice>{t('settings.adminFieldsLocked')}</Notice>}
      </SettingsGroup>
      <PublicEndpointsPanel settings={settings} updateSetting={updateSetting} refreshKey={savedVersion} adminLocked={adminLocked} />
      <SettingsGroup legend={t('settings.sessionTimezone')}>
        <NumberInput id="set-session_timeout" label={lockedLabel('settings.sessionTimeout')} disabled={adminLocked}
          value={shownNumber(settings.session_timeout ?? 28800, (s) => Math.round((s || 28800) / 60))}
          onChange={(e) => updateSetting('session_timeout', typedNumber(e, (m) => m * 60))}
          hint={t('settings.sessionTimeoutHelper')} error={fieldErrors.session_timeout} />
        <NumberInput id="set-max_login_attempts" label={lockedLabel('settings.maxLoginAttempts')} disabled={adminLocked}
          value={shownNumber(settings.max_login_attempts ?? 5, (n) => n || 5)}
          onChange={(e) => updateSetting('max_login_attempts', typedNumber(e))}
          hint={t('settings.maxLoginAttemptsHelper')} error={fieldErrors.max_login_attempts} />
        <NumberInput id="set-lockout_duration" label={lockedLabel('settings.lockoutDuration')} disabled={adminLocked}
          value={shownNumber(settings.lockout_duration ?? 900, (s) => Math.round((s || 900) / 60))}
          onChange={(e) => updateSetting('lockout_duration', typedNumber(e, (m) => m * 60))}
          hint={t('settings.lockoutDurationHelper')} error={fieldErrors.lockout_duration} />
        <Select id="set-timezone" label={t('settings.timezone')} options={TIMEZONES} value={settings.timezone || 'UTC'}
          onChange={(val) => updateSetting('timezone', val)} />
        <Select id="set-date_format" label={t('settings.dateFormat')}
          options={[
            { value: 'short', label: `${t('settings.dateFormats.short')}, ${sampleDate('short')}` },
            { value: 'long', label: `${t('settings.dateFormats.long')}, ${sampleDate('long')}` },
            { value: 'iso', label: `${t('settings.dateFormats.iso')}, 2026-01-06` },
            { value: 'eu', label: `${t('settings.dateFormats.eu')}, 06/01/2026` },
            { value: 'us', label: `${t('settings.dateFormats.us')}, 01/06/2026` },
          ]}
          value={settings.date_format || 'short'} onChange={(val) => updateSetting('date_format', val)} />
        <ToggleSwitch id="set-show_time" checked={settings.show_time !== 'false' && settings.show_time !== false}
          onChange={(on) => updateSetting('show_time', on)} label={t('settings.showTime')} />
      </SettingsGroup>
      <SettingsGroup legend={<>{t('settings.metrics.title')}{' '}
        <Pill label={settings.metrics_enabled ? t('common.enabled') : t('common.disabled')} tone={settings.metrics_enabled ? 'good' : 'muted'} /></>}
      hint={t('settings.metrics.subtitle')}>
        <Input id="set-metrics_token" label={t('settings.metrics.token')} value={metricsToken}
          onChange={(e) => setMetricsToken(e.target.value)} hint={t('settings.metrics.tokenHelper')}
          placeholder={settings.metrics_enabled ? t('settings.metrics.tokenRotatePlaceholder') : t('settings.metrics.tokenPlaceholder')} />
        <div className="settings-actions">
          <Btn icon="refresh" write onClick={generateToken} disabled={!canWrite('settings')}>{t('settings.metrics.generate')}</Btn>
          {canWrite('settings') && (
            <Btn tone="primary" icon="check" onClick={saveMetricsToken} disabled={metricsBusy || !metricsToken}>
              {settings.metrics_enabled ? t('settings.metrics.rotate') : t('settings.metrics.enable')}
            </Btn>
          )}
          {canWrite('settings') && settings.metrics_enabled && (
            <Btn tone="danger" onClick={disableMetrics} disabled={metricsBusy}>{t('settings.metrics.disable')}</Btn>
          )}
        </div>
      </SettingsGroup>
      <ServiceStatusWidget />
    </>
  )
}
