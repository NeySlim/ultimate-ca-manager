/**
 * AutoUpdateSettings — scheduled update check channel + opt-in unattended
 * install (#301). Only the editable fields are sent back on save.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Select, ToggleSwitch } from '../../components/atelier/Form'
import { SettingsGroup } from '../../components/atelier/SettingsView'
import { apiClient } from '../../services'
import { useNotification } from '../../contexts'
import { useSavePart, keptPartDraft } from '../../components/sectioned'

const HOUR_OPTIONS = Array.from({ length: 24 }, (_, h) => ({
  value: h,
  label: `${String(h).padStart(2, '0')}:00`,
}))

export default function AutoUpdateSettings() {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [canAutoUpdate, setCanAutoUpdate] = useState(true)
  const [channel, setChannel] = useState('stable')
  const [autoInstall, setAutoInstall] = useState(false)
  const [hour, setHour] = useState(3)
  const [popupEnabled, setPopupEnabled] = useState(false)
  // Values as loaded or last stored: the page's save bar counts the changes against them
  const [saved, setSaved] = useState(null)

  useEffect(() => {
    let cancelled = false
    apiClient.get('/system/updates/settings')
      .then((response) => {
        if (cancelled) return
        const data = response?.data || response || {}
        const loaded = {
          channel: data.channel || 'stable', autoInstall: !!data.auto_install,
          hour: Number.isInteger(data.hour) ? data.hour : 3, popupEnabled: !!data.popup_enabled,
        }
        // A draft left pending on this tab comes back over what the server holds
        const shown = { ...loaded, ...keptPartDraft('updates:auto') }
        setChannel(shown.channel)
        setAutoInstall(shown.autoInstall)
        setPopupEnabled(shown.popupEnabled)
        setHour(shown.hour)
        setCanAutoUpdate(data.can_auto_update !== false)
        setSaved(loaded)
      })
      .catch(() => {})
      .finally(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [])

  // Stored by the page's save bar, through the same route as before
  const handleSave = async ({ quiet = false } = {}) => {
    setSaving(true)
    try {
      await apiClient.patch('/system/updates/settings', {
        channel,
        auto_install: autoInstall,
        hour,
        popup_enabled: popupEnabled,
      })
      setSaved({ channel, autoInstall, hour, popupEnabled })
      if (!quiet) showSuccess(t('settings.autoUpdateSaved'))
      return { ok: true }
    } catch (err) {
      if (!quiet) showError(err?.message || t('settings.autoUpdateSaveFailed'))
      return { ok: false, message: err?.message || t('settings.autoUpdateSaveFailed') }
    } finally {
      setSaving(false)
    }
  }

  const current = { channel, autoInstall, hour, popupEnabled }
  const count = saved ? Object.keys(current).filter((k) => current[k] !== saved[k]).length : 0
  useSavePart('updates:auto', {
    section: 'updates',
    count,
    draft: saved ? current : undefined,
    save: () => handleSave({ quiet: true }),
    reset: () => {
      if (!saved) return
      setChannel(saved.channel)
      setAutoInstall(saved.autoInstall)
      setHour(saved.hour)
      setPopupEnabled(saved.popupEnabled)
    },
  })

  if (loading) return null

  return (
    <SettingsGroup legend={t('settings.autoUpdateTitle')} hint={t('settings.autoUpdateDesc')} aria-busy={saving || undefined}>
      <Select id="set-update_channel" label={t('settings.autoUpdateChannel')} value={channel} onChange={(val) => setChannel(val)}
        options={[
          { value: 'stable', label: t('settings.autoUpdateChannelStable') },
          { value: 'rc', label: t('settings.autoUpdateChannelRc') },
        ]} />
      {autoInstall && canAutoUpdate && (
        <Select id="set-update_hour" short label={t('settings.autoUpdateHour')} value={hour} onChange={(val) => setHour(Number(val))} options={HOUR_OPTIONS} />
      )}
      <ToggleSwitch id="set-update_auto_install" checked={autoInstall} onChange={(val) => setAutoInstall(val)} label={t('settings.autoUpdateEnable')}
        description={canAutoUpdate ? t('settings.autoUpdateEnableDesc') : t('settings.autoUpdateDockerHint')} disabled={!canAutoUpdate} />
      <ToggleSwitch id="set-update_popup" checked={popupEnabled} onChange={(val) => setPopupEnabled(val)} label={t('settings.updatePopupEnable')}
        description={t('settings.updatePopupEnableDesc')} />
    </SettingsGroup>
  )
}
