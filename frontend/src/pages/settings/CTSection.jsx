import { useTranslation } from 'react-i18next'
import { Eye, Trash, Plus, ArrowsClockwise, FloppyDisk } from '@phosphor-icons/react'
import { Button, Input, DetailHeader, DetailSection, DetailContent } from '../../components'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'

export default function CTSection({ ctSettings, setCtSettings, ctLoading, ctSaving, ctNewLogUrl, setCtNewLogUrl, handleCtSave, handleCtAddLogUrl, handleCtRemoveLogUrl }) {
  const { t } = useTranslation()
  return (
    <DetailContent>
      <DetailHeader
        icon={Eye}
        title={t('settings.ct')}
        subtitle={t('settings.ctDescription')}
      />

      {ctLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-6 h-6 border-2 border-accent-primary-op30 border-t-accent-primary rounded-full animate-spin" />
        </div>
      ) : (
        <DetailSection title={t('settings.ct')} icon={Eye} iconClass="icon-bg-cyan">
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium text-text-primary mb-2 block">{t('settings.ctLogUrls')}</label>
              {ctSettings.log_urls?.length > 0 && (
                <div className="space-y-2 mb-3">
                  {ctSettings.log_urls.map((url, i) => (
                    <div key={i} className="flex items-center gap-2 p-2 bg-tertiary-50 border border-border rounded-lg">
                      <span className="flex-1 text-xs font-mono text-text-secondary truncate">{url}</span>
                      <Button type="button" size="sm" variant="danger" onClick={() => handleCtRemoveLogUrl(i)}>
                        <Trash size={14} />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
              <div className="flex gap-2">
                <Input
                  value={ctNewLogUrl}
                  onChange={(e) => setCtNewLogUrl(e.target.value)}
                  placeholder="https://ct.googleapis.com/logs/argon2025h1/"
                  className="flex-1"
                  onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleCtAddLogUrl() } }}
                />
                <Button type="button" variant="secondary" onClick={handleCtAddLogUrl}>
                  <Plus size={14} />
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

            <div className="flex justify-end pt-4 border-t border-border">
              <Button type="button" onClick={handleCtSave} disabled={ctSaving}>
                {ctSaving ? <ArrowsClockwise size={14} className="animate-spin mr-1" /> : <FloppyDisk size={14} className="mr-1" />}
                {t('common.save')}
              </Button>
            </div>
          </div>
        </DetailSection>
      )}
    </DetailContent>
  )
}
