/**
 * SSO Settings Section - Pro Feature
 * Embedded in Settings page when Pro module is present
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
  DetailHeader, DetailSection, DetailGrid, DetailField, DetailContent
} from '../../components'
import * as Tabs from '@radix-ui/react-tabs'
import { useNotification } from '../../contexts/NotificationContext'
import { apiClient } from '../../services/apiClient'

const PROVIDER_TYPES = [
  { value: 'ldap', label: 'LDAP / Active Directory', icon: Database },
  { value: 'oauth2', label: 'OAuth2 / OIDC', icon: Globe },
  { value: 'saml', label: 'SAML 2.0', icon: Shield },
]

const PROVIDER_ICONS = {
  ldap: Database,
  oauth2: Globe,
  saml: Shield,
}

export default function SSOSettingsSection() {
  const [providers, setProviders] = useState([])
  const [selectedProvider, setSelectedProvider] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [modalMode, setModalMode] = useState('create')
  const [testing, setTesting] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const { showSuccess, showError } = useNotification()

  useEffect(() => {
    loadProviders()
  }, [])

  const loadProviders = async () => {
    try {
      const response = await apiClient.get('/sso/providers')
      setProviders(response.data || [])
    } catch (error) {
      showError('Failed to load SSO providers')
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

  const handleDelete = async (provider) => {
    if (!confirm(`Delete SSO provider "${provider.name}"?`)) return
    try {
      await apiClient.delete(`/sso/providers/${provider.id}`)
      showSuccess('Provider deleted')
      loadProviders()
      setSelectedProvider(null)
    } catch (error) {
      showError('Failed to delete provider')
    }
  }

  const handleToggle = async (provider) => {
    try {
      await apiClient.post(`/sso/providers/${provider.id}/toggle`)
      showSuccess(`Provider ${provider.enabled ? 'disabled' : 'enabled'}`)
      loadProviders()
    } catch (error) {
      showError('Failed to toggle provider')
    }
  }

  const handleTest = async (provider) => {
    setTesting(true)
    try {
      const response = await apiClient.post(`/sso/providers/${provider.id}/test`)
      if (response.data?.status === 'success') {
        showSuccess(response.data.message || 'Connection successful')
      } else {
        showError(response.message || 'Test failed')
      }
    } catch (error) {
      showError(error.message || 'Connection test failed')
    } finally {
      setTesting(false)
    }
  }

  const handleSave = async (formData) => {
    try {
      if (modalMode === 'create') {
        await apiClient.post('/sso/providers', formData)
        showSuccess('Provider created')
      } else {
        await apiClient.put(`/sso/providers/${selectedProvider.id}`, formData)
        showSuccess('Provider updated')
      }
      setShowModal(false)
      loadProviders()
    } catch (error) {
      showError(error.message || 'Failed to save provider')
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
        title="Single Sign-On"
        subtitle="Configure LDAP, OAuth2, or SAML providers for centralized authentication"
        badge={<Badge variant="info">Pro</Badge>}
        actions={[
          { label: 'Add Provider', icon: Plus, onClick: handleCreate }
        ]}
      />

      <HelpCard variant="info" title="SSO Providers" className="mb-4">
        Connect UCM to your identity provider for seamless authentication. 
        Users can login with their corporate credentials.
      </HelpCard>

      {/* Search */}
      {providers.length > 0 && (
        <div className="mb-4">
          <div className="relative max-w-sm">
            <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary" />
            <input
              type="text"
              placeholder="Search providers..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-3 py-2 text-sm bg-bg-tertiary border border-border rounded-lg text-text-primary placeholder:text-text-tertiary focus:outline-none focus:ring-1 focus:ring-accent-primary"
            />
          </div>
        </div>
      )}

      {/* Provider Grid */}
      {filteredProviders.length === 0 ? (
        <EmptyState
          icon={Key}
          title={searchTerm ? "No matches" : "No SSO providers"}
          description={searchTerm ? "Try a different search" : "Add LDAP, OAuth2, or SAML providers"}
          action={!searchTerm ? { label: 'Add Provider', onClick: handleCreate } : undefined}
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
        <DetailSection title="Provider Details" className="mt-6">
          <ProviderDetails 
            provider={selectedProvider}
            onEdit={() => handleEdit(selectedProvider)}
            onDelete={() => handleDelete(selectedProvider)}
            onToggle={() => handleToggle(selectedProvider)}
            onTest={() => handleTest(selectedProvider)}
            testing={testing}
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
    </DetailContent>
  )
}

function ProviderDetails({ provider, onEdit, onDelete, onToggle, onTest, testing }) {
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
            Test
          </Button>
          <Button size="sm" variant="secondary" onClick={onToggle}>
            <Lightning size={14} />
            {provider.enabled ? 'Disable' : 'Enable'}
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
        <DetailField label="Status" value={
          <Badge variant={provider.enabled ? 'success' : 'secondary'}>
            {provider.enabled ? 'Enabled' : 'Disabled'}
          </Badge>
        } />
        <DetailField label="Default Role" value={provider.default_role || 'viewer'} />
        <DetailField label="Auto-create Users" value={provider.auto_create_users ? 'Yes' : 'No'} />
        <DetailField label="Auto-update Users" value={provider.auto_update_users ? 'Yes' : 'No'} />
      </DetailGrid>

      {provider.provider_type === 'ldap' && (
        <DetailGrid columns={2}>
          <DetailField label="Server" value={`${provider.ldap_server}:${provider.ldap_port}`} mono />
          <DetailField label="SSL/TLS" value={provider.ldap_use_ssl ? 'Enabled' : 'Disabled'} />
          <DetailField label="Base DN" value={provider.ldap_base_dn} mono fullWidth />
        </DetailGrid>
      )}

      {provider.provider_type === 'oauth2' && (
        <DetailGrid columns={2}>
          <DetailField label="Client ID" value={provider.oauth2_client_id} mono />
          <DetailField label="Scopes" value={provider.oauth2_scopes?.join(', ')} />
          <DetailField label="Auth URL" value={provider.oauth2_auth_url} mono fullWidth />
        </DetailGrid>
      )}

      {provider.provider_type === 'saml' && (
        <DetailGrid columns={2}>
          <DetailField label="Entity ID" value={provider.saml_entity_id} mono fullWidth />
          <DetailField label="SSO URL" value={provider.saml_sso_url} mono fullWidth />
        </DetailGrid>
      )}
    </div>
  )
}

function ProviderModal({ provider, onSave, onClose }) {
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
      title={provider ? 'Edit SSO Provider' : 'New SSO Provider'}
      size="lg"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <Tabs.Root value={activeTab} onValueChange={setActiveTab}>
          <Tabs.List className="flex gap-1 border-b border-border mb-4">
            <Tabs.Trigger value="general" className="px-4 py-2 text-sm font-medium text-text-secondary hover:text-text-primary data-[state=active]:text-accent-primary data-[state=active]:border-b-2 data-[state=active]:border-accent-primary">General</Tabs.Trigger>
            <Tabs.Trigger value="connection" className="px-4 py-2 text-sm font-medium text-text-secondary hover:text-text-primary data-[state=active]:text-accent-primary data-[state=active]:border-b-2 data-[state=active]:border-accent-primary">Connection</Tabs.Trigger>
            <Tabs.Trigger value="provisioning" className="px-4 py-2 text-sm font-medium text-text-secondary hover:text-text-primary data-[state=active]:text-accent-primary data-[state=active]:border-b-2 data-[state=active]:border-accent-primary">Provisioning</Tabs.Trigger>
          </Tabs.List>

          <Tabs.Content value="general" className="space-y-4 mt-4">
            <div className="grid grid-cols-2 gap-4">
              <Input label="Provider Name" value={formData.name} onChange={e => handleChange('name', e.target.value)} required placeholder="e.g., corporate-ldap" />
              <Input label="Display Name" value={formData.display_name} onChange={e => handleChange('display_name', e.target.value)} placeholder="e.g., Corporate Directory" />
            </div>
            {!provider && (
              <Select label="Provider Type" value={formData.provider_type} onChange={value => handleChange('provider_type', value)} options={PROVIDER_TYPES} />
            )}
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={formData.enabled} onChange={e => handleChange('enabled', e.target.checked)} className="rounded" />
              Enable provider
            </label>
          </Tabs.Content>

          <Tabs.Content value="connection" className="space-y-4 mt-4">
            {formData.provider_type === 'ldap' && (
              <>
                <div className="grid grid-cols-3 gap-4">
                  <Input label="LDAP Server" value={formData.ldap_server} onChange={e => handleChange('ldap_server', e.target.value)} placeholder="ldap.example.com" className="col-span-2" />
                  <Input label="Port" type="number" value={formData.ldap_port} onChange={e => handleChange('ldap_port', parseInt(e.target.value))} />
                </div>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={formData.ldap_use_ssl} onChange={e => handleChange('ldap_use_ssl', e.target.checked)} className="rounded" />
                  Use SSL/TLS
                </label>
                <Input label="Bind DN" value={formData.ldap_bind_dn} onChange={e => handleChange('ldap_bind_dn', e.target.value)} placeholder="cn=admin,dc=example,dc=com" />
                <Input label="Bind Password" type="password" value={formData.ldap_bind_password} onChange={e => handleChange('ldap_bind_password', e.target.value)} placeholder={provider ? '••••••• (leave empty to keep)' : ''} />
                <Input label="Base DN" value={formData.ldap_base_dn} onChange={e => handleChange('ldap_base_dn', e.target.value)} placeholder="dc=example,dc=com" />
                <Input label="User Filter" value={formData.ldap_user_filter} onChange={e => handleChange('ldap_user_filter', e.target.value)} placeholder="(uid={username})" />
              </>
            )}
            {formData.provider_type === 'oauth2' && (
              <>
                <Input label="Client ID" value={formData.oauth2_client_id} onChange={e => handleChange('oauth2_client_id', e.target.value)} />
                <Input label="Client Secret" type="password" value={formData.oauth2_client_secret} onChange={e => handleChange('oauth2_client_secret', e.target.value)} placeholder={provider ? '••••••• (leave empty to keep)' : ''} />
                <Input label="Authorization URL" value={formData.oauth2_auth_url} onChange={e => handleChange('oauth2_auth_url', e.target.value)} placeholder="https://provider.com/oauth/authorize" />
                <Input label="Token URL" value={formData.oauth2_token_url} onChange={e => handleChange('oauth2_token_url', e.target.value)} placeholder="https://provider.com/oauth/token" />
                <Input label="Scopes" value={formData.oauth2_scopes} onChange={e => handleChange('oauth2_scopes', e.target.value)} placeholder="openid profile email" />
              </>
            )}
            {formData.provider_type === 'saml' && (
              <>
                <Input label="Entity ID" value={formData.saml_entity_id} onChange={e => handleChange('saml_entity_id', e.target.value)} placeholder="https://idp.example.com/saml/metadata" />
                <Input label="SSO URL" value={formData.saml_sso_url} onChange={e => handleChange('saml_sso_url', e.target.value)} placeholder="https://idp.example.com/saml/sso" />
                <Input label="SLO URL (optional)" value={formData.saml_slo_url} onChange={e => handleChange('saml_slo_url', e.target.value)} placeholder="https://idp.example.com/saml/slo" />
                <Textarea label="IdP Certificate (PEM)" value={formData.saml_certificate} onChange={e => handleChange('saml_certificate', e.target.value)} rows={6} placeholder="-----BEGIN CERTIFICATE-----..." className="font-mono text-xs" />
              </>
            )}
          </Tabs.Content>

          <Tabs.Content value="provisioning" className="space-y-4 mt-4">
            <Select label="Default Role" value={formData.default_role} onChange={value => handleChange('default_role', value)} options={[
              { value: 'admin', label: 'Admin' },
              { value: 'operator', label: 'Operator' },
              { value: 'viewer', label: 'Viewer' },
            ]} />
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={formData.auto_create_users} onChange={e => handleChange('auto_create_users', e.target.checked)} className="rounded" />
                Auto-create users on first login
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={formData.auto_update_users} onChange={e => handleChange('auto_update_users', e.target.checked)} className="rounded" />
                Update user info on each login
              </label>
            </div>
          </Tabs.Content>
        </Tabs.Root>

        <div className="flex justify-end gap-2 pt-4 border-t border-border">
          <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit">{provider ? 'Update' : 'Create'} Provider</Button>
        </div>
      </form>
    </Modal>
  )
}
