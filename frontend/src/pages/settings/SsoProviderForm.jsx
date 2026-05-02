import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { CheckCircle, XCircle } from '@phosphor-icons/react'
import { Button, Badge, Input } from '../../components'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import { ssoService } from '../../services'
import { useNotification } from '../../contexts'
import SsoLdapFields from './sso/SsoLdapFields'
import SsoOAuth2Fields from './sso/SsoOAuth2Fields'
import SsoSamlFields from './sso/SsoSamlFields'

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
  const [connectionStatus, setConnectionStatus] = useState(null)
  const [testingMapping, setTestingMapping] = useState(false)
  const [testMappingUsername, setTestMappingUsername] = useState('')
  const [testMappingResult, setTestMappingResult] = useState(null)
  const [oauth2Preset, setOauth2Preset] = useState('custom')

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

  const connectionBadge = connectionStatus === 'success'
    ? <Badge variant="success" size="sm" className="ml-2"><CheckCircle size={12} weight="bold" className="mr-1" />{t('sso.testConnectionSuccess')}</Badge>
    : connectionStatus === 'error'
    ? <Badge variant="error" size="sm" className="ml-2"><XCircle size={12} weight="bold" className="mr-1" />{t('sso.testConnectionFailed')}</Badge>
    : null

  const isLdap = formData.provider_type === 'ldap'
  const isOauth2 = formData.provider_type === 'oauth2'
  const isSaml = formData.provider_type === 'saml'

  const sharedProps = { formData, handleChange, provider, testingConnection, connectionBadge, roleOptions, handleTestConnection }

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4 max-h-[75vh] overflow-y-auto">
      {/* General Settings */}
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

      {isLdap && (
        <SsoLdapFields
          {...sharedProps}
          testMappingUsername={testMappingUsername}
          setTestMappingUsername={setTestMappingUsername}
          testingMapping={testingMapping}
          testMappingResult={testMappingResult}
          handleTestMapping={handleTestMapping}
          setFormData={setFormData}
        />
      )}

      {isOauth2 && (
        <SsoOAuth2Fields
          {...sharedProps}
          oauth2Preset={oauth2Preset}
          applyOAuth2Preset={applyOAuth2Preset}
          oauthCallbackUrl={oauthCallbackUrl}
        />
      )}

      {isSaml && (
        <SsoSamlFields
          {...sharedProps}
          fetchingMetadata={fetchingMetadata}
          fetchIdpMetadata={fetchIdpMetadata}
          availableCerts={availableCerts}
          baseUrl={baseUrl}
          spEntityId={spEntityId}
          samlAcsUrl={samlAcsUrl}
          samlSloUrl={samlSloUrl}
        />
      )}

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
