import { useTranslation } from 'react-i18next'
import { Btn, IconBtn, RecordList, RecordRow, SkeletonPanel } from '../../components/atelier'
import { Input, ToggleSwitch, Notice } from '../../components/atelier/Form'
import { SettingsGroup } from '../../components/atelier/SettingsView'

export default function CTSection({ ctSettings, setCtSettings, ctLoading, ctNewLogUrl, setCtNewLogUrl, handleCtAddLogUrl, handleCtRemoveLogUrl }) {
  const { t } = useTranslation()
  if (ctLoading) return <SkeletonPanel label={t('common.loading')} />
  const set = (key) => (val) => setCtSettings(prev => ({ ...prev, [key]: val }))
  return (
    <>
      {/* The logs as the mockup's record list; a new one typed in a full-width field, its button under it */}
      <SettingsGroup legend={t('settings.ct')} grid={false}>
        {ctSettings.log_urls?.length > 0 && (
          <RecordList label={t('settings.ctLogUrls')}>
            {ctSettings.log_urls.map((url, i) => (
              <RecordRow key={i} title={<span className="mono">{url}</span>}
                action={<IconBtn icon="close" write label={`${t('common.delete')} ${url}`} title={t('common.delete')} onClick={() => handleCtRemoveLogUrl(i)} />} />
            ))}
          </RecordList>
        )}
        <div className="settings-grid">
          <Input id="set-ct_log_url" full label={t('settings.ctLogUrls')} value={ctNewLogUrl} onChange={(e) => setCtNewLogUrl(e.target.value)}
            placeholder="https://ct.googleapis.com/logs/us1/argon2027h1/"
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleCtAddLogUrl() } }} />
        </div>
        <div className="settings-actions">
          <Btn icon="plus" write onClick={handleCtAddLogUrl}>{t('settings.ctAddLogUrl')}</Btn>
        </div>
        <div className="settings-grid">
          <ToggleSwitch id="set-ct_auto_submit" label={t('settings.ctAutoSubmit')} checked={ctSettings.auto_submit} onChange={set('auto_submit')} />
          <ToggleSwitch id="set-ct_enabled" label={t('settings.ctEnabled')} checked={ctSettings.enabled} onChange={set('enabled')} />
          {ctSettings.enabled && (
            <ToggleSwitch id="set-ct_embed_sct" label={t('settings.ctEmbedSct')} checked={ctSettings.embed_sct ?? false} onChange={set('embed_sct')} />
          )}
          {ctSettings.enabled && ctSettings.embed_sct && (
            <ToggleSwitch id="set-ct_required" label={t('settings.ctRequired')} checked={ctSettings.required ?? false} onChange={set('required')} />
          )}
          {ctSettings.enabled && ctSettings.embed_sct && ctSettings.required && <Notice tone="warn">{t('settings.ctRequiredWarning')}</Notice>}
        </div>
      </SettingsGroup>
    </>
  )
}
