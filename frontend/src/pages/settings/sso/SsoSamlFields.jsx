import { useTranslation } from 'react-i18next'
import { Btn, RecordList } from '../../../components/atelier'
import { Input, Select, Textarea, ToggleSwitch, Fold, Notice } from '../../../components/atelier/Form'
import CopyableUrl from '../CopyableUrl'
import MappingEditor from '../MappingEditor'
import RoleMappingEditor from '../RoleMappingEditor'
import LegacyGroupsNotice from './LegacyGroupsNotice'
import ProvisioningNotice, { hasRoleRules } from './ProvisioningNotice'
import TestConnectionButton from './TestConnectionButton'
import SignInTestPanel from './SignInTestPanel'
import { formatDate } from '../../../lib/utils'

export const NAMEID_UNSPECIFIED = 'urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified'
const NAME_ID_FORMATS = [
  { value: NAMEID_UNSPECIFIED, labelKey: 'sso.nameIdUnspecified' },
  { value: 'urn:oasis:names:tc:SAML:2.0:nameid-format:persistent', labelKey: 'sso.nameIdPersistent' },
  { value: 'urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress', labelKey: 'sso.nameIdEmail' },
  { value: 'urn:oasis:names:tc:SAML:2.0:nameid-format:transient', labelKey: 'sso.nameIdTransient' },
]

// Common SAML attribute Names that carry groups, by origin. None is read by default:
// a click adds a visible "→ groups" row the operator saves (or removes) himself.
const SAML_GROUP_SHORTCUTS = [
  { name: 'Role', originKey: 'sso.samlGroupShortcutKeycloakRoles' },
  { name: 'member', originKey: 'sso.samlGroupShortcutKeycloakGroups' },
  { name: 'memberOf', originKey: 'sso.samlGroupShortcutMemberOf' },
  { name: 'urn:oid:1.3.6.1.4.1.5923.1.5.1.1', originKey: 'sso.samlGroupShortcutIsMemberOf' },
]

export default function SsoSamlFields({
  formData,
  handleChange,
  provider,
  testingConnection,
  connectionStatus,
  fetchingMetadata,
  fetchIdpMetadata,
  availableCerts,
  roleOptions,
  defaultRoleOptions,
  customRoles,
  spEntityId,
  spMetadataUrl,
  spOriginUnconfigured,
  samlAcsUrl,
  samlSloUrl,
  handleTestConnection,
  dirty,
}) {
  const { t } = useTranslation()

  return (
    <>
      {spOriginUnconfigured && <Notice tone="warn">{t('sso.spOriginNotConfigured')}</Notice>}
      <Fold title={t('sso.idpSection')} defaultOpen>
        {/* The metadata URL and the button that reads it, on one line (the issue form's inline row) */}
        <div className="field full">
          <label htmlFor="sso-saml-metadata">{t('sso.metadataUrl')}</label>
          <div className="inline-row">
            <input id="sso-saml-metadata" value={formData.saml_metadata_url} autoComplete="off" spellCheck={false}
              placeholder="https://idp.example.com/saml/metadata" aria-describedby="hint-sso-saml-metadata"
              onChange={e => handleChange('saml_metadata_url', e.target.value)} />
            <Btn icon="download" onClick={fetchIdpMetadata} disabled={fetchingMetadata || !formData.saml_metadata_url || undefined}>
              {t('sso.fetchMetadata')}
            </Btn>
          </div>
          <small id="hint-sso-saml-metadata">{t('sso.metadataUrlHelp')}</small>
        </div>
        <Input id="sso-saml-entity" full label={t('sso.entityId')} value={formData.saml_entity_id} onChange={e => handleChange('saml_entity_id', e.target.value)} placeholder="https://idp.example.com/saml/metadata" />
        <Input id="sso-saml-sso-url" label={t('sso.ssoURL')} value={formData.saml_sso_url} onChange={e => handleChange('saml_sso_url', e.target.value)} placeholder="https://idp.example.com/saml/sso" />
        <Input id="sso-saml-slo-url" label={t('sso.sloURL')} value={formData.saml_slo_url} onChange={e => handleChange('saml_slo_url', e.target.value)} placeholder="https://idp.example.com/saml/slo" />
        <Textarea id="sso-saml-certificate" label={t('sso.certificate')} value={formData.saml_certificate} onChange={e => handleChange('saml_certificate', e.target.value)}
          rows={4} placeholder="-----BEGIN CERTIFICATE-----..." mono />
        <ToggleSwitch checked={formData.saml_sign_requests} onChange={(val) => handleChange('saml_sign_requests', val)}
          label={t('sso.signRequests')} description={t('sso.signRequestsHelp')} />
        <ToggleSwitch checked={formData.saml_allow_idp_initiated} onChange={(val) => handleChange('saml_allow_idp_initiated', val)}
          label={t('sso.allowIdpInitiated')} description={t('sso.allowIdpInitiatedHelp')} />
        <Select id="sso-saml-sp-cert" label={t('sso.spCertificate')} value={formData.saml_sp_cert_source}
          onChange={value => handleChange('saml_sp_cert_source', value)}
          options={availableCerts.length > 0
            ? availableCerts.map(c => ({ value: c.id, label: c.not_after ? `${c.label} (${formatDate(c.not_after)})` : c.label }))
            : [{ value: 'https', label: t('sso.httpsDefault') }]} />
        <Select id="sso-saml-nameid" label={t('sso.nameIdFormat')} value={formData.saml_name_id_format}
          onChange={value => handleChange('saml_name_id_format', value)}
          options={NAME_ID_FORMATS.map(f => ({ value: f.value, label: t(f.labelKey) }))} hint={t('sso.nameIdFormatHelp')} />
        <ToggleSwitch checked={formData.saml_verify_ssl} onChange={(val) => handleChange('saml_verify_ssl', val)} label={t('sso.verifySsl')} />
        {!formData.saml_verify_ssl && <Notice tone="warn">{t('sso.sslWarning')}</Notice>}
        {formData.saml_verify_ssl && (
          <Textarea id="sso-saml-ca-bundle" label={t('sso.caBundleLabel')} value={formData.saml_ca_bundle} onChange={e => handleChange('saml_ca_bundle', e.target.value)}
            placeholder={'-----BEGIN CERTIFICATE-----\n...'} rows={4} mono hint={t('sso.caBundleHelp')} />
        )}
        {provider?.id && (
          <TestConnectionButton onClick={handleTestConnection} testing={testingConnection} dirty={dirty} status={connectionStatus} />
        )}
        <SignInTestPanel provider={provider} dirty={dirty} formData={formData} handleChange={handleChange} />
      </Fold>

      <Fold title={t('sso.spSection')}>
        <Notice>{t('sso.spMetadataHelp')}</Notice>
        <div className="field full">
          <RecordList>
            <CopyableUrl label={t('sso.spMetadataXml')} value={spMetadataUrl} description={t('sso.spMetadataXmlDesc')} />
            <CopyableUrl label={t('sso.spEntityId')} value={spEntityId} />
            <CopyableUrl label={t('sso.acsUrl')} value={samlAcsUrl} description={t('sso.acsUrlDesc')} />
            <CopyableUrl label={t('sso.spSloUrl')} value={samlSloUrl} />
          </RecordList>
        </div>
      </Fold>

      <Fold title={t('sso.attributeRoleMappingSection')}>
        <MappingEditor legend={t('sso.attributeMapping')} hint={t('sso.attributeMappingHelp')}
          value={formData.attribute_mapping} onChange={val => handleChange('attribute_mapping', val)}
          keyLabel={t('sso.ssoAttribute')} valueLabel={t('sso.ucmField')} keyPlaceholder="e.g., preferred_username" valuePlaceholder="e.g., username" />
        <LegacyGroupsNotice mapping={formData.attribute_mapping} />
        <div className="field full">
          <span id="sso-saml-shortcuts">{t('sso.samlGroupShortcuts')}</span>
          <div className="row-actions" role="group" aria-labelledby="sso-saml-shortcuts">
            {SAML_GROUP_SHORTCUTS.map(({ name, originKey }) => (
              <button key={name} type="button" className="btn"
                disabled={Object.prototype.hasOwnProperty.call(formData.attribute_mapping || {}, name) || undefined}
                onClick={() => handleChange('attribute_mapping', { ...(formData.attribute_mapping || {}), [name]: 'groups' })}>
                <span className="mono">{name}</span>
                <span className="muted">{t(originKey)}</span>
              </button>
            ))}
          </div>
        </div>
        <RoleMappingEditor legend={t('sso.roleMapping')} hint={t('sso.roleMappingHelp')}
          value={formData.role_mapping} onChange={val => handleChange('role_mapping', val)}
          keyLabel={t('sso.externalGroup')} keyPlaceholder="e.g., pki-admins" roleOptions={roleOptions} customRoles={customRoles} />
      </Fold>

      <Fold title={t('sso.provisioningSection')} defaultOpen={!hasRoleRules(formData.role_mapping)}>
        <ProvisioningNotice formData={formData} />
        <Select id="sso-saml-default-role" label={t('sso.defaultRole')} value={formData.default_role} onChange={value => handleChange('default_role', value)} options={defaultRoleOptions} />
        <ToggleSwitch checked={formData.auto_create_users} onChange={(val) => handleChange('auto_create_users', val)} label={t('sso.autoCreateUsers')} />
        <ToggleSwitch checked={formData.auto_update_users} onChange={(val) => handleChange('auto_update_users', val)} label={t('sso.autoUpdateUsers')} />
        <ToggleSwitch checked={formData.sync_role_on_login} onChange={(val) => handleChange('sync_role_on_login', val)}
          label={t('sso.syncRoleOnLogin')} description={t('sso.syncRoleOnLoginHelp')} />
      </Fold>
    </>
  )
}
