/**
 * SSO Settings Section
 * Configure LDAP, OAuth2, or SAML authentication providers
 */
import { useState, useEffect } from 'react'
import { 
  Key, Shield, Plus, Trash, PencilSimple, 
  CheckCircle, XCircle, TestTube, Lightning,
  Globe, Database, ArrowsClockwise, MagnifyingGlass,
  Calendar, User
} from '@phosphor-icons/react'
import { 
  Card, Button, Badge, Modal, Input, Select, Textarea, EmptyState, HelpCard,
  DetailHeader, DetailSection, DetailGrid, DetailField, DetailContent, ConfirmModal
} from '../../components'
import * as Tabs from '@radix-ui/react-tabs'
import { useNotification } from '../../contexts/NotificationContext'
import { apiClient } from '../../services/apiClient'
import { useTranslation } from 'react-i18next'

const PROVIDER_ICONS = {
  ldap: Database,
  oauth2: Globe,
  saml: Shield,
}

export default function SSOSettingsSection() {
  const { t } = useTranslation()
  const [providers, setProviders] = useState([])
  const [selectedProvider, setSelectedProvider] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [modalMode, setModalMode] = useState('create')
  const [testing, setTesting] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(null)
  const { showSuccess, showError } = useNotification()

  useEffect(() => {
    loadProviders()
  }, [])

  const loadProviders = async () => {
    try {
      const response = await apiClient.get('/sso/providers')
      setProviders(response.data || [])
    } catch (error) {
      showError(t('sso.loadFailed'))
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = () => {
    setSelectedProvider(null)
    setModalMode('create')
    setShowModal(true)
  }

  const handleEdit = (provider) => {
    setSelectedProvider(provider)
    setModalMode('edit')
    setShowModal(true)
  }

  const handleDelete = async () => {
    if (!confirmDelete) return
    try {
      await apiClient.delete(`/sso/providers/${confirmDelete.id}`)
      showSuccess(t('sso.deleteSuccess'))
      loadProviders()
      setSelectedProvider(null)
    } catch (error) {
      showError(t('sso.deleteFailed'))
    } finally {
      setConfirmDelete(null)
    }
  }

  const handleToggle = async (provider) => {
    try {
      await apiClient.post(`/sso/providers/${provider.id}/toggle`)
      showSuccess(t('sso.toggleSuccess', { action: provider.enabled ? t('sso.disabled').toLowerCase() : t('sso.enabled').toLowerCase() }))
      loadProviders()
    } catch (error) {
      showError(t('sso.toggleFailed'))
    }
  }

  const handleTest = async (provider) => {
    setTesting(true)
    try {
      const response = await apiClient.post(`/sso/providers/${provider.id}/test`)
      if (response.data?.status === 'success') {
        showSuccess(response.data.message || t('sso.testSuccess'))
      } else {
        showError(response.message || t('sso.testFailed'))
      }
    } catch (error) {
      showError(error.message || t('sso.testFailed'))
    } finally {
      setTesting(false)
    }
  }

  const handleSave = async (formData) => {
    try {
      if (modalMode === 'create') {
        await apiClient.post('/sso/providers', formData)
        showSuccess(t('sso.createSuccess'))
      } else {
        await apiClient.put(`/sso/providers/${selectedProvider.id}`, formData)
        showSuccess(t('sso.updateSuccess'))
      }
      setShowModal(false)
      loadProviders()
    } catch (error) {
      showError(error.message || t('sso.saveFailed'))
    }
  }

  const filteredProviders = providers.filter(p => 
    p.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    p.display_name?.toLowerCase().includes(searchTerm.toLowerCase())
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="w-6 h-6 border-2 border-accent-primary/30 border-t-accent-primary rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <DetailContent>
      <DetailHeader
        icon={Key}
        title={t('sso.title')}
        subtitle={t('sso.subtitle')}
        actions={[
          { label: t('sso.addProvider'), icon: Plus, onClick: handleCreate }
        ]}
      />

      <HelpCard variant="info" title={t('sso.helpTitle')} className="mb-4">
        {t('sso.helpDescription')}
      </HelpCard>

      {/* Search */}
      {providers.length > 0 && (
        <div className="mb-4">
          <Input
            icon={MagnifyingGlass}
            placeholder={t('sso.searchProviders')}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="max-w-sm"
          />
        </div>
      )}

      {/* Provider Grid */}
      {filteredProviders.length === 0 ? (
        <EmptyState
          icon={Key}
          title={searchTerm ? t('sso.noMatches') : t('sso.noProviders')}
          description={searchTerm ? t('sso.tryDifferentSearch') : t('sso.noProvidersDescription')}
          action={!searchTerm ? { label: t('sso.addProvider'), onClick: handleCreate } : undefined}
        />
      ) : (
        <div className="grid gap-3 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
          {filteredProviders.map(provider => {
            const Icon = PROVIDER_ICONS[provider.provider_type] || Key
            return (
              <Card
                key={provider.id}
                className={`cursor-pointer transition-all ${
                  selectedProvider?.id === provider.id 
                    ? 'ring-2 ring-accent-primary bg-accent-primary/5' 
                    : 'hover:bg-bg-tertiary'
                }`}
                onClick={() => setSelectedProvider(provider)}
              >
                <div className="flex items-start gap-3">
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                    selectedProvider?.id === provider.id ? 'bg-accent-primary/20' : 'bg-bg-tertiary'
                  }`}>
                    <Icon size={20} className={
                      selectedProvider?.id === provider.id ? 'text-accent-primary' : 'text-text-tertiary'
                    } />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-text-primary truncate">
                        {provider.display_name || provider.name}
                      </span>
                      {provider.enabled ? (
                        <CheckCircle size={16} className="status-success-text shrink-0" weight="fill" />
                      ) : (
                        <XCircle size={16} className="text-text-tertiary shrink-0" />
                      )}
                    </div>
                    <p className="text-xs text-text-tertiary mt-0.5">
                      {provider.provider_type?.toUpperCase() || 'Unknown'}
                    </p>
                  </div>
                </div>
              </Card>
            )
          })}
        </div>
      )}

      {/* Selected Provider Details */}
      {selectedProvider && (
        <DetailSection title={t('sso.providerDetails')} className="mt-6">
          <ProviderDetails 
            provider={selectedProvider}
            onEdit={() => handleEdit(selectedProvider)}
            onDelete={() => setConfirmDelete(selectedProvider)}
            onToggle={() => handleToggle(selectedProvider)}
            onTest={() => handleTest(selectedProvider)}
            testing={testing}
            t={t}
          />
        </DetailSection>
      )}

      {/* Provider Modal */}
      {showModal && (
        <ProviderModal
          provider={modalMode === 'edit' ? selectedProvider : null}
          onSave={handleSave}
          onClose={() => setShowModal(false)}
        />
      )}

      {/* Confirm Delete Modal */}
      {confirmDelete && (
        <ConfirmModal
          open={true}
          onClose={() => setConfirmDelete(null)}
          onConfirm={handleDelete}
          title={t('common.confirmDelete')}
          message={t('sso.deleteConfirm', { name: confirmDelete.name })}
          confirmText={t('common.delete')}
          variant="danger"
        />
      )}
    </DetailContent>
  )
}

function ProviderDetails({ provider, onEdit, onDelete, onToggle, onTest, testing, t }) {
  const Icon = PROVIDER_ICONS[provider.provider_type] || Key
  
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-accent-primary/10 flex items-center justify-center">
            <Icon size={20} className="text-accent-primary" />
          </div>
          <div>
            <h4 className="font-medium text-text-primary">{provider.display_name || provider.name}</h4>
            <p className="text-xs text-text-secondary">{provider.provider_type?.toUpperCase()}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="secondary" onClick={onTest} disabled={testing}>
            {testing ? <ArrowsClockwise size={14} className="animate-spin" /> : <TestTube size={14} />}
            {t('sso.test')}
          </Button>
          <Button size="sm" variant="secondary" onClick={onToggle}>
            <Lightning size={14} />
            {provider.enabled ? t('sso.disable') : t('sso.enable')}
          </Button>
          <Button size="sm" variant="secondary" onClick={onEdit}>
            <PencilSimple size={14} />
          </Button>
          <Button size="sm" variant="danger" onClick={onDelete}>
            <Trash size={14} />
          </Button>
        </div>
      </div>

      <DetailGrid columns={2}>
        <DetailField label={t('sso.status')} value={
          <Badge variant={provider.enabled ? 'success' : 'secondary'}>
            {provider.enabled ? t('sso.enabled') : t('sso.disabled')}
          </Badge>
        } />
        <DetailField label={t('sso.defaultRole')} value={t(`sso.roles.${provider.default_role}`) || provider.default_role} />
        <DetailField label={t('sso.autoCreateUsers')} value={provider.auto_create_users ? t('common.yes') : t('common.no')} />
        <DetailField label={t('sso.autoUpdateUsers')} value={provider.auto_update_users ? t('common.yes') : t('common.no')} />
      </DetailGrid>

      {provider.provider_type === 'ldap' && (
        <DetailGrid columns={2}>
          <DetailField label={t('sso.ldapServer')} value={`${provider.ldap_server}:${provider.ldap_port}`} mono />
          <DetailField label="SSL/TLS" value={provider.ldap_use_ssl ? t('sso.enabled') : t('sso.disabled')} />
          <DetailField label={t('sso.baseDn')} value={provider.ldap_base_dn} mono fullWidth />
        </DetailGrid>
      )}

      {provider.provider_type === 'oauth2' && (
        <DetailGrid columns={2}>
          <DetailField label={t('sso.clientId')} value={provider.oauth2_client_id} mono />
          <DetailField label={t('sso.scopes')} value={provider.oauth2_scopes?.join(', ')} />
          <DetailField label={t('sso.authUrl')} value={provider.oauth2_auth_url} mono fullWidth />
        </DetailGrid>
      )}

      {provider.provider_type === 'saml' && (
        <DetailGrid columns={2}>
          <DetailField label={t('sso.entityId')} value={provider.saml_entity_id} mono fullWidth />
          <DetailField label={t('sso.ssoURL')} value={provider.saml_sso_url} mono fullWidth />
        </DetailGrid>
      )}
    </div>
  )
}

function ProviderModal({ provider, onSave, onClose }) {
  const { t } = useTranslation()
  const [formData, setFormData] = useState({
    name: provider?.name || '',
    display_name: provider?.display_name || '',
    provider_type: provider?.provider_type || 'ldap',
    enabled: provider?.enabled ?? false,
    default_role: provider?.default_role || 'viewer',
    auto_create_users: provider?.auto_create_users ?? true,
    auto_update_users: provider?.auto_update_users ?? true,
    // LDAP
    ldap_server: provider?.ldap_server || '',
    ldap_port: provider?.ldap_port || 389,
    ldap_use_ssl: provider?.ldap_use_ssl ?? false,
    ldap_bind_dn: provider?.ldap_bind_dn || '',
    ldap_bind_password: '',
    ldap_base_dn: provider?.ldap_base_dn || '',
    ldap_user_filter: provider?.ldap_user_filter || '(uid={username})',
    // OAuth2
    oauth2_client_id: provider?.oauth2_client_id || '',
    oauth2_client_secret: '',
    oauth2_auth_url: provider?.oauth2_auth_url || '',
    oauth2_token_url: provider?.oauth2_token_url || '',
    oauth2_userinfo_url: provider?.oauth2_userinfo_url || '',
    oauth2_scopes: provider?.oauth2_scopes?.join(' ') || 'openid profile email',
    // SAML
    saml_entity_id: provider?.saml_entity_id || '',
    saml_sso_url: provider?.saml_sso_url || '',
    saml_slo_url: provider?.saml_slo_url || '',
    saml_certificate: provider?.saml_certificate || '',
  })
  
  const [activeTab, setActiveTab] = useState('general')

  const PROVIDER_TYPES = [
    { value: 'ldap', label: t('sso.ldap'), icon: Database },
    { value: 'oauth2', label: t('sso.oauth2'), icon: Globe },
    { value: 'saml', label: t('sso.saml'), icon: Shield },
  ]

  const ROLE_OPTIONS = [
    { value: 'admin', label: t('sso.roles.admin') },
    { value: 'operator', label: t('sso.roles.operator') },
    { value: 'viewer', label: t('sso.roles.viewer') },
  ]

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    const data = { ...formData }
    if (data.provider_type === 'oauth2') {
      data.oauth2_scopes = data.oauth2_scopes.split(/\s+/).filter(Boolean)
    }
    onSave(data)
  }

  return (
    <Modal
      open={true}
      onClose={onClose}
      title={provider ? t('sso.editProvider') : t('sso.newProvider')}
      size="lg"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <Tabs.Root value={activeTab} onValueChange={setActiveTab}>
          <Tabs.List className="flex gap-1 border-b border-border mb-4">
            <Tabs.Trigger value="general" className="px-4 py-2 text-sm font-medium text-text-secondary hover:text-text-primary data-[state=active]:text-accent-primary data-[state=active]:border-b-2 data-[state=active]:border-accent-primary">{t('sso.tabs.general')}</Tabs.Trigger>
            <Tabs.Trigger value="connection" className="px-4 py-2 text-sm font-medium text-text-secondary hover:text-text-primary data-[state=active]:text-accent-primary data-[state=active]:border-b-2 data-[state=active]:border-accent-primary">{t('sso.tabs.connection')}</Tabs.Trigger>
            <Tabs.Trigger value="provisioning" className="px-4 py-2 text-sm font-medium text-text-secondary hover:text-text-primary data-[state=active]:text-accent-primary data-[state=active]:border-b-2 data-[state=active]:border-accent-primary">{t('sso.tabs.provisioning')}</Tabs.Trigger>
          </Tabs.List>

          <Tabs.Content value="general" className="space-y-4 mt-4">
            <div className="grid grid-cols-2 gap-4">
              <Input label={t('sso.providerName')} value={formData.name} onChange={e => handleChange('name', e.target.value)} required placeholder={t('sso.providerNamePlaceholder')} />
              <Input label={t('sso.displayName')} value={formData.display_name} onChange={e => handleChange('display_name', e.target.value)} placeholder={t('sso.displayNamePlaceholder')} />
            </div>
            {!provider && (
              <Select label={t('sso.providerType')} value={formData.provider_type} onChange={value => handleChange('provider_type', value)} options={PROVIDER_TYPES} />
            )}
            <label className="flex items-center gap-3 cursor-pointer p-2 rounded-lg hover:bg-bg-tertiary/50 transition-colors">
              <input type="checkbox" checked={formData.enabled} onChange={e => handleChange('enabled', e.target.checked)} className="w-4 h-4 rounded border-border bg-bg-tertiary text-accent-primary focus:ring-accent-primary/50" />
              <span className="text-sm text-text-primary">{t('sso.enableProvider')}</span>
            </label>
          </Tabs.Content>

          <Tabs.Content value="connection" className="space-y-4 mt-4">
            {formData.provider_type === 'ldap' && (
              <>
                <div className="grid grid-cols-3 gap-4">
                  <Input label={t('sso.ldapServer')} value={formData.ldap_server} onChange={e => handleChange('ldap_server', e.target.value)} placeholder="ldap.example.com" className="col-span-2" />
                  <Input label={t('sso.ldapPort')} type="number" value={formData.ldap_port} onChange={e => handleChange('ldap_port', parseInt(e.target.value))} />
                </div>
                <label className="flex items-center gap-3 cursor-pointer p-2 rounded-lg hover:bg-bg-tertiary/50 transition-colors">
                  <input type="checkbox" checked={formData.ldap_use_ssl} onChange={e => handleChange('ldap_use_ssl', e.target.checked)} className="w-4 h-4 rounded border-border bg-bg-tertiary text-accent-primary focus:ring-accent-primary/50" />
                  <span className="text-sm text-text-primary">{t('sso.ldapUseSsl')}</span>
                </label>
                <Input label={t('sso.bindDn')} value={formData.ldap_bind_dn} onChange={e => handleChange('ldap_bind_dn', e.target.value)} placeholder={t('sso.bindDnPlaceholder')} />
                <Input label={t('sso.bindPassword')} type="password" value={formData.ldap_bind_password} onChange={e => handleChange('ldap_bind_password', e.target.value)} placeholder={provider ? t('sso.keepExisting') : ''} />
                <Input label={t('sso.baseDn')} value={formData.ldap_base_dn} onChange={e => handleChange('ldap_base_dn', e.target.value)} placeholder={t('sso.baseDnPlaceholder')} />
                <Input label={t('sso.userFilter')} value={formData.ldap_user_filter} onChange={e => handleChange('ldap_user_filter', e.target.value)} placeholder={t('sso.userFilterPlaceholder')} />
              </>
            )}
            {formData.provider_type === 'oauth2' && (
              <>
                <Input label={t('sso.clientId')} value={formData.oauth2_client_id} onChange={e => handleChange('oauth2_client_id', e.target.value)} />
                <Input label={t('sso.clientSecret')} type="password" value={formData.oauth2_client_secret} onChange={e => handleChange('oauth2_client_secret', e.target.value)} placeholder={provider ? t('sso.keepExisting') : ''} />
                <Input label={t('sso.authUrl')} value={formData.oauth2_auth_url} onChange={e => handleChange('oauth2_auth_url', e.target.value)} placeholder={t('sso.authUrlPlaceholder')} />
                <Input label={t('sso.tokenUrl')} value={formData.oauth2_token_url} onChange={e => handleChange('oauth2_token_url', e.target.value)} placeholder={t('sso.tokenUrlPlaceholder')} />
                <Input label={t('sso.scopes')} value={formData.oauth2_scopes} onChange={e => handleChange('oauth2_scopes', e.target.value)} placeholder={t('sso.scopesPlaceholder')} />
              </>
            )}
            {formData.provider_type === 'saml' && (
              <>
                <Input label={t('sso.entityId')} value={formData.saml_entity_id} onChange={e => handleChange('saml_entity_id', e.target.value)} placeholder="https://idp.example.com/saml/metadata" />
                <Input label={t('sso.ssoURL')} value={formData.saml_sso_url} onChange={e => handleChange('saml_sso_url', e.target.value)} placeholder="https://idp.example.com/saml/sso" />
                <Input label={t('sso.sloURL')} value={formData.saml_slo_url} onChange={e => handleChange('saml_slo_url', e.target.value)} placeholder="https://idp.example.com/saml/slo" />
                <Textarea label={t('sso.certificate')} value={formData.saml_certificate} onChange={e => handleChange('saml_certificate', e.target.value)} rows={6} placeholder="-----BEGIN CERTIFICATE-----..." className="font-mono text-xs" />
              </>
            )}
          </Tabs.Content>

          <Tabs.Content value="provisioning" className="space-y-4 mt-4">
            <Select label={t('sso.defaultRole')} value={formData.default_role} onChange={value => handleChange('default_role', value)} options={ROLE_OPTIONS} />
            <div className="space-y-2">
              <label className="flex items-center gap-3 cursor-pointer p-2 rounded-lg hover:bg-bg-tertiary/50 transition-colors">
                <input type="checkbox" checked={formData.auto_create_users} onChange={e => handleChange('auto_create_users', e.target.checked)} className="w-4 h-4 rounded border-border bg-bg-tertiary text-accent-primary focus:ring-accent-primary/50" />
                <span className="text-sm text-text-primary">{t('sso.autoCreateUsers')}</span>
              </label>
              <label className="flex items-center gap-3 cursor-pointer p-2 rounded-lg hover:bg-bg-tertiary/50 transition-colors">
                <input type="checkbox" checked={formData.auto_update_users} onChange={e => handleChange('auto_update_users', e.target.checked)} className="w-4 h-4 rounded border-border bg-bg-tertiary text-accent-primary focus:ring-accent-primary/50" />
                <span className="text-sm text-text-primary">{t('sso.autoUpdateUsers')}</span>
              </label>
            </div>
          </Tabs.Content>
        </Tabs.Root>

        <div className="flex justify-end gap-2 pt-4 border-t border-border">
          <Button type="button" variant="secondary" onClick={onClose}>{t('sso.cancel')}</Button>
          <Button type="submit">{provider ? t('sso.update') : t('sso.create')} Provider</Button>
        </div>
      </form>
    </Modal>
  )
}
