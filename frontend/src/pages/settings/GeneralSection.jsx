import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {  FloppyDisk, ArrowsClockwise } from '@phosphor-icons/react'
import { Button, Input, Select, Badge } from '../../components'
import { useNotification } from '../../contexts'
import { certificatesService, settingsService } from '../../services'
import { certificateLabel } from '../../lib/utils'
import { fetchAllPages } from '../../lib/fetchAllPages'
import ServiceStatusWidget from './ServiceStatusWidget'
import PublicEndpointsPanel from './PublicEndpointsPanel'
import AdminLockLabel from './AdminLockLabel'
import { FormGroup } from '../../components/sectioned'

export default function GeneralSection({ settings, fieldErrors = {}, updateSetting, canWrite, hasPermission, savedVersion = 0 }) {
  const { t, i18n } = useTranslation()
  // The short and long samples in the reader's language, as the dates will read
  const sampleDate = (month) => {
    try { return new Intl.DateTimeFormat(i18n?.language, { year: 'numeric', month, day: 'numeric' }).format(new Date(2026, 0, 6)) } catch { return '' }
  }
  const { showSuccess, showError } = useNotification()
  const [metricsToken, setMetricsToken] = useState('')
  const [metricsBusy, setMetricsBusy] = useState(false)
  const [tlsCertOptions, setTlsCertOptions] = useState([])

  // The API drops these keys without admin:settings; the other fields still save.
  const adminLocked = !(typeof hasPermission === 'function' && hasPermission('admin:settings'))
  const lockedLabel = (key) => <AdminLockLabel text={t(key)} locked={adminLocked} />
  // HTTP_PROTOCOL_PORT in the service environment sets the port: the value shown is the one bound
  const portPinned = settings.env_locked?.http_protocol_port_env === true
  // Certificates with a private key, for the ACME public vhost TLS selector
  useEffect(() => {
    let cancelled = false
    fetchAllPages((query) => certificatesService.getAll({ ...query, has_private_key: true }))
      .then((all) => {
        if (cancelled) return
        const certs = all.filter((c) => !c.revoked)
        setTlsCertOptions(certs.map((c) => ({
          value: String(c.id),
          label: `${certificateLabel(c) || c.refid} (#${c.id})`,
        })))
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

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
      <FormGroup title={t('settings.subtitle')}>
        <div className="space-y-4">
          <Input
            label={t('settings.systemName')}
            value={settings.system_name || ''}
            onChange={(e) => updateSetting('system_name', e.target.value)}
            helperText={t('settings.systemNameHelper')}
          />
          <Input
            label={lockedLabel('settings.baseUrl')}
            disabled={adminLocked}
            value={settings.base_url || ''}
            onChange={(e) => updateSetting('base_url', e.target.value)}
            placeholder={t('settings.baseUrlPlaceholder')}
            helperText={t('settings.baseUrlHelper')}
          />
          <Input
            label={lockedLabel('settings.protocolBaseUrl')}
            disabled={adminLocked}
            value={settings.protocol_base_url || ''}
            onChange={(e) => updateSetting('protocol_base_url', e.target.value)}
            placeholder="http://admin.ucm.example.com:8080"
            helperText={t('settings.protocolBaseUrlHelper')}
          />
          <Input
            className="sf-short"
            label={t('settings.httpProtocolPort')}
            type="number"
            min={0}
            max={65535}
            disabled={portPinned}
            value={settings.http_protocol_port ?? 8080}
            onChange={(e) => {
              const val = parseInt(e.target.value) || 0
              updateSetting('http_protocol_port', Math.min(65535, Math.max(0, val)))
            }}
            placeholder="8080"
            helperText={portPinned
              ? t('settings.httpProtocolPortEnvLocked')
              : t('settings.httpProtocolPortHelper')}
          />
          <Input
            label={lockedLabel('settings.acmePublicVhost')}
            disabled={adminLocked}
            value={settings.acme_public_vhost || ''}
            onChange={(e) => updateSetting('acme_public_vhost', e.target.value)}
            placeholder="acme.ucm.example.com"
            helperText={t('settings.acmePublicVhostHelper')}
          />
          <Input
            className="sf-short"
            label={lockedLabel('settings.acmePublicPort')}
            disabled={adminLocked}
            type="number"
            min={1}
            max={65535}
            inputMode="numeric"
            value={settings.acme_public_port ?? 443}
            onChange={(e) => updateSetting('acme_public_port', e.target.value === '' ? '' : Number(e.target.value))}
            error={fieldErrors.acme_public_port}
            helperText={t('settings.acmePublicPortHelper')}
          />
          <Select
            label={lockedLabel('settings.acmePublicTlsCertId')}
            disabled={adminLocked}
            value={settings.acme_public_tls_cert_id ? String(settings.acme_public_tls_cert_id) : ''}
            onChange={(val) => updateSetting('acme_public_tls_cert_id', val || '')}
            options={[
              { value: '', label: t('common.none') },
              ...tlsCertOptions,
            ]}
            helperText={t('settings.acmePublicTlsCertIdHelper')}
          />
          {canWrite('settings') && adminLocked && (
            <p className="text-xs text-text-tertiary">{t('settings.adminFieldsLocked')}</p>
          )}
        </div>
      </FormGroup>
      <PublicEndpointsPanel
        settings={settings}
        updateSetting={updateSetting}
        refreshKey={savedVersion}
        adminLocked={adminLocked}
      />
      <FormGroup title={t('settings.sessionTimezone')}>
        <div className="space-y-4">
          <Input
            className="sf-short"
            label={lockedLabel('settings.sessionTimeout')}
            disabled={adminLocked}
            type="number"
            value={Math.round((settings.session_timeout || 28800) / 60)}
            onChange={(e) => updateSetting('session_timeout', parseInt(e.target.value) * 60)}
            min="5"
            max="1440"
            helperText={t('settings.sessionTimeoutHelper')}
          />
          <Input
            className="sf-short"
            label={lockedLabel('settings.maxLoginAttempts')}
            disabled={adminLocked}
            type="number"
            value={settings.max_login_attempts || 5}
            onChange={(e) => updateSetting('max_login_attempts', parseInt(e.target.value))}
            min="3"
            max="20"
            helperText={t('settings.maxLoginAttemptsHelper')}
          />
          <Input
            className="sf-short"
            label={lockedLabel('settings.lockoutDuration')}
            disabled={adminLocked}
            type="number"
            value={Math.round((settings.lockout_duration || 900) / 60)}
            onChange={(e) => updateSetting('lockout_duration', parseInt(e.target.value) * 60)}
            min="1"
            max="60"
            helperText={t('settings.lockoutDurationHelper')}
          />
          <Select
            label={t('settings.timezone')}
            options={[
              { value: 'UTC', label: 'UTC (GMT+0)' },
              { value: 'Europe/London', label: 'Europe/London (GMT+0/+1)' },
              { value: 'Europe/Paris', label: 'Europe/Paris (GMT+1/+2)' },
              { value: 'Europe/Berlin', label: 'Europe/Berlin (GMT+1/+2)' },
              { value: 'Europe/Zurich', label: 'Europe/Zurich (GMT+1/+2)' },
              { value: 'Europe/Brussels', label: 'Europe/Brussels (GMT+1/+2)' },
              { value: 'Europe/Amsterdam', label: 'Europe/Amsterdam (GMT+1/+2)' },
              { value: 'Europe/Rome', label: 'Europe/Rome (GMT+1/+2)' },
              { value: 'Europe/Madrid', label: 'Europe/Madrid (GMT+1/+2)' },
              { value: 'Europe/Helsinki', label: 'Europe/Helsinki (GMT+2/+3)' },
              { value: 'Europe/Athens', label: 'Europe/Athens (GMT+2/+3)' },
              { value: 'Europe/Moscow', label: 'Europe/Moscow (GMT+3)' },
              { value: 'America/New_York', label: 'America/New York (GMT-5/-4)' },
              { value: 'America/Chicago', label: 'America/Chicago (GMT-6/-5)' },
              { value: 'America/Denver', label: 'America/Denver (GMT-7/-6)' },
              { value: 'America/Los_Angeles', label: 'America/Los Angeles (GMT-8/-7)' },
              { value: 'America/Toronto', label: 'America/Toronto (GMT-5/-4)' },
              { value: 'America/Sao_Paulo', label: 'America/São Paulo (GMT-3)' },
              { value: 'Asia/Dubai', label: 'Asia/Dubai (GMT+4)' },
              { value: 'Asia/Kolkata', label: 'Asia/Kolkata (GMT+5:30)' },
              { value: 'Asia/Shanghai', label: 'Asia/Shanghai (GMT+8)' },
              { value: 'Asia/Tokyo', label: 'Asia/Tokyo (GMT+9)' },
              { value: 'Asia/Seoul', label: 'Asia/Seoul (GMT+9)' },
              { value: 'Asia/Singapore', label: 'Asia/Singapore (GMT+8)' },
              { value: 'Australia/Sydney', label: 'Australia/Sydney (GMT+10/+11)' },
              { value: 'Pacific/Auckland', label: 'Pacific/Auckland (GMT+12/+13)' },
            ]}
            value={settings.timezone || 'UTC'}
            onChange={(val) => updateSetting('timezone', val)}
          />
          <Select
            label={t('settings.dateFormat')}
            options={[
              { value: 'short', label: `${t('settings.dateFormats.short')}, ${sampleDate('short')}` },
              { value: 'long', label: `${t('settings.dateFormats.long')}, ${sampleDate('long')}` },
              { value: 'iso', label: `${t('settings.dateFormats.iso')}, 2026-01-06` },
              { value: 'eu', label: `${t('settings.dateFormats.eu')}, 06/01/2026` },
              { value: 'us', label: `${t('settings.dateFormats.us')}, 01/06/2026` },
            ]}
            value={settings.date_format || 'short'}
            onChange={(val) => updateSetting('date_format', val)}
          />
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={settings.show_time !== 'false' && settings.show_time !== false}
              onChange={(e) => updateSetting('show_time', e.target.checked)}
              className="rounded"
            />
            {t('settings.showTime')}
          </label>
        </div>
      </FormGroup>
      <FormGroup title={t('settings.metrics.title')}>
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Badge variant={settings.metrics_enabled ? 'success' : 'secondary'} size="sm">
              {settings.metrics_enabled ? t('common.enabled') : t('common.disabled')}
            </Badge>
            <span className="text-xs text-text-secondary">{t('settings.metrics.subtitle')}</span>
          </div>
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <Input
                label={t('settings.metrics.token')}
                type="text"
                value={metricsToken}
                onChange={(e) => setMetricsToken(e.target.value)}
                placeholder={settings.metrics_enabled ? t('settings.metrics.tokenRotatePlaceholder') : t('settings.metrics.tokenPlaceholder')}
                helperText={t('settings.metrics.tokenHelper')}
              />
            </div>
            <Button type="button" variant="secondary" onClick={generateToken} disabled={!canWrite('settings')}>
              <ArrowsClockwise size={16} />
              {t('settings.metrics.generate')}
            </Button>
          </div>
          {canWrite('settings') && (
            <div className="flex items-center gap-2 pt-1">
              <Button type="button" onClick={saveMetricsToken} disabled={metricsBusy || !metricsToken}>
                <FloppyDisk size={16} />
                {settings.metrics_enabled ? t('settings.metrics.rotate') : t('settings.metrics.enable')}
              </Button>
              {settings.metrics_enabled && (
                <Button type="button" variant="danger-soft" onClick={disableMetrics} disabled={metricsBusy}>
                  {t('settings.metrics.disable')}
                </Button>
              )}
            </div>
          )}
        </div>
      </FormGroup>
      <ServiceStatusWidget />
    </>
  )
}
