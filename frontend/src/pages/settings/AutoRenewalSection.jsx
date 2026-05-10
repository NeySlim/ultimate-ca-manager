import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowsClockwise, FloppyDisk, ClockClockwise, Plus, X, Lightning } from '@phosphor-icons/react'
import { Button, Input, DetailHeader, DetailSection, DetailContent } from '../../components'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'

const SOURCES = ['scep', 'acme', 'est']

export default function AutoRenewalSection({
  arSettings,
  setArSettings,
  arLoading,
  arSaving,
  arRunning,
  handleArSave,
  handleArRunNow,
}) {
  const { t } = useTranslation()
  const [emailInput, setEmailInput] = useState('')

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

  const addEmail = () => {
    const email = emailInput.trim()
    if (!email) return
    if (arSettings.notify_emails.includes(email)) return
    setArSettings((prev) => ({ ...prev, notify_emails: [...prev.notify_emails, email] }))
    setEmailInput('')
  }

  const removeEmail = (idx) => {
    setArSettings((prev) => ({
      ...prev,
      notify_emails: prev.notify_emails.filter((_, i) => i !== idx),
    }))
  }

  return (
    <DetailContent>
      <DetailHeader
        icon={ClockClockwise}
        title={t('settings.autoRenewal')}
        subtitle={t('settings.autoRenewalDescription')}
      />

      {arLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-6 h-6 border-2 border-accent-primary-op30 border-t-accent-primary rounded-full animate-spin" />
        </div>
      ) : (
        <DetailSection
          title={t('settings.autoRenewal')}
          icon={ClockClockwise}
          iconClass="icon-bg-emerald"
        >
          <div className="space-y-5">
            <ToggleSwitch
              label={t('settings.autoRenewalEnabled')}
              description={t('settings.autoRenewalEnabledDesc')}
              checked={arSettings.enabled}
              onChange={(val) => setArSettings((prev) => ({ ...prev, enabled: val }))}
            />

            <div>
              <label className="text-sm font-medium text-text-primary mb-1 block">
                {t('settings.autoRenewalDays')}
              </label>
              <Input
                type="number"
                min={1}
                max={365}
                value={arSettings.days_before_expiry}
                onChange={(e) =>
                  setArSettings((prev) => ({
                    ...prev,
                    days_before_expiry: parseInt(e.target.value, 10) || 0,
                  }))
                }
                className="max-w-[140px]"
              />
              <p className="text-xs text-text-secondary mt-1">
                {t('settings.autoRenewalDaysHelp')}
              </p>
            </div>

            <div>
              <label className="text-sm font-medium text-text-primary mb-2 block">
                {t('settings.autoRenewalSources')}
              </label>
              <div className="flex flex-wrap gap-2">
                {SOURCES.map((src) => {
                  const active = arSettings.renewal_sources.includes(src)
                  return (
                    <button
                      key={src}
                      type="button"
                      onClick={() => toggleSource(src)}
                      className={`px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors ${
                        active
                          ? 'bg-accent-primary text-white border-accent-primary'
                          : 'bg-tertiary-50 text-text-secondary border-border hover:border-accent-primary'
                      }`}
                    >
                      {t(`settings.autoRenewalSource_${src}`)}
                    </button>
                  )
                })}
              </div>
              <p className="text-xs text-text-secondary mt-2">
                {t('settings.autoRenewalSourcesHelp')}
              </p>
            </div>

            <div className="pt-4 border-t border-border">
              <h4 className="text-sm font-semibold text-text-primary mb-3">
                {t('settings.autoRenewalNotifications')}
              </h4>

              <ToggleSwitch
                label={t('settings.autoRenewalNotifyOnRenewal')}
                checked={arSettings.notify_on_renewal}
                onChange={(val) =>
                  setArSettings((prev) => ({ ...prev, notify_on_renewal: val }))
                }
              />

              <div className="mt-3">
                <ToggleSwitch
                  label={t('settings.autoRenewalNotifyOnFailure')}
                  checked={arSettings.notify_on_failure}
                  onChange={(val) =>
                    setArSettings((prev) => ({ ...prev, notify_on_failure: val }))
                  }
                />
              </div>

              <div className="mt-4">
                <label className="text-sm font-medium text-text-primary mb-2 block">
                  {t('settings.autoRenewalNotifyEmails')}
                </label>
                {arSettings.notify_emails?.length > 0 && (
                  <div className="space-y-2 mb-3">
                    {arSettings.notify_emails.map((email, i) => (
                      <div
                        key={i}
                        className="flex items-center gap-2 p-2 bg-tertiary-50 border border-border rounded-lg"
                      >
                        <span className="flex-1 text-xs font-mono text-text-secondary truncate">
                          {email}
                        </span>
                        <Button
                          type="button"
                          size="sm"
                          variant="danger"
                          onClick={() => removeEmail(i)}
                        >
                          <X size={14} />
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
                <div className="flex gap-2">
                  <Input
                    type="email"
                    value={emailInput}
                    onChange={(e) => setEmailInput(e.target.value)}
                    placeholder="ops@example.com"
                    className="flex-1"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        addEmail()
                      }
                    }}
                  />
                  <Button type="button" variant="secondary" onClick={addEmail}>
                    <Plus size={14} />
                    {t('common.add')}
                  </Button>
                </div>
                <p className="text-xs text-text-secondary mt-1">
                  {t('settings.autoRenewalNotifyEmailsHelp')}
                </p>
              </div>
            </div>

            <div className="flex justify-between items-center pt-4 border-t border-border">
              <Button
                type="button"
                variant="secondary"
                onClick={handleArRunNow}
                disabled={arRunning || !arSettings.enabled}
                title={!arSettings.enabled ? t('settings.autoRenewalRunDisabled') : ''}
              >
                {arRunning ? (
                  <ArrowsClockwise size={14} className="animate-spin mr-1" />
                ) : (
                  <Lightning size={14} className="mr-1" />
                )}
                {t('settings.autoRenewalRunNow')}
              </Button>

              <Button type="button" onClick={handleArSave} disabled={arSaving}>
                {arSaving ? (
                  <ArrowsClockwise size={14} className="animate-spin mr-1" />
                ) : (
                  <FloppyDisk size={14} className="mr-1" />
                )}
                {t('common.save')}
              </Button>
            </div>
          </div>
        </DetailSection>
      )}
    </DetailContent>
  )
}
