/**
 * SSO Page - UCM Pro
 * SAML, OAuth2, LDAP provider management
 */
import { useState, useEffect } from 'react'
import { 
  Key, Shield, Users, Plus, Trash, PencilSimple, 
  CheckCircle, XCircle, TestTube, Lightning,
  Globe, Lock, Database, ArrowsClockwise, MagnifyingGlass,
  Calendar, User
} from '@phosphor-icons/react'
import { 
  PageLayout, FocusItem, Card, Button, Badge, 
  Modal, Input, Select, Textarea, EmptyState, HelpCard,
  CompactHeader, CompactSection, CompactGrid, CompactField, CompactStats
} from '../../components'
import * as Tabs from '@radix-ui/react-tabs'
import { useNotification } from '../../contexts/NotificationContext'
import { apiClient } from '../../services/apiClient'
import { ERRORS, SUCCESS, CONFIRM } from '../../lib/messages'

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

export default function SSOPage() {
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
      if (response.data?.length > 0 && !selectedProvider) {
        setSelectedProvider(response.data[0])
      }
    } catch (error) {
      showError(ERRORS.LOAD_FAILED.SSO_PROVIDERS)
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
    if (!confirm(CONFIRM.SSO.DELETE_PROVIDER.replace('{name}', provider.name))) return
    
    try {
      await apiClient.delete(`/sso/providers/${provider.id}`)
      showSuccess(SUCCESS.DELETE.PROVIDER)
      loadProviders()
      setSelectedProvider(null)
    } catch (error) {
      showError(error.message || ERRORS.DELETE_FAILED.PROVIDER)
    }
  }

  const handleToggle = async (provider) => {
    try {
      await apiClient.post(`/sso/providers/${provider.id}/toggle`)
      showSuccess(SUCCESS.SSO.TOGGLED(provider.enabled))
      loadProviders()
    } catch (error) {
      showError(error.message || ERRORS.SSO.TOGGLE_FAILED)
    }
  }

  const handleTest = async (provider) => {
    setTesting(true)
    try {
      const response = await apiClient.post(`/sso/providers/${provider.id}/test`)
      if (response.data?.status === 'success') {
        showSuccess(response.data.message || SUCCESS.SSO.CONNECTION_OK)
      } else {
        showError(response.message || ERRORS.SSO.TEST_FAILED)
      }
    } catch (error) {
      showError(error.message || ERRORS.SSO.TEST_FAILED)
    } finally {
      setTesting(false)
    }
  }

  const handleSave = async (formData) => {
    try {
      if (modalMode === 'create') {
        await apiClient.post('/sso/providers', formData)
        showSuccess(SUCCESS.CREATE.PROVIDER)
      } else {
        await apiClient.put(`/sso/providers/${selectedProvider.id}`, formData)
        showSuccess(SUCCESS.UPDATE.PROVIDER)
      }
      setShowModal(false)
      loadProviders()
    } catch (error) {
      showError(error.message || ERRORS.CREATE_FAILED.PROVIDER)
    }
  }

  const filteredProviders = providers.filter(p => 
    p.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    p.display_name?.toLowerCase().includes(searchTerm.toLowerCase())
  )

  // Provider list content (main area)
  const providerListContent = (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <Input
          placeholder="Search providers..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          icon={<MagnifyingGlass size={14} />}
          className="w-64"
        />
        <Button onClick={handleCreate}>
          <Plus size={14} />
          New Provider
        </Button>
      </div>
      
      {loading ? (
        <div className="p-8 text-center text-text-secondary">Loading...</div>
      ) : filteredProviders.length === 0 ? (
        <EmptyState
          icon={Key}
          title={searchTerm ? "No matches" : "No SSO providers"}
          description={searchTerm ? "Try a different search" : "Add LDAP, OAuth2, or SAML providers"}
          action={!searchTerm ? {
            label: 'Add Provider',
            onClick: handleCreate
          } : undefined}
        />
      ) : (
        <div className="grid gap-3 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
          {filteredProviders.map(provider => {
            const Icon = PROVIDER_ICONS[provider.provider_type] || Key
            const isSelected = selectedProvider?.id === provider.id
            const typeColors = {
              ldap: 'bg-status-orange/15 text-status-orange',
              oauth2: 'bg-status-cyan/15 text-status-cyan',
              saml: 'bg-status-purple/15 text-status-purple'
            }
            return (
              <Card
                key={provider.id}
                className={`cursor-pointer transition-all ${
                  isSelected 
                    ? 'ring-2 ring-accent-primary bg-accent-primary/5' 
                    : 'hover:bg-bg-tertiary'
                }`}
                onClick={() => setSelectedProvider(provider)}
              >
                <div className="flex items-start gap-3">
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                    isSelected ? 'bg-accent-primary/20' : typeColors[provider.provider_type] || 'bg-bg-tertiary'
                  }`}>
                    <Icon size={20} weight="duotone" className={
                      isSelected ? 'text-accent-primary' : ''
                    } />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-text-primary truncate">
                        {provider.display_name || provider.name}
                      </span>
                      <Badge 
                        variant={provider.enabled ? 'success' : 'secondary'} 
                        size="sm" 
                        dot 
                        pulse={provider.enabled}
                      >
                        {provider.enabled ? 'Active' : 'Off'}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <Badge 
                        variant={provider.provider_type === 'ldap' ? 'orange' : provider.provider_type === 'oauth2' ? 'cyan' : 'purple'} 
                        size="sm"
                      >
                        {provider.provider_type?.toUpperCase() || 'Unknown'}
                      </Badge>
                    </div>
                  </div>
                </div>
              </Card>
            )
          })}
        </div>
      )}
      
      <div className="mt-4 text-xs text-text-tertiary">
        {providers.length} provider{providers.length !== 1 ? 's' : ''}
      </div>
    </div>
  )

  // Provider details content (focus panel - right side)
  const providerDetailsContent = selectedProvider ? (
    <ProviderDetails 
      provider={selectedProvider}
      onEdit={() => handleEdit(selectedProvider)}
      onDelete={() => handleDelete(selectedProvider)}
      onToggle={() => handleToggle(selectedProvider)}
      onTest={() => handleTest(selectedProvider)}
      testing={testing}
    />
  ) : (
    <div className="flex items-center justify-center h-full p-4 text-text-secondary">
      <div className="text-center">
        <Shield size={40} className="mx-auto mb-3 text-text-tertiary" />
        <p className="text-sm">Select a provider to view details</p>
      </div>
    </div>
  )

  return (
    <>
      <PageLayout
        title="SSO Providers"
        focusTitle="Provider Details"
        focusContent={providerDetailsContent}
        focusCollapsible={true}
        focusDefaultOpen={true}
      >
        {providerListContent}
      </PageLayout>

      {showModal && (
        <ProviderModal
          provider={modalMode === 'edit' ? selectedProvider : null}
          onSave={handleSave}
          onClose={() => setShowModal(false)}
        />
      )}
    </>
  )
}

function ProviderDetails({ provider, onEdit, onDelete, onToggle, onTest, testing }) {
  const Icon = PROVIDER_ICONS[provider.provider_type] || Key
  
  const headerActions = [
    {
      label: testing ? 'Testing...' : 'Test',
      icon: testing ? ArrowsClockwise : TestTube,
      onClick: onTest,
      disabled: testing,
      variant: 'secondary'
    },
    {
      label: provider.enabled ? 'Disable' : 'Enable',
      icon: Lightning,
      onClick: onToggle,
      variant: 'secondary'
    },
    {
      label: 'Configure',
      icon: PencilSimple,
      onClick: onEdit,
      variant: 'secondary'
    },
    {
      label: 'Delete',
      icon: Trash,
      onClick: onDelete,
      variant: 'danger'
    }
  ]
  
  return (
    <div className="p-3 space-y-3">
      <HelpCard variant="info" title="Single Sign-On" compact className="mb-3">
        Configure {provider.provider_type?.toUpperCase()} for centralized authentication and user provisioning.
      </HelpCard>

      <CompactHeader
        icon={Icon}
        iconClass={provider.enabled ? "bg-status-success/20" : "bg-bg-tertiary"}
        title={provider.display_name || provider.name}
        subtitle={`${provider.provider_type?.toUpperCase() || 'Unknown'} Provider`}
        badge={
          <Badge variant={provider.enabled ? 'success' : 'secondary'} size="sm">
            {provider.enabled ? 'Enabled' : 'Disabled'}
          </Badge>
        }
      />

      <CompactStats stats={[
        { icon: Calendar, value: provider.created_at ? new Date(provider.created_at).toLocaleDateString() : '—' },
        ...(provider.last_used_at ? [{ icon: User, value: new Date(provider.last_used_at).toLocaleDateString() }] : [])
      ]} />

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        <Button 
          size="sm" 
          variant="secondary" 
          onClick={onTest}
          disabled={testing}
        >
          {testing ? <ArrowsClockwise size={14} className="animate-spin" /> : <TestTube size={14} />}
          {testing ? 'Testing...' : 'Test'}
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

      {/* Configuration Details */}
      <CompactSection title="Configuration">
        {provider.provider_type === 'ldap' && (
          <CompactGrid>
            <CompactField 
              label="Server" 
              value={`${provider.ldap_server}:${provider.ldap_port}`} 
              mono 
              copyable 
            />
            <CompactField 
              label="SSL/TLS" 
              value={provider.ldap_use_ssl ? 'Enabled' : 'Disabled'} 
            />
            <CompactField 
              label="Base DN" 
              value={provider.ldap_base_dn} 
              mono 
              copyable 
            />
            <CompactField 
              label="User Filter" 
              value={provider.ldap_user_filter} 
              mono 
            />
          </CompactGrid>
        )}
        
        {provider.provider_type === 'oauth2' && (
          <CompactGrid>
            <CompactField 
              label="Client ID" 
              value={provider.oauth2_client_id} 
              mono 
              copyable 
            />
            <CompactField 
              label="Scopes" 
              value={provider.oauth2_scopes?.join(', ')} 
            />
            <CompactField 
              label="Authorization URL" 
              value={provider.oauth2_auth_url} 
              mono 
              copyable 
            />
            <CompactField 
              label="Token URL" 
              value={provider.oauth2_token_url} 
              mono 
              copyable 
            />
          </CompactGrid>
        )}
        
        {provider.provider_type === 'saml' && (
          <CompactGrid>
            <CompactField 
              label="Entity ID" 
              value={provider.saml_entity_id} 
              mono 
              copyable 
            />
            <CompactField 
              label="SSO URL" 
              value={provider.saml_sso_url} 
              mono 
              copyable 
            />
            <CompactField 
              label="SLO URL" 
              value={provider.saml_slo_url || '—'} 
              mono 
            />
            <CompactField 
              label="Certificate" 
              value={provider.saml_certificate ? '✓ Configured' : '✗ Missing'} 
            />
          </CompactGrid>
        )}
      </CompactSection>

      {/* User Provisioning */}
      <CompactSection title="User Provisioning">
        <CompactGrid cols={3}>
          <CompactField 
            label="Auto-create" 
            value={provider.auto_create_users ? 'Yes' : 'No'} 
          />
          <CompactField 
            label="Auto-update" 
            value={provider.auto_update_users ? 'Yes' : 'No'} 
          />
          <CompactField 
            label="Default role" 
            value={provider.default_role || 'viewer'} 
          />
        </CompactGrid>
      </CompactSection>

      {/* Role Mapping */}
      {provider.role_mapping && Object.keys(provider.role_mapping).length > 0 && (
        <CompactSection title="Role Mapping" collapsible>
          <div className="space-y-2">
            {Object.entries(provider.role_mapping).map(([ssoGroup, ucmRole]) => (
              <div key={ssoGroup} className="flex items-center justify-between text-xs p-2 rounded bg-bg-tertiary/50 border border-border">
                <span className="text-text-secondary font-mono">{ssoGroup}</span>
                <span className="text-text-tertiary">→</span>
                <Badge variant="secondary" size="sm">{ucmRole}</Badge>
              </div>
            ))}
          </div>
        </CompactSection>
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
    
    // Convert scopes string to array for OAuth2
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
      <form onSubmit={handleSubmit} className="p-4 space-y-4">
        <Tabs.Root value={activeTab} onValueChange={setActiveTab}>
          <Tabs.List className="flex gap-1 border-b border-border mb-4">
            <Tabs.Trigger value="general" className="px-4 py-2 text-sm font-medium text-text-secondary hover:text-text-primary data-[state=active]:text-accent-primary data-[state=active]:border-b-2 data-[state=active]:border-accent-primary">General</Tabs.Trigger>
            <Tabs.Trigger value="connection" className="px-4 py-2 text-sm font-medium text-text-secondary hover:text-text-primary data-[state=active]:text-accent-primary data-[state=active]:border-b-2 data-[state=active]:border-accent-primary">Connection</Tabs.Trigger>
            <Tabs.Trigger value="provisioning" className="px-4 py-2 text-sm font-medium text-text-secondary hover:text-text-primary data-[state=active]:text-accent-primary data-[state=active]:border-b-2 data-[state=active]:border-accent-primary">Provisioning</Tabs.Trigger>
          </Tabs.List>

          <Tabs.Content value="general" className="space-y-4 mt-4">
            <div className="grid grid-cols-2 gap-4">
              <Input
                label="Provider Name"
                value={formData.name}
                onChange={e => handleChange('name', e.target.value)}
                required
                placeholder="e.g., corporate-ldap"
              />
              <Input
                label="Display Name"
                value={formData.display_name}
                onChange={e => handleChange('display_name', e.target.value)}
                placeholder="e.g., Corporate Directory"
              />
            </div>
            
            {!provider && (
              <Select
                label="Provider Type"
                value={formData.provider_type}
                onChange={value => handleChange('provider_type', value)}
                options={PROVIDER_TYPES}
              />
            )}
            
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={formData.enabled}
                  onChange={e => handleChange('enabled', e.target.checked)}
                  className="rounded"
                />
                Enable provider
              </label>
            </div>
          </Tabs.Content>

          <Tabs.Content value="connection" className="space-y-4 mt-4">
            {formData.provider_type === 'ldap' && (
              <>
                <div className="grid grid-cols-3 gap-4">
                  <Input
                    label="LDAP Server"
                    value={formData.ldap_server}
                    onChange={e => handleChange('ldap_server', e.target.value)}
                    placeholder="ldap.example.com"
                    className="col-span-2"
                  />
                  <Input
                    label="Port"
                    type="number"
                    value={formData.ldap_port}
                    onChange={e => handleChange('ldap_port', parseInt(e.target.value))}
                  />
                </div>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={formData.ldap_use_ssl}
                    onChange={e => handleChange('ldap_use_ssl', e.target.checked)}
                    className="rounded"
                  />
                  Use SSL/TLS
                </label>
                <Input
                  label="Bind DN"
                  value={formData.ldap_bind_dn}
                  onChange={e => handleChange('ldap_bind_dn', e.target.value)}
                  placeholder="cn=admin,dc=example,dc=com"
                />
                <Input
                  label="Bind Password"
                  type="password"
                  value={formData.ldap_bind_password}
                  onChange={e => handleChange('ldap_bind_password', e.target.value)}
                  placeholder={provider ? '••••••• (leave empty to keep)' : ''}
                />
                <Input
                  label="Base DN"
                  value={formData.ldap_base_dn}
                  onChange={e => handleChange('ldap_base_dn', e.target.value)}
                  placeholder="dc=example,dc=com"
                />
                <Input
                  label="User Filter"
                  value={formData.ldap_user_filter}
                  onChange={e => handleChange('ldap_user_filter', e.target.value)}
                  placeholder="(uid={username})"
                />
              </>
            )}

            {formData.provider_type === 'oauth2' && (
              <>
                <Input
                  label="Client ID"
                  value={formData.oauth2_client_id}
                  onChange={e => handleChange('oauth2_client_id', e.target.value)}
                />
                <Input
                  label="Client Secret"
                  type="password"
                  value={formData.oauth2_client_secret}
                  onChange={e => handleChange('oauth2_client_secret', e.target.value)}
                  placeholder={provider ? '••••••• (leave empty to keep)' : ''}
                />
                <Input
                  label="Authorization URL"
                  value={formData.oauth2_auth_url}
                  onChange={e => handleChange('oauth2_auth_url', e.target.value)}
                  placeholder="https://provider.com/oauth/authorize"
                />
                <Input
                  label="Token URL"
                  value={formData.oauth2_token_url}
                  onChange={e => handleChange('oauth2_token_url', e.target.value)}
                  placeholder="https://provider.com/oauth/token"
                />
                <Input
                  label="User Info URL"
                  value={formData.oauth2_userinfo_url}
                  onChange={e => handleChange('oauth2_userinfo_url', e.target.value)}
                  placeholder="https://provider.com/oauth/userinfo"
                />
                <Input
                  label="Scopes"
                  value={formData.oauth2_scopes}
                  onChange={e => handleChange('oauth2_scopes', e.target.value)}
                  placeholder="openid profile email"
                />
              </>
            )}

            {formData.provider_type === 'saml' && (
              <>
                <Input
                  label="Entity ID"
                  value={formData.saml_entity_id}
                  onChange={e => handleChange('saml_entity_id', e.target.value)}
                  placeholder="https://idp.example.com/saml/metadata"
                />
                <Input
                  label="SSO URL"
                  value={formData.saml_sso_url}
                  onChange={e => handleChange('saml_sso_url', e.target.value)}
                  placeholder="https://idp.example.com/saml/sso"
                />
                <Input
                  label="SLO URL (optional)"
                  value={formData.saml_slo_url}
                  onChange={e => handleChange('saml_slo_url', e.target.value)}
                  placeholder="https://idp.example.com/saml/slo"
                />
                <Textarea
                  label="IdP Certificate (PEM)"
                  value={formData.saml_certificate}
                  onChange={e => handleChange('saml_certificate', e.target.value)}
                  rows={6}
                  placeholder="-----BEGIN CERTIFICATE-----..."
                  className="font-mono text-xs"
                />
              </>
            )}
          </Tabs.Content>

          <Tabs.Content value="provisioning" className="space-y-4 mt-4">
            <Select
              label="Default Role"
              value={formData.default_role}
              onChange={value => handleChange('default_role', value)}
              options={[
                { value: 'admin', label: 'Admin' },
                { value: 'operator', label: 'Operator' },
                { value: 'viewer', label: 'Viewer' },
              ]}
            />
            
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={formData.auto_create_users}
                  onChange={e => handleChange('auto_create_users', e.target.checked)}
                  className="rounded"
                />
                Auto-create users on first login
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={formData.auto_update_users}
                  onChange={e => handleChange('auto_update_users', e.target.checked)}
                  className="rounded"
                />
                Update user info on each login
              </label>
            </div>
          </Tabs.Content>
        </Tabs.Root>

        <div className="flex justify-end gap-2 pt-4 border-t border-border">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit">
            {provider ? 'Update' : 'Create'} Provider
          </Button>
        </div>
      </form>
    </Modal>
  )
}
