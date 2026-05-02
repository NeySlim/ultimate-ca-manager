import { useTranslation } from 'react-i18next'
import { Gear, Clock, FloppyDisk } from '@phosphor-icons/react'
import { Button, Input, Select, DetailHeader, DetailSection, DetailGrid, DetailContent } from '../../components'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import ServiceStatusWidget from './ServiceStatusWidget'

export default function GeneralSection({ settings, updateSetting, handleSave, saving, canWrite }) {
  const { t } = useTranslation()
  return (
    <DetailContent>
      <DetailHeader
        icon={Gear}
        title={t('settings.helpGeneral')}
        subtitle={t('settings.generalSubtitle')}
      />
      <DetailSection title={t('settings.subtitle')} icon={Gear} iconClass="icon-bg-blue">
        <div className="space-y-4">
          <Input
            label={t('settings.systemName')}
            value={settings.system_name || ''}
            onChange={(e) => updateSetting('system_name', e.target.value)}
            helperText={t('settings.systemNameHelper')}
          />
          <Input
            label={t('settings.baseUrl')}
            value={settings.base_url || ''}
            onChange={(e) => updateSetting('base_url', e.target.value)}
            placeholder={t('settings.baseUrlPlaceholder')}
            helperText={t('settings.baseUrlHelper')}
          />
          <Input
            label={t('settings.protocolBaseUrl')}
            value={settings.protocol_base_url || ''}
            onChange={(e) => updateSetting('protocol_base_url', e.target.value)}
            placeholder="http://pki.example.com"
            helperText={t('settings.protocolBaseUrlHelper')}
          />
          <Input
            label={t('settings.httpProtocolPort')}
            type="number"
            min={0}
            max={65535}
            value={settings.http_protocol_port ?? 8080}
            onChange={(e) => {
              const val = parseInt(e.target.value) || 0
              updateSetting('http_protocol_port', Math.min(65535, Math.max(0, val)))
            }}
            placeholder="8080"
            helperText={t('settings.httpProtocolPortHelper')}
          />
        </div>
      </DetailSection>
      <DetailSection title={t('settings.sessionTimezone')} icon={Clock} iconClass="icon-bg-teal">
        <div className="space-y-4">
          <Input
            label={t('settings.sessionTimeout')}
            type="number"
            value={Math.round((settings.session_timeout || 28800) / 60)}
            onChange={(e) => updateSetting('session_timeout', parseInt(e.target.value) * 60)}
            min="5"
            max="1440"
            helperText={t('settings.sessionTimeoutHelper')}
          />
          <Input
            label={t('settings.maxLoginAttempts')}
            type="number"
            value={settings.max_login_attempts || 5}
            onChange={(e) => updateSetting('max_login_attempts', parseInt(e.target.value))}
            min="3"
            max="20"
            helperText={t('settings.maxLoginAttemptsHelper')}
          />
          <Input
            label={t('settings.lockoutDuration')}
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
              { value: 'short', label: `${t('settings.dateFormats.short')} — Jan 6, 2026` },
              { value: 'long', label: `${t('settings.dateFormats.long')} — January 6, 2026` },
              { value: 'iso', label: `${t('settings.dateFormats.iso')} — 2026-01-06` },
              { value: 'eu', label: `${t('settings.dateFormats.eu')} — 06/01/2026` },
              { value: 'us', label: `${t('settings.dateFormats.us')} — 01/06/2026` },
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
          {canWrite('settings') && (
            <div className="pt-2">
              <Button type="button" onClick={() => handleSave('general')} disabled={saving}>
                <FloppyDisk size={16} />
                {t('common.saveChanges')}
              </Button>
            </div>
          )}
        </div>
      </DetailSection>
      <ServiceStatusWidget />
    </DetailContent>
  )
}
