import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Plugs, MagnifyingGlass, UsersThree, TreeStructure, UserPlus,
  Lightning, Globe, Shield, CheckCircle, XCircle, Download, Play
} from '@phosphor-icons/react'
import {
  Button, Input, Select, Badge, Textarea, LoadingSpinner, HelpCard,
  CompactSection
} from '../../components'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import { ssoService } from '../../services'
import { useNotification } from '../../contexts'
import { formatDate } from '../../lib/utils'
import CopyableUrl from './CopyableUrl'
import MappingEditor from './MappingEditor'

export default function SsoProviderForm({ provider, forcedType, onSave, onCancel }) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const providerType = provider?.provider_type || forcedType || 'ldap'
  const [formData, setFormData] = useState({
    name: provider?.name || '',
    display_name: provider?.display_name || '',
    provider_type: providerType,
    enabled: provider?.enabled ?? false,
    is_default: provider?.is_default ?? false,
    default_role: provider?.default_role || 'viewer',
    auto_create_users: provider?.auto_create_users ?? true,
    auto_update_users: provider?.auto_update_users ?? true,
    sync_role_on_login: provider?.sync_role_on_login ?? false,
    attribute_mapping: provider?.attribute_mapping || {},
    role_mapping: provider?.role_mapping || {},
    // LDAP
    ldap_server: provider?.ldap_server || '',
    ldap_port: provider?.ldap_port || 389,
    ldap_use_ssl: provider?.ldap_use_ssl ?? false,
    ldap_verify_ssl: provider?.ldap_verify_ssl ?? true,
    ldap_ca_bundle: '',
    ldap_bind_dn: provider?.ldap_bind_dn || '',
    ldap_bind_password: '',
    ldap_base_dn: provider?.ldap_base_dn || '',
    ldap_user_filter: provider?.ldap_user_filter || '(uid={username})',
    ldap_group_filter: provider?.ldap_group_filter || '',
    ldap_group_member_attr: provider?.ldap_group_member_attr || 'member',
    ldap_username_attr: provider?.ldap_username_attr || 'uid',
    ldap_email_attr: provider?.ldap_email_attr || 'mail',
    ldap_fullname_attr: provider?.ldap_fullname_attr || 'cn',
    // OAuth2
    oauth2_client_id: provider?.oauth2_client_id || '',
    oauth2_client_secret: '',
    oauth2_auth_url: provider?.oauth2_auth_url || '',
    oauth2_token_url: provider?.oauth2_token_url || '',
    oauth2_userinfo_url: provider?.oauth2_userinfo_url || '',
    oauth2_scopes: provider?.oauth2_scopes?.join(' ') || 'openid profile email',
    oauth2_verify_ssl: provider?.oauth2_verify_ssl ?? true,
    oauth2_ca_bundle: '',
    // SAML
    saml_metadata_url: provider?.saml_metadata_url || '',
    saml_entity_id: provider?.saml_entity_id || '',
    saml_sso_url: provider?.saml_sso_url || '',
    saml_slo_url: provider?.saml_slo_url || '',
    saml_certificate: provider?.saml_certificate || '',
    saml_sign_requests: provider?.saml_sign_requests ?? true,
    saml_sp_cert_source: provider?.saml_sp_cert_source || 'https',
    saml_verify_ssl: provider?.saml_verify_ssl ?? true,
    saml_ca_bundle: '',
  })
  const [fetchingMetadata, setFetchingMetadata] = useState(false)
  const [availableCerts, setAvailableCerts] = useState([])
  const [testingConnection, setTestingConnection] = useState(false)
  const [connectionStatus, setConnectionStatus] = useState(null) // 'success' | 'error' | null
  const [testingMapping, setTestingMapping] = useState(false)
  const [testMappingUsername, setTestMappingUsername] = useState('')
  const [testMappingResult, setTestMappingResult] = useState(null)
  const [oauth2Preset, setOauth2Preset] = useState('custom')

  // Load available certificates when SAML is selected
  useEffect(() => {
    if (formData.provider_type === 'saml') {
      ssoService.getSamlCertificates()
        .then(res => {
          const certs = res.data || res
          setAvailableCerts(Array.isArray(certs) ? certs : [])
        })
        .catch(() => setAvailableCerts([]))
    }
  }, [formData.provider_type])

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  const fetchIdpMetadata = async () => {
    if (!formData.saml_metadata_url) return
    setFetchingMetadata(true)
    try {
      const response = await ssoService.fetchIdpMetadata(formData.saml_metadata_url, {
        provider_id: provider?.id,
        verify_ssl: formData.saml_verify_ssl,
        ca_bundle: formData.saml_ca_bundle || undefined,
      })
      const meta = response.data
      setFormData(prev => ({
        ...prev,
        saml_entity_id: meta.entity_id || prev.saml_entity_id,
        saml_sso_url: meta.sso_url || prev.saml_sso_url,
        saml_slo_url: meta.slo_url || prev.saml_slo_url,
        saml_certificate: meta.certificate || prev.saml_certificate,
      }))
      showSuccess(t('sso.metadataFetched'))
    } catch (err) {
      showError(err.message || t('sso.metadataFetchFailed'))
    } finally {
      setFetchingMetadata(false)
    }
  }

  const handleTestConnection = async () => {
    if (!provider?.id) return
    setTestingConnection(true)
    setConnectionStatus(null)
    try {
      await ssoService.testProvider(provider.id)
      setConnectionStatus('success')
      showSuccess(t('sso.testConnectionSuccess'))
    } catch (err) {
      setConnectionStatus('error')
      showError(err.message || t('sso.testConnectionFailed'))
    } finally {
      setTestingConnection(false)
    }
  }

  const handleTestMapping = async () => {
    if (!provider?.id || !testMappingUsername.trim()) return
    setTestingMapping(true)
    setTestMappingResult(null)
    try {
      const res = await ssoService.testMapping(provider.id, testMappingUsername.trim())
      setTestMappingResult(res.data || res)
    } catch (err) {
      showError(err.message || t('sso.testMappingFailed'))
    } finally {
      setTestingMapping(false)
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    const data = { ...formData }
    delete data._directoryType
    // Don't send empty ca_bundle strings
    if (!data.oauth2_ca_bundle) delete data.oauth2_ca_bundle
    if (!data.saml_ca_bundle) delete data.saml_ca_bundle
    if (!data.ldap_ca_bundle) delete data.ldap_ca_bundle
    if (data.provider_type === 'oauth2') {
      data.oauth2_scopes = data.oauth2_scopes.split(/\s+/).filter(Boolean)
    }
    if (data.attribute_mapping) {
      data.attribute_mapping = Object.fromEntries(
        Object.entries(data.attribute_mapping).filter(([k, v]) => k && v)
      )
    }
    if (data.role_mapping) {
      data.role_mapping = Object.fromEntries(
        Object.entries(data.role_mapping).filter(([k, v]) => k && v)
      )
    }
    onSave(data)
  }

  // Apply OAuth2 preset
  const applyOAuth2Preset = (preset) => {
    setOauth2Preset(preset)
    if (preset === 'azure') {
      setFormData(prev => ({
        ...prev,
        oauth2_auth_url: 'https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize',
        oauth2_token_url: 'https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token',
        oauth2_userinfo_url: 'https://graph.microsoft.com/oidc/userinfo',
        oauth2_scopes: 'openid profile email',
      }))
    } else if (preset === 'google') {
      setFormData(prev => ({
        ...prev,
        oauth2_auth_url: 'https://accounts.google.com/o/oauth2/v2/auth',
        oauth2_token_url: 'https://oauth2.googleapis.com/token',
        oauth2_userinfo_url: 'https://openidconnect.googleapis.com/v1/userinfo',
        oauth2_scopes: 'openid profile email',
      }))
    } else if (preset === 'github') {
      setFormData(prev => ({
        ...prev,
        oauth2_auth_url: 'https://github.com/login/oauth/authorize',
        oauth2_token_url: 'https://github.com/login/oauth/access_token',
        oauth2_userinfo_url: 'https://api.github.com/user',
        oauth2_scopes: 'read:user user:email',
      }))
    }
  }

  // SP metadata URLs
  const baseUrl = window.location.origin
  const spEntityId = `${baseUrl}/api/v2/sso`
  const samlAcsUrl = `${baseUrl}/api/v2/sso/callback/saml`
  const samlSloUrl = `${baseUrl}/api/v2/sso/callback/saml`
  const oauthCallbackUrl = `${baseUrl}/api/v2/sso/callback/oauth2`

  const roleOptions = [
    { value: 'admin', label: t('common.admin') },
    { value: 'operator', label: t('common.operator') },
    { value: 'auditor', label: t('common.auditor') },
    { value: 'viewer', label: t('common.viewer') },
  ]

  // Connection status badge for section header
  const connectionBadge = connectionStatus === 'success' 
    ? <Badge variant="success" size="sm" className="ml-2"><CheckCircle size={12} weight="bold" className="mr-1" />{t('sso.testConnectionSuccess')}</Badge>
    : connectionStatus === 'error'
    ? <Badge variant="error" size="sm" className="ml-2"><XCircle size={12} weight="bold" className="mr-1" />{t('sso.testConnectionFailed')}</Badge>
    : null

  const isLdap = formData.provider_type === 'ldap'
  const isOauth2 = formData.provider_type === 'oauth2'
  const isSaml = formData.provider_type === 'saml'

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4 max-h-[75vh] overflow-y-auto">
      {/* General Settings — always visible */}
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-4">
          <Input
            label={t('common.providerName')}
            value={formData.name}
            onChange={e => handleChange('name', e.target.value)}
            required
            placeholder={t('sso.providerNamePlaceholder')}
          />
          <Input
            label={t('sso.displayName')}
            value={formData.display_name}
            onChange={e => handleChange('display_name', e.target.value)}
            placeholder={t('sso.displayNamePlaceholder')}
          />
        </div>
        <div className="flex gap-6">
          <ToggleSwitch
            checked={formData.enabled}
            onChange={(val) => handleChange('enabled', val)}
            label={t('common.enableProvider')}
          />
          <ToggleSwitch
            checked={formData.is_default}
            onChange={(val) => handleChange('is_default', val)}
            label={t('sso.isDefault')}
          />
        </div>
      </div>

      {/* ── LDAP SECTIONS ── */}
      {isLdap && (
        <div className="space-y-3">
          {/* Section 1: Connection */}
          <CompactSection 
            title={<span className="flex items-center">{t('sso.connectionSection')}{connectionBadge}</span>}
            icon={Plugs} 
            collapsible 
            defaultOpen
          >
            <div className="space-y-3">
              <Select
                label={t('sso.directoryType')}
                value={formData._directoryType || 'custom'}
                onChange={value => {
                  handleChange('_directoryType', value)
                  if (value === 'openldap') {
                    setFormData(prev => ({ ...prev, _directoryType: value, ldap_port: prev.ldap_port || 389, ldap_user_filter: '(uid={username})', ldap_username_attr: 'uid', ldap_email_attr: 'mail', ldap_fullname_attr: 'cn', ldap_group_filter: '(objectClass=groupOfNames)', ldap_group_member_attr: 'member' }))
                  } else if (value === 'ad') {
                    setFormData(prev => ({ ...prev, _directoryType: value, ldap_port: prev.ldap_use_ssl ? 636 : 389, ldap_user_filter: '(sAMAccountName={username})', ldap_username_attr: 'sAMAccountName', ldap_email_attr: 'mail', ldap_fullname_attr: 'displayName', ldap_group_filter: '(objectClass=group)', ldap_group_member_attr: 'memberOf' }))
                  }
                }}
                options={[
                  { value: 'openldap', label: t('sso.ldapTypes.openldap') },
                  { value: 'ad', label: t('sso.ldapTypes.activeDirectory') },
                  { value: 'custom', label: t('common.custom') },
                ]}
              />
              <div className="grid grid-cols-3 gap-4">
                <Input
                  label={t('sso.ldapServer')}
                  value={formData.ldap_server}
                  onChange={e => handleChange('ldap_server', e.target.value)}
                  placeholder={formData._directoryType === 'ad' ? 'dc.example.com' : 'ldap.example.com'}
                  className="col-span-2"
                />
                <Input
                  label={t('common.portLabel')}
                  type="number"
                  value={formData.ldap_port}
                  onChange={e => handleChange('ldap_port', parseInt(e.target.value))}
                />
              </div>
              <ToggleSwitch
                checked={formData.ldap_use_ssl}
                onChange={(val) => {
                  handleChange('ldap_use_ssl', val)
                  if (formData._directoryType === 'ad') {
                    handleChange('ldap_port', val ? 636 : 389)
                  }
                }}
                label={t('sso.ldapUseSsl')}
                size="sm"
              />
              {formData.ldap_use_ssl && (
                <>
                  <ToggleSwitch
                    checked={formData.ldap_verify_ssl}
                    onChange={(val) => handleChange('ldap_verify_ssl', val)}
                    label={t('sso.verifySsl')}
                    size="sm"
                  />
                  {!formData.ldap_verify_ssl && (
                    <p className="text-xs text-amber-500">{t('sso.sslWarning')}</p>
                  )}
                  {formData.ldap_verify_ssl && (
                      <Textarea
                        label={t('sso.caBundleLabel')}
                        value={formData.ldap_ca_bundle}
                        onChange={e => handleChange('ldap_ca_bundle', e.target.value)}
                        placeholder="-----BEGIN CERTIFICATE-----&#10;..."
                        rows={4}
                        mono
                        helperText={t('sso.caBundleHelp')}
                      />
                  )}
                </>
              )}
              <Input
                label={t('sso.bindDn')}
                value={formData.ldap_bind_dn}
                onChange={e => handleChange('ldap_bind_dn', e.target.value)}
                placeholder={formData._directoryType === 'ad' ? 'CN=svc-ldap,OU=Service Accounts,DC=example,DC=com' : t('sso.bindDnPlaceholder')}
              />
              <Input
                label={t('sso.bindPassword')}
                type="password"
                noAutofill
                value={formData.ldap_bind_password}
                onChange={e => handleChange('ldap_bind_password', e.target.value)}
                hasExistingValue={!!provider?.ldap_bind_password}
              />
              <Input
                label={t('sso.baseDn')}
                value={formData.ldap_base_dn}
                onChange={e => handleChange('ldap_base_dn', e.target.value)}
                placeholder={formData._directoryType === 'ad' ? 'DC=example,DC=com' : t('sso.baseDnPlaceholder')}
              />
              {provider?.id && (
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={handleTestConnection}
                  disabled={testingConnection}
                  className="gap-1.5"
                >
                  {testingConnection ? <LoadingSpinner size="xs" /> : <Plugs size={14} />}
                  {t('sso.testConnection')}
                </Button>
              )}
            </div>
          </CompactSection>

          {/* Section 2: User Search */}
          <CompactSection 
            title={t('sso.userSearchSection')} 
            icon={MagnifyingGlass} 
            collapsible 
            defaultOpen={false}
          >
            <div className="space-y-3">
              <Input
                label={t('sso.userFilter')}
                value={formData.ldap_user_filter}
                onChange={e => handleChange('ldap_user_filter', e.target.value)}
                placeholder={formData._directoryType === 'ad' ? '(sAMAccountName={username})' : t('sso.userFilterPlaceholder')}
              />
              <div className="grid grid-cols-3 gap-4">
                <Input
                  label={t('sso.usernameAttr')}
                  value={formData.ldap_username_attr}
                  onChange={e => handleChange('ldap_username_attr', e.target.value)}
                  placeholder={formData._directoryType === 'ad' ? 'sAMAccountName' : 'uid'}
                />
                <Input
                  label={t('sso.emailAttr')}
                  value={formData.ldap_email_attr}
                  onChange={e => handleChange('ldap_email_attr', e.target.value)}
                  placeholder="mail"
                />
                <Input
                  label={t('sso.fullnameAttr')}
                  value={formData.ldap_fullname_attr}
                  onChange={e => handleChange('ldap_fullname_attr', e.target.value)}
                  placeholder={formData._directoryType === 'ad' ? 'displayName' : 'cn'}
                />
              </div>
            </div>
          </CompactSection>

          {/* Section 3: Groups & Role Mapping */}
          <CompactSection 
            title={t('sso.groupsRolesSection')} 
            icon={UsersThree} 
            collapsible 
            defaultOpen={false}
          >
            <div className="space-y-3">
              <Input
                label={t('sso.groupFilter')}
                value={formData.ldap_group_filter}
                onChange={e => handleChange('ldap_group_filter', e.target.value)}
                placeholder={formData._directoryType === 'ad' ? '(objectClass=group)' : t('sso.groupFilterPlaceholder')}
              />
              <Select
                label={t('sso.groupMemberAttr')}
                value={formData.ldap_group_member_attr || 'member'}
                onChange={value => handleChange('ldap_group_member_attr', value)}
                options={[
                  { value: 'memberOf', label: t('sso.ldapGroupAttrs.memberOf') },
                  { value: 'member', label: t('sso.ldapGroupAttrs.member') },
                  { value: 'uniqueMember', label: t('sso.ldapGroupAttrs.uniqueMember') },
                ]}
              />
              <Select
                label={t('sso.defaultRole')}
                value={formData.default_role}
                onChange={value => handleChange('default_role', value)}
                options={roleOptions}
              />
              <div className="pt-1">
                <p className="text-xs font-medium text-text-secondary mb-2">{t('sso.roleMapping')}</p>
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

              {/* Test Mapping */}
              {provider?.id && (
                <div className="pt-2 border-t border-border">
                  <p className="text-xs text-text-muted mb-2">{t('sso.testMappingDesc')}</p>
                  <div className="flex gap-2">
                    <Input
                      value={testMappingUsername}
                      onChange={e => setTestMappingUsername(e.target.value)}
                      placeholder={t('sso.testMappingUserPlaceholder')}
                      className="flex-1"
                      size="sm"
                    />
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={handleTestMapping}
                      disabled={testingMapping || !testMappingUsername.trim()}
                      className="gap-1 whitespace-nowrap"
                    >
                      {testingMapping ? <LoadingSpinner size="xs" /> : <Play size={14} />}
                      {t('sso.testMappingRun')}
                    </Button>
                  </div>
                  {testMappingResult && (
                    <div className="mt-2 p-2.5 rounded-lg border border-border bg-bg-secondary text-xs space-y-1">
                      {testMappingResult.found === false ? (
                        <p className="text-status-error">{t('sso.testMappingNotFound')}</p>
                      ) : (
                        <>
                          <p><span className="text-text-secondary font-medium">DN:</span> <span className="text-text-muted font-mono">{testMappingResult.user_dn}</span></p>
                          <p>
                            <span className="text-text-secondary font-medium">{t('sso.testMappingGroups')}:</span>{' '}
                            {testMappingResult.groups?.length > 0 
                              ? testMappingResult.groups.map(g => <Badge key={g} variant="secondary" size="sm" className="mr-1">{g}</Badge>)
                              : <span className="text-text-muted italic">{t('sso.testMappingNoGroups')}</span>
                            }
                          </p>
                          <p>
                            <span className="text-text-secondary font-medium">{t('sso.testMappingResolvedRole')}:</span>{' '}
                            <Badge variant={testMappingResult.resolved_role === 'admin' ? 'error' : testMappingResult.resolved_role === 'operator' ? 'warning' : 'info'} size="sm">
                              {testMappingResult.resolved_role}
                            </Badge>
                          </p>
                        </>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </CompactSection>

          {/* Section 4: Provisioning */}
          <CompactSection 
            title={t('sso.provisioningSection')} 
            icon={UserPlus} 
            collapsible 
            defaultOpen={false}
          >
            <div className="space-y-2">
              <ToggleSwitch
                checked={formData.auto_create_users}
                onChange={(val) => handleChange('auto_create_users', val)}
                label={t('sso.autoCreateUsers')}
              />
              <ToggleSwitch
                checked={formData.auto_update_users}
                onChange={(val) => handleChange('auto_update_users', val)}
                label={t('sso.autoUpdateUsers')}
              />
              <ToggleSwitch
                checked={formData.sync_role_on_login}
                onChange={(val) => handleChange('sync_role_on_login', val)}
                label={t('sso.syncRoleOnLogin')}
                description={t('sso.syncRoleOnLoginHelp')}
              />
            </div>
          </CompactSection>
        </div>
      )}

      {/* ── OAUTH2 SECTIONS ── */}
      {isOauth2 && (
        <div className="space-y-3">
          {/* Section 1: Provider Preset */}
          <CompactSection 
            title={t('sso.oauth2Preset')} 
            icon={Lightning} 
            collapsible 
            defaultOpen
          >
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

          {/* Section 2: Connection */}
          <CompactSection 
            title={<span className="flex items-center">{t('sso.connectionSection')}{connectionBadge}</span>}
            icon={Plugs} 
            collapsible 
            defaultOpen
          >
            <div className="space-y-3">
              <Input
                label={t('common.clientId')}
                value={formData.oauth2_client_id}
                onChange={e => handleChange('oauth2_client_id', e.target.value)}
              />
              <Input
                label={t('common.clientSecret')}
                type="password"
                noAutofill
                value={formData.oauth2_client_secret}
                onChange={e => handleChange('oauth2_client_secret', e.target.value)}
                hasExistingValue={!!provider?.oauth2_client_secret}
              />
              <Input
                label={t('sso.authUrl')}
                value={formData.oauth2_auth_url}
                onChange={e => handleChange('oauth2_auth_url', e.target.value)}
                placeholder={t('sso.authUrlPlaceholder')}
              />
              <Input
                label={t('sso.tokenUrl')}
                value={formData.oauth2_token_url}
                onChange={e => handleChange('oauth2_token_url', e.target.value)}
                placeholder={t('sso.tokenUrlPlaceholder')}
              />
              <Input
                label={t('sso.userinfoUrl')}
                value={formData.oauth2_userinfo_url}
                onChange={e => handleChange('oauth2_userinfo_url', e.target.value)}
                placeholder={t('sso.userinfoUrlPlaceholder')}
              />
              <Input
                label={t('sso.scopes')}
                value={formData.oauth2_scopes}
                onChange={e => handleChange('oauth2_scopes', e.target.value)}
                placeholder={t('sso.scopesPlaceholder')}
              />
              <CopyableUrl label={t('sso.redirectUri')} value={oauthCallbackUrl} />
              <ToggleSwitch
                checked={formData.oauth2_verify_ssl}
                onChange={(val) => handleChange('oauth2_verify_ssl', val)}
                label={t('sso.verifySsl')}
                size="sm"
              />
              {!formData.oauth2_verify_ssl && (
                <p className="text-xs text-amber-500">{t('sso.sslWarning')}</p>
              )}
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
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={handleTestConnection}
                  disabled={testingConnection}
                  className="gap-1.5"
                >
                  {testingConnection ? <LoadingSpinner size="xs" /> : <Plugs size={14} />}
                  {t('sso.testConnection')}
                </Button>
              )}
            </div>
          </CompactSection>

          {/* Section 3: Attribute & Role Mapping */}
          <CompactSection 
            title={t('sso.attributeRoleMappingSection')} 
            icon={TreeStructure} 
            collapsible 
            defaultOpen={false}
          >
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

          {/* Section 4: Provisioning */}
          <CompactSection 
            title={t('sso.provisioningSection')} 
            icon={UserPlus} 
            collapsible 
            defaultOpen={false}
          >
            <div className="space-y-3">
              <Select
                label={t('sso.defaultRole')}
                value={formData.default_role}
                onChange={value => handleChange('default_role', value)}
                options={roleOptions}
              />
              <ToggleSwitch
                checked={formData.auto_create_users}
                onChange={(val) => handleChange('auto_create_users', val)}
                label={t('sso.autoCreateUsers')}
              />
              <ToggleSwitch
                checked={formData.auto_update_users}
                onChange={(val) => handleChange('auto_update_users', val)}
                label={t('sso.autoUpdateUsers')}
              />
              <ToggleSwitch
                checked={formData.sync_role_on_login}
                onChange={(val) => handleChange('sync_role_on_login', val)}
                label={t('sso.syncRoleOnLogin')}
                description={t('sso.syncRoleOnLoginHelp')}
              />
            </div>
          </CompactSection>
        </div>
      )}

      {/* ── SAML SECTIONS ── */}
      {isSaml && (
        <div className="space-y-3">
          {/* Section 1: Identity Provider (IdP) */}
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
              <HelpCard variant="info" className="text-xs">
                {t('sso.metadataUrlHelp')}
              </HelpCard>
              <Input
                label={t('sso.entityId')}
                value={formData.saml_entity_id}
                onChange={e => handleChange('saml_entity_id', e.target.value)}
                placeholder="https://idp.example.com/saml/metadata"
              />
              <Input
                label={t('sso.ssoURL')}
                value={formData.saml_sso_url}
                onChange={e => handleChange('saml_sso_url', e.target.value)}
                placeholder="https://idp.example.com/saml/sso"
              />
              <Input
                label={t('sso.sloURL')}
                value={formData.saml_slo_url}
                onChange={e => handleChange('saml_slo_url', e.target.value)}
                placeholder="https://idp.example.com/saml/slo"
              />
              <Textarea
                label={t('sso.certificate')}
                value={formData.saml_certificate}
                onChange={e => handleChange('saml_certificate', e.target.value)}
                rows={4}
                placeholder="-----BEGIN CERTIFICATE-----..."
                className="font-mono text-xs"
              />
              <ToggleSwitch
                checked={formData.saml_sign_requests}
                onChange={(val) => handleChange('saml_sign_requests', val)}
                label={t('sso.signRequests')}
              />
              <Select
                label={t('sso.spCertificate')}
                value={formData.saml_sp_cert_source}
                onChange={value => handleChange('saml_sp_cert_source', value)}
                options={availableCerts.length > 0
                  ? availableCerts.map(c => ({
                      value: c.id,
                      label: c.not_after
                        ? `${c.label} (${formatDate(c.not_after)})`
                        : c.label
                    }))
                  : [{ value: 'https', label: t('sso.httpsDefault') }]
                }
              />
              <ToggleSwitch
                checked={formData.saml_verify_ssl}
                onChange={(val) => handleChange('saml_verify_ssl', val)}
                label={t('sso.verifySsl')}
                size="sm"
              />
              {!formData.saml_verify_ssl && (
                <p className="text-xs text-amber-500">{t('sso.sslWarning')}</p>
              )}
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
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={handleTestConnection}
                  disabled={testingConnection}
                  className="gap-1.5"
                >
                  {testingConnection ? <LoadingSpinner size="xs" /> : <Plugs size={14} />}
                  {t('sso.testConnection')}
                </Button>
              )}
            </div>
          </CompactSection>

          {/* Section 2: SP Endpoints */}
          <CompactSection 
            title={t('sso.spSection')} 
            icon={Globe} 
            collapsible 
            defaultOpen={false}
          >
            <div className="space-y-3">
              <HelpCard variant="info" className="text-xs">
                {t('sso.spMetadataHelp')}
              </HelpCard>
              <CopyableUrl
                label={t('sso.spMetadataXml')}
                value={`${baseUrl}/api/v2/sso/saml/metadata`}
                description={t('sso.spMetadataXmlDesc')}
              />
              <CopyableUrl label={t('sso.spEntityId')} value={spEntityId} />
              <CopyableUrl label={t('sso.acsUrl')} value={samlAcsUrl} description={t('sso.acsUrlDesc')} />
              <CopyableUrl label={t('sso.spSloUrl')} value={samlSloUrl} />
            </div>
          </CompactSection>

          {/* Section 3: Attribute & Role Mapping */}
          <CompactSection 
            title={t('sso.attributeRoleMappingSection')} 
            icon={TreeStructure} 
            collapsible 
            defaultOpen={false}
          >
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

          {/* Section 4: Provisioning */}
          <CompactSection 
            title={t('sso.provisioningSection')} 
            icon={UserPlus} 
            collapsible 
            defaultOpen={false}
          >
            <div className="space-y-3">
              <Select
                label={t('sso.defaultRole')}
                value={formData.default_role}
                onChange={value => handleChange('default_role', value)}
                options={roleOptions}
              />
              <ToggleSwitch
                checked={formData.auto_create_users}
                onChange={(val) => handleChange('auto_create_users', val)}
                label={t('sso.autoCreateUsers')}
              />
              <ToggleSwitch
                checked={formData.auto_update_users}
                onChange={(val) => handleChange('auto_update_users', val)}
                label={t('sso.autoUpdateUsers')}
              />
              <ToggleSwitch
                checked={formData.sync_role_on_login}
                onChange={(val) => handleChange('sync_role_on_login', val)}
                label={t('sso.syncRoleOnLogin')}
                description={t('sso.syncRoleOnLoginHelp')}
              />
            </div>
          </CompactSection>
        </div>
      )}

      {/* Actions */}
      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button type="submit">
          {provider ? t('common.save') : t('common.create')}
        </Button>
      </div>
    </form>
  )
}
