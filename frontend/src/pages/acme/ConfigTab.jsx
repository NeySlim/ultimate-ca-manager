import { useTranslation } from 'react-i18next'
import { FloppyDisk, Globe, ArrowsClockwise, Lightning } from '@phosphor-icons/react'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import { Select, Button, HelpCard, CompactSection, CompactGrid, CompactField } from '../../components'

export default function ConfigTab({ acmeSettings, cas, updateSetting, onSaveConfig, saving, revokeSuperseded, onRevokeSupersededChange, onToggleRevokeOnRenewal, canWrite }) {
  const { t } = useTranslation()

  return (
    <div className="p-4 space-y-4">
      <HelpCard variant="info" title={t('common.aboutAcme')} compact>
        {t('acme.aboutAcmeDesc')}
      </HelpCard>

      <CompactSection title={t('acme.acmeServer')} icon={Globe}>
        <div className="space-y-3">
          <ToggleSwitch
            checked={acmeSettings.enabled || false}
            onChange={(val) => updateSetting('enabled', val)}
            disabled={!canWrite}
            label={t('acme.enableAcmeServer')}
            description={t('acme.enableAcmeServerDesc')}
          />

          <Select
            label={t('acme.defaultIssuingCA')}
            value={acmeSettings.issuing_ca_id?.toString() || ''}
            onChange={(val) => updateSetting('issuing_ca_id', val ? parseInt(val) : null)}
            disabled={!acmeSettings.enabled || !canWrite}
            placeholder={t('common.acmeSelectCA')}
            options={cas.map(ca => ({ 
              value: ca.id.toString(), 
              label: ca.name || ca.common_name 
            }))}
          />
        </div>
      </CompactSection>

      <CompactSection title={t('acme.renewalPolicy')} icon={ArrowsClockwise}>
        <div className="space-y-2">
          <ToggleSwitch
            checked={acmeSettings.revoke_on_renewal || false}
            onChange={onToggleRevokeOnRenewal}
            disabled={!canWrite}
            label={t('acme.revokeOnRenewal')}
            description={t('acme.revokeOnRenewalDesc')}
          />
          
          {!acmeSettings.revoke_on_renewal && acmeSettings.superseded_count > 0 && (
            <label className="flex items-center gap-3 cursor-pointer ml-7 p-2 rounded-lg hover:bg-tertiary-op50 transition-colors">
              <input
                type="checkbox"
                checked={revokeSuperseded}
                onChange={(e) => onRevokeSupersededChange(e.target.checked)}
                className="w-4 h-4 rounded border-border bg-bg-tertiary text-accent-warning focus:ring-accent-warning-op50"
              />
              <div>
                <p className="text-sm text-accent-warning font-medium">
                  {t('acme.revokeExistingSuperseded', { count: acmeSettings.superseded_count })}
                </p>
                <p className="text-xs text-text-secondary">{t('acme.revokeExistingSupersededDesc')}</p>
              </div>
            </label>
          )}
        </div>
      </CompactSection>

      <CompactSection title={t('acme.endpoints')} icon={Lightning}>
        <CompactGrid columns={1}>
          <CompactField 
            autoIcon="environment"
            label={t('acme.directory')} 
            value={`${window.location.origin}/acme/directory`}
            mono
            copyable
          />
        </CompactGrid>
        <p className="text-xs text-text-tertiary mt-2">
          {t('acme.certbotUsage')} <code className="bg-bg-tertiary px-1 rounded">--server {window.location.origin}/acme/directory</code>
        </p>
      </CompactSection>

      {canWrite && (
        <div className="flex gap-2 pt-3 border-t border-border">
          <Button type="button" onClick={onSaveConfig} disabled={saving}>
            <FloppyDisk size={14} />
            {saving ? t('common.saving') : t('common.saveConfiguration')}
          </Button>
        </div>
      )}
    </div>
  )
}
