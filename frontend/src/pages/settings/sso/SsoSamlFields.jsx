import { useTranslation } from 'react-i18next'
import { Shield, Globe, TreeStructure, UserPlus, Download } from '@phosphor-icons/react'
import { Button, Input, Select, Textarea, LoadingSpinner, HelpCard, CompactSection } from '../../../components'
import { ToggleSwitch } from '../../../components/ui/ToggleSwitch'
import CopyableUrl from '../CopyableUrl'
import MappingEditor from '../MappingEditor'
import { formatDate } from '../../../lib/utils'

export default function SsoSamlFields({
  formData,
  handleChange,
  provider,
  testingConnection,
  connectionBadge,
  fetchingMetadata,
  fetchIdpMetadata,
  availableCerts,
  roleOptions,
  baseUrl,
  spEntityId,
  samlAcsUrl,
  samlSloUrl,
  handleTestConnection,
}) {
  const { t } = useTranslation()

  return (
    <div className="space-y-3">
      {/* Identity Provider */}
      <CompactSection
        title={<span className="flex items-center">{t('sso.idpSection')}{connectionBadge}</span>}
        icon={Shield}
        collapsible
        defaultOpen
      >
        <div className="space-y-3">
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <Input
                label={t('sso.metadataUrl')}
                value={formData.saml_metadata_url}
                onChange={e => handleChange('saml_metadata_url', e.target.value)}
                placeholder="https://idp.example.com/saml/metadata"
              />
            </div>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={fetchIdpMetadata}
              disabled={fetchingMetadata || !formData.saml_metadata_url}
              className="mb-0.5 gap-1.5 whitespace-nowrap"
            >
              {fetchingMetadata ? <LoadingSpinner size="xs" /> : <Download size={14} />}
              {t('sso.fetchMetadata')}
            </Button>
          </div>
          <HelpCard variant="info" className="text-xs">{t('sso.metadataUrlHelp')}</HelpCard>
          <Input label={t('sso.entityId')} value={formData.saml_entity_id} onChange={e => handleChange('saml_entity_id', e.target.value)} placeholder="https://idp.example.com/saml/metadata" />
          <Input label={t('sso.ssoURL')} value={formData.saml_sso_url} onChange={e => handleChange('saml_sso_url', e.target.value)} placeholder="https://idp.example.com/saml/sso" />
          <Input label={t('sso.sloURL')} value={formData.saml_slo_url} onChange={e => handleChange('saml_slo_url', e.target.value)} placeholder="https://idp.example.com/saml/slo" />
          <Textarea
            label={t('sso.certificate')}
            value={formData.saml_certificate}
            onChange={e => handleChange('saml_certificate', e.target.value)}
            rows={4}
            placeholder="-----BEGIN CERTIFICATE-----..."
            className="font-mono text-xs"
          />
          <ToggleSwitch checked={formData.saml_sign_requests} onChange={(val) => handleChange('saml_sign_requests', val)} label={t('sso.signRequests')} />
          <Select
            label={t('sso.spCertificate')}
            value={formData.saml_sp_cert_source}
            onChange={value => handleChange('saml_sp_cert_source', value)}
            options={availableCerts.length > 0
              ? availableCerts.map(c => ({
                  value: c.id,
                  label: c.not_after ? `${c.label} (${formatDate(c.not_after)})` : c.label,
                }))
              : [{ value: 'https', label: t('sso.httpsDefault') }]
            }
          />
          <ToggleSwitch checked={formData.saml_verify_ssl} onChange={(val) => handleChange('saml_verify_ssl', val)} label={t('sso.verifySsl')} size="sm" />
          {!formData.saml_verify_ssl && <p className="text-xs text-amber-500">{t('sso.sslWarning')}</p>}
          {formData.saml_verify_ssl && (
            <Textarea
              label={t('sso.caBundleLabel')}
              value={formData.saml_ca_bundle}
              onChange={e => handleChange('saml_ca_bundle', e.target.value)}
              placeholder="-----BEGIN CERTIFICATE-----&#10;..."
              rows={4}
              mono
              helperText={t('sso.caBundleHelp')}
            />
          )}
          {provider?.id && (
            <Button type="button" variant="secondary" size="sm" onClick={handleTestConnection} disabled={testingConnection} className="gap-1.5">
              {testingConnection ? <LoadingSpinner size="xs" /> : <Shield size={14} />}
              {t('sso.testConnection')}
            </Button>
          )}
        </div>
      </CompactSection>

      {/* SP Endpoints */}
      <CompactSection title={t('sso.spSection')} icon={Globe} collapsible defaultOpen={false}>
        <div className="space-y-3">
          <HelpCard variant="info" className="text-xs">{t('sso.spMetadataHelp')}</HelpCard>
          <CopyableUrl label={t('sso.spMetadataXml')} value={`${baseUrl}/api/v2/sso/saml/metadata`} description={t('sso.spMetadataXmlDesc')} />
          <CopyableUrl label={t('sso.spEntityId')} value={spEntityId} />
          <CopyableUrl label={t('sso.acsUrl')} value={samlAcsUrl} description={t('sso.acsUrlDesc')} />
          <CopyableUrl label={t('sso.spSloUrl')} value={samlSloUrl} />
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
