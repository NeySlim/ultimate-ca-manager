import { useTranslation } from 'react-i18next'
import { Trash, Plus } from '@phosphor-icons/react'
import { Button, Input } from '../../components'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import { FormGroup } from '../../components/sectioned'

export default function CTSection({ ctSettings, setCtSettings, ctLoading, ctNewLogUrl, setCtNewLogUrl, handleCtAddLogUrl, handleCtRemoveLogUrl }) {
  const { t } = useTranslation()
  return (
    <>

      {ctLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-6 h-6 border-2 border-accent-primary-op30 border-t-accent-primary rounded-full animate-spin" />
        </div>
      ) : (
        <FormGroup title={t('settings.ct')}>
          <div className="space-y-4">
            {/* The logs as the mockup's record list; a new one typed in a full-width field, its button under it */}
            <div className="sf-stack">
              {ctSettings.log_urls?.length > 0 && (
                <ul className="sf-records" aria-label={t('settings.ctLogUrls')}>
                  {ctSettings.log_urls.map((url, i) => (
                    <li key={i}>
                      <div className="sf-record-main"><span className="sf-copy-value">{url}</span></div>
                      <div className="sf-record-actions">
                        <Button type="button" variant="danger" onClick={() => handleCtRemoveLogUrl(i)}
                          aria-label={`${t('common.delete')} ${url}`} title={t('common.delete')}>
                          <Trash size={16} />
                        </Button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              <div className="sf-grid">
                <Input
                  label={t('settings.ctLogUrls')}
                  value={ctNewLogUrl}
                  onChange={(e) => setCtNewLogUrl(e.target.value)}
                  placeholder="https://ct.googleapis.com/logs/us1/argon2027h1/"
                  onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleCtAddLogUrl() } }}
                />
              </div>
              <div className="sf-actions-row">
                <Button type="button" variant="secondary" onClick={handleCtAddLogUrl}>
                  <Plus size={16} />
                  {t('settings.ctAddLogUrl')}
                </Button>
              </div>
            </div>

            <ToggleSwitch
              label={t('settings.ctAutoSubmit')}
              checked={ctSettings.auto_submit}
              onChange={(val) => setCtSettings(prev => ({ ...prev, auto_submit: val }))}
            />

            <ToggleSwitch
              label={t('settings.ctEnabled')}
              checked={ctSettings.enabled}
              onChange={(val) => setCtSettings(prev => ({ ...prev, enabled: val }))}
            />

            {ctSettings.enabled && (
              <ToggleSwitch
                label={t('settings.ctEmbedSct')}
                checked={ctSettings.embed_sct ?? false}
                onChange={(val) => setCtSettings(prev => ({ ...prev, embed_sct: val }))}
              />
            )}

            {ctSettings.enabled && ctSettings.embed_sct && (
              <>
                <ToggleSwitch
                  label={t('settings.ctRequired')}
                  checked={ctSettings.required ?? false}
                  onChange={(val) => setCtSettings(prev => ({ ...prev, required: val }))}
                />
                {ctSettings.required && (
                  <p className="text-xs text-status-warning">{t('settings.ctRequiredWarning')}</p>
                )}
              </>
            )}

          </div>
        </FormGroup>
      )}
    </>
  )
}
