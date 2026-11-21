import { useTranslation } from 'react-i18next'
import { RecordList } from '../../../components/atelier'
import { Input, SecretInput, Select, Textarea, ToggleSwitch, SegmentedField, Fold, Notice } from '../../../components/atelier/Form'
import CopyableUrl from '../CopyableUrl'
import MappingEditor from '../MappingEditor'
import RoleMappingEditor from '../RoleMappingEditor'
import LegacyGroupsNotice from './LegacyGroupsNotice'
import ProvisioningNotice, { hasRoleRules } from './ProvisioningNotice'
import TestConnectionButton from './TestConnectionButton'
import SignInTestPanel from './SignInTestPanel'

export default function SsoOAuth2Fields({
  formData,
  handleChange,
  provider,
  testingConnection,
  connectionStatus,
  oauth2Preset,
  applyOAuth2Preset,
  roleOptions,
  defaultRoleOptions,
  customRoles,
  oauthCallbackUrl,
  handleTestConnection,
  dirty,
  secretProps,
}) {
  const { t } = useTranslation()
  // Accepted tenants: Entra multi-tenant only, so shown for its preset or once set
  const hasTenants = !!(formData.oauth2_tenants || '').trim()
  const showTenants = hasTenants || oauth2Preset === 'azure'
    || (formData.oauth2_issuer || '').includes('login.microsoftonline.com')

  return (
    <>
      <Fold title={t('sso.oauth2Preset')} defaultOpen>
        <SegmentedField id="sso-oauth2-preset" label={t('sso.oauth2Preset')} hint={t('sso.oauth2PresetHelp')}
          options={[
            { value: 'custom', label: t('sso.oauth2PresetCustom') },
            { value: 'azure', label: t('sso.oauthProviders.azure') },
            { value: 'google', label: t('sso.oauthProviders.google') },
            { value: 'github', label: t('sso.oauthProviders.github') },
          ]}
          pressed={(p) => oauth2Preset === p} onPick={applyOAuth2Preset} />
      </Fold>

      <Fold title={t('sso.connectionSection')} defaultOpen>
        <Input id="sso-oauth2-client-id" label={t('common.clientId')} value={formData.oauth2_client_id} onChange={e => handleChange('oauth2_client_id', e.target.value)} />
        <SecretInput id="sso-oauth2-client-secret" label={t('common.clientSecret')} value={formData.oauth2_client_secret}
          onChange={e => handleChange('oauth2_client_secret', e.target.value)} hasExistingValue={!!provider?.oauth2_client_secret} {...secretProps} />
        {['oauth2_auth_url', 'oauth2_token_url', 'oauth2_issuer'].some(k => (formData[k] || '').includes('{tenant}')) && (
          <Notice tone="warn">{t('sso.tenantPlaceholderHint')}</Notice>
        )}
        <Input id="sso-oauth2-auth-url" full label={t('sso.authUrl')} value={formData.oauth2_auth_url} onChange={e => handleChange('oauth2_auth_url', e.target.value)} placeholder={t('sso.authUrlPlaceholder')} />
        <Input id="sso-oauth2-token-url" full label={t('sso.tokenUrl')} value={formData.oauth2_token_url} onChange={e => handleChange('oauth2_token_url', e.target.value)} placeholder={t('sso.tokenUrlPlaceholder')} />
        <Input id="sso-oauth2-userinfo-url" full label={t('sso.userinfoUrl')} value={formData.oauth2_userinfo_url} onChange={e => handleChange('oauth2_userinfo_url', e.target.value)} placeholder={t('sso.userinfoUrlPlaceholder')} />
        <Input id="sso-oauth2-scopes" label={t('sso.scopes')} value={formData.oauth2_scopes} onChange={e => handleChange('oauth2_scopes', e.target.value)} placeholder={t('sso.scopesPlaceholder')} />
        <Input id="sso-oauth2-issuer" label={t('sso.oidcIssuer')} value={formData.oauth2_issuer} onChange={e => handleChange('oauth2_issuer', e.target.value)}
          placeholder="https://idp.example.com/realms/main" hint={t('sso.oidcIssuerHelp')} />
        <Input id="sso-oauth2-jwks" full label={t('sso.oidcJwksUri')} value={formData.oauth2_jwks_uri} onChange={e => handleChange('oauth2_jwks_uri', e.target.value)}
          placeholder="https://idp.example.com/.well-known/jwks.json" hint={t('sso.oidcJwksUriHelp')} />
        {showTenants && (
          <Textarea id="sso-oauth2-tenants" label={t('sso.oidcTenants')} value={formData.oauth2_tenants} onChange={e => handleChange('oauth2_tenants', e.target.value)}
            placeholder="00000000-0000-0000-0000-000000000000" rows={3} mono hint={t('sso.oidcTenantsHelp')} />
        )}
        {showTenants && (
          <Textarea id="sso-oauth2-role-tenants" label={t('sso.oidcRoleTenants')} value={formData.oauth2_role_tenants} onChange={e => handleChange('oauth2_role_tenants', e.target.value)}
            placeholder="00000000-0000-0000-0000-000000000000" rows={2} mono hint={t('sso.oidcRoleTenantsHelp')} />
        )}
        {/* With role rules, a tenant whose roles are not honoured is refused at sign-in */}
        {hasTenants && hasRoleRules(formData.role_mapping) && !(formData.oauth2_role_tenants || '').trim() && (
          <Notice tone="warn">{t('sso.oidcRoleTenantsNoneWarning')}</Notice>
        )}
        {hasTenants && !formData.id_token_verify && <Notice tone="warn">{t('sso.oidcTenantsNeedVerify')}</Notice>}
        <ToggleSwitch checked={formData.id_token_verify} onChange={(val) => handleChange('id_token_verify', val)} label={t('sso.idTokenVerify')} />
        {oauth2Preset === 'github' && <Notice>{t('sso.githubNotOidc')}</Notice>}
        {formData.id_token_verify && !formData.oauth2_issuer && <Notice tone="warn">{t('sso.idTokenVerifyIssuerMissing')}</Notice>}
        {!formData.id_token_verify && <Notice tone="warn">{t('sso.idTokenVerifyWarning')}</Notice>}
        <div className="field full">
          <RecordList><CopyableUrl label={t('sso.redirectUri')} value={oauthCallbackUrl} /></RecordList>
        </div>
        <ToggleSwitch checked={formData.oauth2_verify_ssl} onChange={(val) => handleChange('oauth2_verify_ssl', val)} label={t('sso.verifySsl')} />
        {!formData.oauth2_verify_ssl && <Notice tone="warn">{t('sso.sslWarning')}</Notice>}
        {formData.oauth2_verify_ssl && (
          <Textarea id="sso-oauth2-ca-bundle" label={t('sso.caBundleLabel')} value={formData.oauth2_ca_bundle} onChange={e => handleChange('oauth2_ca_bundle', e.target.value)}
            placeholder={'-----BEGIN CERTIFICATE-----\n...'} rows={4} mono hint={t('sso.caBundleHelp')} />
        )}
        {provider?.id && (
          <TestConnectionButton onClick={handleTestConnection} testing={testingConnection} dirty={dirty} status={connectionStatus} />
        )}
        <SignInTestPanel provider={provider} dirty={dirty} formData={formData} handleChange={handleChange} />
      </Fold>

      <Fold title={t('sso.attributeRoleMappingSection')}>
        <MappingEditor legend={t('sso.attributeMapping')} hint={t('sso.attributeMappingHelp')}
          value={formData.attribute_mapping} onChange={val => handleChange('attribute_mapping', val)}
          keyLabel={t('sso.ssoAttribute')} valueLabel={t('sso.ucmField')} keyPlaceholder="e.g., preferred_username" valuePlaceholder="e.g., username" />
        <LegacyGroupsNotice mapping={formData.attribute_mapping} />
        <RoleMappingEditor legend={t('sso.roleMapping')} hint={t('sso.roleMappingHelp')}
          value={formData.role_mapping} onChange={val => handleChange('role_mapping', val)}
          keyLabel={t('sso.externalGroup')} keyPlaceholder="e.g., pki-admins" roleOptions={roleOptions} customRoles={customRoles} />
      </Fold>

      <Fold title={t('sso.provisioningSection')} defaultOpen={!hasRoleRules(formData.role_mapping)}>
        <ProvisioningNotice formData={formData} />
        <Select id="sso-oauth2-default-role" label={t('sso.defaultRole')} value={formData.default_role} onChange={value => handleChange('default_role', value)} options={defaultRoleOptions} />
        <ToggleSwitch checked={formData.auto_create_users} onChange={(val) => handleChange('auto_create_users', val)} label={t('sso.autoCreateUsers')} />
        <ToggleSwitch checked={formData.auto_update_users} onChange={(val) => handleChange('auto_update_users', val)} label={t('sso.autoUpdateUsers')} />
        <ToggleSwitch checked={formData.sync_role_on_login} onChange={(val) => handleChange('sync_role_on_login', val)}
          label={t('sso.syncRoleOnLogin')} description={t('sso.syncRoleOnLoginHelp')} />
      </Fold>
    </>
  )
}
