/**
 * Automatic renewal: on or off, the delay and the sources, the notifications and their
 * recipients, then a run now with its result on the same line (the mockup's test zone).
 */
import { useTranslation } from 'react-i18next'
import { ArrowsClockwise, Lightning, CheckCircle, WarningCircle, Question } from '@phosphor-icons/react'
import { Button, Input } from '../../components'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import TagsInput from '../../components/ui/TagsInput'
import { FormGroup } from '../../components/sectioned'

const SOURCES = ['manual', 'scep', 'acme', 'est']
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export default function AutoRenewalSection({
  arSettings,
  setArSettings,
  arLoading,
  arRunning,
  arRunResult,
  handleArRunNow,
}) {
  const { t } = useTranslation()

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

  if (arLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="w-6 h-6 border-2 border-accent-primary-op30 border-t-accent-primary rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <>
      <FormGroup title={t('settings.autoRenewal')}>
        <div className="space-y-4">
          <ToggleSwitch
            label={t('settings.autoRenewalEnabled')}
            description={t('settings.autoRenewalEnabledDesc')}
            checked={arSettings.enabled}
            onChange={(val) => setArSettings((prev) => ({ ...prev, enabled: val }))}
          />
          <Input
            className="sf-short"
            label={t('settings.autoRenewalDays')}
            type="number"
            inputMode="numeric"
            min={1}
            max={365}
            value={arSettings.days_before_expiry}
            onChange={(e) => setArSettings((prev) => ({ ...prev, days_before_expiry: parseInt(e.target.value, 10) || 0 }))}
            helperText={t('settings.autoRenewalDaysHelp')}
          />
          <div className="ui-field">
            <span className="ui-label" id="ar-sources">{t('settings.autoRenewalSources')}</span>
            <div className="ui-segmented" role="group" aria-labelledby="ar-sources">
              {SOURCES.map((src) => (
                <button
                  key={src}
                  type="button"
                  aria-pressed={arSettings.renewal_sources.includes(src)}
                  onClick={() => toggleSource(src)}
                >
                  {t(`settings.autoRenewalSource_${src}`)}
                </button>
              ))}
            </div>
            <p className="ui-help">{t('settings.autoRenewalSourcesHelp')}</p>
          </div>
        </div>
      </FormGroup>

      <FormGroup title={t('settings.autoRenewalNotifications')}>
        <div className="space-y-4">
          <ToggleSwitch
            label={t('settings.autoRenewalNotifyOnRenewal')}
            checked={arSettings.notify_on_renewal}
            onChange={(val) => setArSettings((prev) => ({ ...prev, notify_on_renewal: val }))}
          />
          <ToggleSwitch
            label={t('settings.autoRenewalNotifyOnFailure')}
            checked={arSettings.notify_on_failure}
            onChange={(val) => setArSettings((prev) => ({ ...prev, notify_on_failure: val }))}
          />
          <TagsInput
            label={t('settings.autoRenewalNotifyEmails')}
            value={arSettings.notify_emails || []}
            onChange={(tags) => setArSettings((prev) => ({ ...prev, notify_emails: tags }))}
            placeholder="ops@example.com"
            helperText={t('settings.autoRenewalNotifyEmailsHelp')}
            validate={(v) => EMAIL.test(v)}
          />
        </div>
        <div className="sf-test sf-under-group">
          <Button
            type="button"
            variant="secondary"
            onClick={handleArRunNow}
            disabled={arRunning || !arSettings.enabled}
          >
            {arRunning ? <ArrowsClockwise size={14} className="animate-spin" /> : <Lightning size={14} />}
            {t('settings.autoRenewalRunNow')}
          </Button>
          {arRunResult ? (
            <p className={`sf-test-result ${arRunResult.ok ? 'is-good' : 'is-bad'}`} role="status">
              {arRunResult.ok ? <CheckCircle aria-hidden="true" /> : <WarningCircle aria-hidden="true" />}
              <span>{arRunResult.text}</span>
            </p>
          ) : (
            <p className="sf-test-result">
              <Question aria-hidden="true" />
              <span>{arSettings.enabled ? t('settings.autoRenewalRunHint') : t('settings.autoRenewalRunDisabled')}</span>
            </p>
          )}
        </div>
      </FormGroup>
    </>
  )
}
