import { useTranslation } from 'react-i18next'
import { Plugs, Lightning, TreeStructure, UserPlus } from '@phosphor-icons/react'
import { Button, Input, Select, Textarea, LoadingSpinner, CompactSection } from '../../../components'
import { ToggleSwitch } from '../../../components/ui/ToggleSwitch'
import CopyableUrl from '../CopyableUrl'
import MappingEditor from '../MappingEditor'

export default function SsoOAuth2Fields({
  formData,
  handleChange,
  provider,
  testingConnection,
  connectionBadge,
  oauth2Preset,
  applyOAuth2Preset,
  roleOptions,
  oauthCallbackUrl,
  handleTestConnection,
}) {
  const { t } = useTranslation()

  return (
    <div className="space-y-3">
      {/* Provider Preset */}
      <CompactSection title={t('sso.oauth2Preset')} icon={Lightning} collapsible defaultOpen>
        <div className="space-y-3">
          <p className="text-xs text-text-muted">{t('sso.oauth2PresetHelp')}</p>
          <div className="flex gap-2 flex-wrap">
            {[
              { id: 'custom', label: t('sso.oauth2PresetCustom') },
              { id: 'azure', label: t('sso.oauthProviders.azure') },
              { id: 'google', label: t('sso.oauthProviders.google') },
              { id: 'github', label: t('sso.oauthProviders.github') },
            ].map(preset => (
              <button
                key={preset.id}
                type="button"
                onClick={() => applyOAuth2Preset(preset.id)}
                className={`px-3 py-1.5 text-xs rounded-lg border transition-all ${
                  oauth2Preset === preset.id
                    ? 'border-accent bg-accent-op10 text-accent-primary font-medium'
                    : 'border-border bg-bg-secondary hover:bg-bg-tertiary text-text-secondary'
                }`}
              >
                {preset.label}
              </button>
            ))}
          </div>
        </div>
      </CompactSection>

      {/* Connection */}
      <CompactSection
        title={<span className="flex items-center">{t('sso.connectionSection')}{connectionBadge}</span>}
        icon={Plugs}
        collapsible
        defaultOpen
      >
        <div className="space-y-3">
          <Input label={t('common.clientId')} value={formData.oauth2_client_id} onChange={e => handleChange('oauth2_client_id', e.target.value)} />
          <Input label={t('common.clientSecret')} type="password" noAutofill value={formData.oauth2_client_secret} onChange={e => handleChange('oauth2_client_secret', e.target.value)} hasExistingValue={!!provider?.oauth2_client_secret} />
          <Input label={t('sso.authUrl')} value={formData.oauth2_auth_url} onChange={e => handleChange('oauth2_auth_url', e.target.value)} placeholder={t('sso.authUrlPlaceholder')} />
          <Input label={t('sso.tokenUrl')} value={formData.oauth2_token_url} onChange={e => handleChange('oauth2_token_url', e.target.value)} placeholder={t('sso.tokenUrlPlaceholder')} />
          <Input label={t('sso.userinfoUrl')} value={formData.oauth2_userinfo_url} onChange={e => handleChange('oauth2_userinfo_url', e.target.value)} placeholder={t('sso.userinfoUrlPlaceholder')} />
          <Input label={t('sso.scopes')} value={formData.oauth2_scopes} onChange={e => handleChange('oauth2_scopes', e.target.value)} placeholder={t('sso.scopesPlaceholder')} />
          <CopyableUrl label={t('sso.redirectUri')} value={oauthCallbackUrl} />
          <ToggleSwitch checked={formData.oauth2_verify_ssl} onChange={(val) => handleChange('oauth2_verify_ssl', val)} label={t('sso.verifySsl')} size="sm" />
          {!formData.oauth2_verify_ssl && <p className="text-xs text-amber-500">{t('sso.sslWarning')}</p>}
          {formData.oauth2_verify_ssl && (
            <Textarea
              label={t('sso.caBundleLabel')}
              value={formData.oauth2_ca_bundle}
              onChange={e => handleChange('oauth2_ca_bundle', e.target.value)}
              placeholder="-----BEGIN CERTIFICATE-----&#10;..."
              rows={4}
              mono
              helperText={t('sso.caBundleHelp')}
            />
          )}
          {provider?.id && (
            <Button type="button" variant="secondary" size="sm" onClick={handleTestConnection} disabled={testingConnection} className="gap-1.5">
              {testingConnection ? <LoadingSpinner size="xs" /> : <Plugs size={14} />}
              {t('sso.testConnection')}
            </Button>
          )}
        </div>
      </CompactSection>

      {/* Attribute & Role Mapping */}
      <CompactSection title={t('sso.attributeRoleMappingSection')} icon={TreeStructure} collapsible defaultOpen={false}>
        <div className="space-y-3">
          <div>
            <p className="text-xs font-medium text-text-secondary mb-1">{t('sso.attributeMapping')}</p>
            <p className="text-xs text-text-muted mb-2">{t('sso.attributeMappingHelp')}</p>
            <MappingEditor
              value={formData.attribute_mapping}
              onChange={val => handleChange('attribute_mapping', val)}
              keyLabel={t('sso.ssoAttribute')}
              valueLabel={t('sso.ucmField')}
              keyPlaceholder="e.g., preferred_username"
              valuePlaceholder="e.g., username"
            />
          </div>
          <div className="pt-2 border-t border-border">
            <p className="text-xs font-medium text-text-secondary mb-1">{t('sso.roleMapping')}</p>
            <p className="text-xs text-text-muted mb-2">{t('sso.roleMappingHelp')}</p>
            <MappingEditor
              value={formData.role_mapping}
              onChange={val => handleChange('role_mapping', val)}
              keyLabel={t('sso.externalGroup')}
              valueLabel={t('sso.ucmRole')}
              keyPlaceholder="e.g., pki-admins"
              valueOptions={roleOptions}
            />
          </div>
        </div>
      </CompactSection>

      {/* Provisioning */}
      <CompactSection title={t('sso.provisioningSection')} icon={UserPlus} collapsible defaultOpen={false}>
        <div className="space-y-3">
          <Select label={t('sso.defaultRole')} value={formData.default_role} onChange={value => handleChange('default_role', value)} options={roleOptions} />
          <ToggleSwitch checked={formData.auto_create_users} onChange={(val) => handleChange('auto_create_users', val)} label={t('sso.autoCreateUsers')} />
          <ToggleSwitch checked={formData.auto_update_users} onChange={(val) => handleChange('auto_update_users', val)} label={t('sso.autoUpdateUsers')} />
          <ToggleSwitch checked={formData.sync_role_on_login} onChange={(val) => handleChange('sync_role_on_login', val)} label={t('sso.syncRoleOnLogin')} description={t('sso.syncRoleOnLoginHelp')} />
        </div>
      </CompactSection>
    </div>
  )
}
