/**
 * Automatic renewal: on or off, the delay and the sources, the notifications and their
 * recipients, then a run now with its result on the same line (the mockup's test zone).
 */
import { useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { SkeletonPanel } from '../../components/atelier'
import { NumberInput, ToggleSwitch, SegmentedField, ListInput } from '../../components/atelier/Form'
import { SettingsGroup, SettingsTest } from '../../components/atelier/SettingsView'
import { useRefocusAfter } from '../../hooks/useRefocus'
import { shownNumber, typedNumber } from './numberFields'

const SOURCES = ['manual', 'scep', 'acme', 'est']
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export default function AutoRenewalSection({
  arSettings,
  setArSettings,
  fieldErrors = {},
  arLoading,
  arRunning,
  arRunResult,
  handleArRunNow,
}) {
  const { t } = useTranslation()
  const runRef = useRef(null)
  useRefocusAfter(Boolean(arRunning), runRef)

  const toggleSource = (src) => {
    setArSettings((prev) => {
      const has = prev.renewal_sources.includes(src)
      return {
        ...prev,
        renewal_sources: has
          ? prev.renewal_sources.filter((s) => s !== src)
          : [...prev.renewal_sources, src],
      }
    })
  }

  if (arLoading) return <SkeletonPanel label={t('common.loading')} />

  return (
    <>
      <SettingsGroup legend={t('settings.autoRenewal')}>
        <ToggleSwitch id="set-ar_enabled" label={t('settings.autoRenewalEnabled')} description={t('settings.autoRenewalEnabledDesc')}
          checked={arSettings.enabled} onChange={(val) => setArSettings((prev) => ({ ...prev, enabled: val }))} />
        <NumberInput id="set-ar_days_before_expiry" label={t('settings.autoRenewalDays')} hint={t('settings.autoRenewalDaysHelp')}
          error={fieldErrors['ar.days_before_expiry']} value={shownNumber(arSettings.days_before_expiry)}
          onChange={(e) => setArSettings((prev) => ({ ...prev, days_before_expiry: typedNumber(e) }))} />
        <SegmentedField id="set-ar_sources" label={t('settings.autoRenewalSources')} hint={t('settings.autoRenewalSourcesHelp')}
          options={SOURCES.map((src) => ({ value: src, label: t(`settings.autoRenewalSource_${src}`) }))}
          pressed={(src) => arSettings.renewal_sources.includes(src)} onPick={toggleSource} />
      </SettingsGroup>

      <SettingsGroup legend={t('settings.autoRenewalNotifications')}>
        <ToggleSwitch id="set-ar_notify_on_renewal" label={t('settings.autoRenewalNotifyOnRenewal')} checked={arSettings.notify_on_renewal}
          onChange={(val) => setArSettings((prev) => ({ ...prev, notify_on_renewal: val }))} />
        <ToggleSwitch id="set-ar_notify_on_failure" label={t('settings.autoRenewalNotifyOnFailure')} checked={arSettings.notify_on_failure}
          onChange={(val) => setArSettings((prev) => ({ ...prev, notify_on_failure: val }))} />
        <ListInput id="set-ar_notify_emails" full label={t('settings.autoRenewalNotifyEmails')} value={arSettings.notify_emails || []}
          onChange={(list) => setArSettings((prev) => ({ ...prev, notify_emails: list }))} validate={(v) => EMAIL.test(v)}
          invalidMessage={(bad) => t('settings.alertRecipientsInvalid', { list: bad.join(', ') })}
          placeholder="ops@example.com" hint={t('settings.autoRenewalNotifyEmailsHelp')} />
      </SettingsGroup>

      {/* Run now as the mockup's test zone, last in the frame: the button, then its result on the line */}
      <SettingsTest id="autoRenewal" label={t('settings.autoRenewalRunNow')} icon="refresh" onTest={handleArRunNow}
        busy={Boolean(arRunning) || !arSettings.enabled} buttonRef={runRef}
        result={arRunResult ? { ok: arRunResult.ok, text: arRunResult.text } : null}
        hint={arSettings.enabled ? t('settings.autoRenewalRunHint') : t('settings.autoRenewalRunDisabled')} />
    </>
  )
}
