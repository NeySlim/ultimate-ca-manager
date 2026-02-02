/**
 * HSM Page - UCM Pro
 * Hardware Security Module management
 * 
 * Uses UnifiedManagementLayout for consistent UX with UsersPage
 */
import { useState, useEffect, useMemo } from 'react'
import { 
  Key, Plus, Trash, PencilSimple, CheckCircle, XCircle, TestTube,
  Cloud, HardDrive, ArrowsClockwise, Lock, Warning
} from '@phosphor-icons/react'
import { 
  UnifiedManagementLayout, Button, Badge, FormModal, Input, Select, HelpCard,
  CompactSection, CompactGrid, CompactField, CompactStats, CompactHeader
} from '../../components'
import { useNotification } from '../../contexts/NotificationContext'
import { apiClient } from '../../services/apiClient'

const PROVIDER_TYPES = [
  { value: 'pkcs11', label: 'PKCS#11 (Local HSM)', icon: HardDrive },
  { value: 'aws-cloudhsm', label: 'AWS CloudHSM', icon: Cloud },
  { value: 'azure-keyvault', label: 'Azure Key Vault', icon: Cloud },
  { value: 'google-kms', label: 'Google Cloud KMS', icon: Cloud },
]

const PROVIDER_ICONS = {
  'pkcs11': HardDrive,
  'aws-cloudhsm': Cloud,
  'azure-keyvault': Cloud,
  'google-kms': Cloud,
}

export default function HSMPage() {
  const [providers, setProviders] = useState([])
  const [keys, setKeys] = useState([])
  const [selectedProvider, setSelectedProvider] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [modalMode, setModalMode] = useState('create')
  const [showKeyModal, setShowKeyModal] = useState(false)
  const [testing, setTesting] = useState(false)
  const { showSuccess, showError } = useNotification()

  useEffect(() => {
    loadData()
  }, [])

  useEffect(() => {
    if (selectedProvider) {
      loadKeys(selectedProvider.id)
    }
  }, [selectedProvider])

  const loadData = async () => {
    try {
      const response = await apiClient.get('/hsm/providers')
      setProviders(response.data || [])
    } catch (error) {
      showError('Failed to load HSM providers')
    } finally {
      setLoading(false)
    }
  }

  const loadKeys = async (providerId) => {
    try {
      const response = await apiClient.get(`/hsm/keys?provider_id=${providerId}`)
      setKeys(response.data || [])
    } catch (error) {
      console.error('Failed to load keys:', error)
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
    if (!confirm(`Delete HSM provider "${provider.name}"?`)) return
    
    try {
      await apiClient.delete(`/hsm/providers/${provider.id}`)
      showSuccess('Provider deleted')
      loadData()
      setSelectedProvider(null)
    } catch (error) {
      showError(error.message || 'Failed to delete provider')
    }
  }

  const handleTest = async (provider) => {
    setTesting(true)
    try {
      const response = await apiClient.post(`/hsm/providers/${provider.id}/test`)
      if (response.data?.status === 'success') {
        showSuccess(response.data.message || 'Connection successful')
        loadData()
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
        await apiClient.post('/hsm/providers', formData)
        showSuccess('Provider created')
      } else {
        await apiClient.put(`/hsm/providers/${selectedProvider.id}`, formData)
        showSuccess('Provider updated')
      }
      setShowModal(false)
      loadData()
    } catch (error) {
      showError(error.message || 'Failed to save provider')
    }
  }

  const handleGenerateKey = async (keyData) => {
    try {
      await apiClient.post(`/hsm/providers/${selectedProvider.id}/keys`, keyData)
      showSuccess('Key generated')
      setShowKeyModal(false)
      loadKeys(selectedProvider.id)
    } catch (error) {
      showError(error.message || 'Failed to generate key')
    }
  }

  const handleDeleteKey = async (key) => {
    if (!confirm(`Destroy key "${key.key_label}"? This cannot be undone.`)) return
    
    try {
      await apiClient.delete(`/hsm/keys/${key.id}`)
      showSuccess('Key destroyed')
      loadKeys(selectedProvider.id)
    } catch (error) {
      showError(error.message || 'Failed to destroy key')
    }
  }

  // Table columns
  const columns = [
    {
      key: 'name',
      header: 'Provider Name',
      render: (val, row) => {
        const Icon = PROVIDER_ICONS[row.provider_type] || Lock
        return (
          <div className="flex items-center gap-2">
            <Icon size={16} className={row.enabled ? 'status-purple-text' : 'text-text-tertiary'} />
            <span className="font-medium truncate">{val}</span>
          </div>
        )
      }
    },
    {
      key: 'provider_type',
      header: 'Type',
      render: (val) => {
        const type = PROVIDER_TYPES.find(t => t.value === val)
        return <span className="text-xs text-text-secondary">{type?.label.split(' ')[0] || val}</span>
      }
    },
    {
      key: 'enabled',
      header: 'Status',
      render: (val) => (
        <Badge variant={val ? 'success' : 'secondary'} size="sm">
          {val ? 'Enabled' : 'Disabled'}
        </Badge>
      )
    },
    {
      key: 'key_count',
      header: 'Keys',
      render: (val) => val || 0
    }
  ]

  // Row actions
  const rowActions = (row) => [
    { label: 'Test', icon: TestTube, onClick: () => handleTest(row) },
    { label: 'Edit', icon: PencilSimple, onClick: () => handleEdit(row) },
    { label: 'Delete', icon: Trash, variant: 'danger', onClick: () => handleDelete(row) }
  ]

  // Stats
  const stats = useMemo(() => {
    const enabledCount = providers.filter(p => p.enabled).length
    const totalKeys = providers.reduce((acc, p) => acc + (p.key_count || 0), 0)
    return [
      { label: 'Providers', value: providers.length, icon: Lock },
      { label: 'Enabled', value: enabledCount, icon: CheckCircle, variant: 'success' },
      { label: 'Keys', value: totalKeys, icon: Key, variant: 'primary' },
    ]
  }, [providers])

  // Render details panel
  const renderDetails = (provider) => {
    const Icon = PROVIDER_ICONS[provider.provider_type] || Lock
    const typeLabel = PROVIDER_TYPES.find(t => t.value === provider.provider_type)?.label || provider.provider_type

    return (
      <div className="p-3 space-y-3">
        {/* Header */}
        <CompactHeader
          icon={Icon}
          iconClass={provider.enabled ? 'status-purple-bg' : 'bg-bg-tertiary'}
          title={provider.name}
          subtitle={typeLabel}
          badge={
            <Badge variant={provider.enabled ? 'success' : 'secondary'} size="sm">
              {provider.enabled ? 'Enabled' : 'Disabled'}
            </Badge>
          }
        />

        {/* Stats */}
        <CompactStats stats={[
          { icon: Key, value: `${provider.key_count || 0} keys` },
          { icon: CheckCircle, value: provider.last_connected_at ? 'Connected' : 'Never' },
        ]} />

        {/* Actions */}
        <div className="flex gap-2">
          <Button 
            size="sm" 
            variant="secondary"
            className="flex-1"
            onClick={() => handleTest(provider)}
            disabled={testing}
          >
            {testing ? <ArrowsClockwise size={14} className="animate-spin" /> : <TestTube size={14} />}
            {testing ? 'Testing...' : 'Test'}
          </Button>
          <Button size="sm" variant="secondary" onClick={() => handleEdit(provider)}>
            <PencilSimple size={14} />
          </Button>
          <Button size="sm" variant="danger" onClick={() => handleDelete(provider)}>
            <Trash size={14} />
          </Button>
        </div>

        {/* Connection Error */}
        {provider.last_error && (
          <div className="p-3 rounded-lg bg-status-danger/10 border border-status-danger/30">
            <div className="flex items-center gap-2 text-status-danger text-xs">
              <Warning size={14} />
              <span className="font-medium">Connection Error</span>
            </div>
            <p className="text-[10px] text-text-secondary mt-1">{provider.last_error}</p>
          </div>
        )}

        {/* Configuration */}
        <CompactSection title="Configuration">
          {provider.provider_type === 'pkcs11' && (
            <>
              <CompactGrid>
                <CompactField label="Slot ID" value={provider.pkcs11_slot_id ?? 'Auto'} />
                <CompactField label="Token" value={provider.pkcs11_token_label || '-'} />
              </CompactGrid>
              <div className="mt-2 text-xs">
                <span className="text-text-tertiary block mb-0.5">Library Path:</span>
                <p className="font-mono text-[10px] text-text-secondary break-all bg-bg-tertiary/50 p-1.5 rounded">
                  {provider.pkcs11_library_path || '-'}
                </p>
              </div>
            </>
          )}
          
          {provider.provider_type === 'aws-cloudhsm' && (
            <CompactGrid>
              <CompactField label="Cluster" value={provider.aws_cluster_id} mono />
              <CompactField label="Region" value={provider.aws_region} />
              <CompactField label="User" value={provider.aws_crypto_user} />
            </CompactGrid>
          )}
          
          {provider.provider_type === 'azure-keyvault' && (
            <>
              <div className="text-xs mb-2">
                <span className="text-text-tertiary block mb-0.5">Vault URL:</span>
                <p className="font-mono text-[10px] text-text-secondary break-all bg-bg-tertiary/50 p-1.5 rounded">
                  {provider.azure_vault_url || '-'}
                </p>
              </div>
              <CompactGrid>
                <CompactField label="Tenant" value={provider.azure_tenant_id} mono />
                <CompactField label="Client" value={provider.azure_client_id} mono />
              </CompactGrid>
            </>
          )}
          
          {provider.provider_type === 'google-kms' && (
            <CompactGrid>
              <CompactField label="Project" value={provider.gcp_project_id} />
              <CompactField label="Location" value={provider.gcp_location} />
              <CompactField label="Key Ring" value={provider.gcp_keyring} />
            </CompactGrid>
          )}
        </CompactSection>

        {/* Keys */}
        <CompactSection title="HSM Keys">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs text-text-tertiary">{keys.length} keys in this HSM</span>
            <Button size="sm" variant="secondary" onClick={() => setShowKeyModal(true)}>
              <Plus size={12} />
              Generate
            </Button>
          </div>
          
          {keys.length === 0 ? (
            <p className="text-xs text-text-tertiary text-center py-4">No keys in this HSM</p>
          ) : (
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {keys.map(key => (
                <div 
                  key={key.id} 
                  className="flex items-center justify-between p-2 bg-bg-tertiary/50 rounded text-xs"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <Key size={14} className="text-text-tertiary flex-shrink-0" />
                    <div className="min-w-0">
                      <p className="font-medium text-text-primary truncate">{key.key_label}</p>
                      <p className="text-text-tertiary">{key.key_type} {key.key_size}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={key.status === 'active' ? 'success' : 'danger'} size="sm">
                      {key.status}
                    </Badge>
                    <Button size="sm" variant="ghost" onClick={() => handleDeleteKey(key)}>
                      <Trash size={12} className="text-status-danger" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CompactSection>
      </div>
    )
  }

  // Help content
  const helpContent = (
    <div className="space-y-4">
      <HelpCard title="Security" variant="warning">
        HSM keys are in tamper-resistant hardware. Destroying a key is irreversible.
      </HelpCard>
      <HelpCard title="Best Practice" variant="info">
        Use HSM for all CA signing keys. Test connections regularly.
      </HelpCard>
    </div>
  )

  // Table filters
  const tableFilters = [
    {
      key: 'enabled',
      label: 'Status',
      options: [
        { value: true, label: 'Enabled' },
        { value: false, label: 'Disabled' }
      ]
    },
    {
      key: 'provider_type',
      label: 'Type',
      options: PROVIDER_TYPES.map(t => ({ value: t.value, label: t.label.split(' ')[0] }))
    }
  ]

  return (
    <>
      <UnifiedManagementLayout
        title="HSM Management"
        stats={stats}
        data={providers}
        columns={columns}
        loading={loading}
        selectedItem={selectedProvider}
        onSelectItem={setSelectedProvider}
        renderDetails={renderDetails}
        detailsTitle="Provider Details"
        icon={Key}
        subtitle={`${providers.length} provider${providers.length !== 1 ? 's' : ''}`}
        splitView={true}
        splitEmptyContent={
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
              <Lock size={24} className="text-text-tertiary" weight="duotone" />
            </div>
            <p className="text-sm text-text-secondary">Select a provider to view details</p>
          </div>
        }
        searchable
        searchPlaceholder="Search providers..."
        searchKeys={['name', 'provider_type']}
        sortable
        defaultSort={{ key: 'name', direction: 'asc' }}
        paginated={false}
        rowActions={rowActions}
        filters={tableFilters}
        emptyIcon={Lock}
        emptyTitle="No HSM providers"
        emptyDescription="Configure hardware security modules for key storage"
        emptyAction={
          <Button onClick={handleCreate}>
            <Plus size={16} /> New Provider
          </Button>
        }
        helpContent={helpContent}
        actions={
          <Button size="sm" onClick={handleCreate}>
            <Plus size={16} /> New Provider
          </Button>
        }
      />

      {showModal && (
        <ProviderModal
          provider={modalMode === 'edit' ? selectedProvider : null}
          onSave={handleSave}
          onClose={() => setShowModal(false)}
        />
      )}

      {showKeyModal && selectedProvider && (
        <KeyModal
          provider={selectedProvider}
          onSave={handleGenerateKey}
          onClose={() => setShowKeyModal(false)}
        />
      )}
    </>
  )
}

function ProviderModal({ provider, onSave, onClose }) {
  const [formData, setFormData] = useState({
    name: provider?.name || '',
    provider_type: provider?.provider_type || 'pkcs11',
    enabled: provider?.enabled ?? false,
    connection_timeout: provider?.connection_timeout || 30,
    pkcs11_library_path: provider?.pkcs11_library_path || '',
    pkcs11_slot_id: provider?.pkcs11_slot_id ?? '',
    pkcs11_pin: '',
    pkcs11_token_label: provider?.pkcs11_token_label || '',
    aws_cluster_id: provider?.aws_cluster_id || '',
    aws_region: provider?.aws_region || 'us-east-1',
    aws_access_key: provider?.aws_access_key || '',
    aws_secret_key: '',
    aws_crypto_user: provider?.aws_crypto_user || '',
    aws_crypto_password: '',
    azure_vault_url: provider?.azure_vault_url || '',
    azure_tenant_id: provider?.azure_tenant_id || '',
    azure_client_id: provider?.azure_client_id || '',
    azure_client_secret: '',
    gcp_project_id: provider?.gcp_project_id || '',
    gcp_location: provider?.gcp_location || 'global',
    gcp_keyring: provider?.gcp_keyring || '',
    gcp_credentials_json: '',
  })

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    onSave(formData)
  }

  return (
    <FormModal
      open={true}
      onClose={onClose}
      title={provider ? 'Edit HSM Provider' : 'New HSM Provider'}
      size="lg"
      onSubmit={() => onSave(formData)}
      submitLabel={provider ? 'Update' : 'Create'}
    >
      <div className="grid grid-cols-2 gap-4">
        <Input label="Provider Name" value={formData.name} onChange={e => handleChange('name', e.target.value)} required />
        {!provider && (
          <Select label="Provider Type" value={formData.provider_type} onChange={value => handleChange('provider_type', value)} options={PROVIDER_TYPES} />
        )}
      </div>

      {formData.provider_type === 'pkcs11' && (
        <div className="space-y-4">
          <Input label="PKCS#11 Library Path" value={formData.pkcs11_library_path} onChange={e => handleChange('pkcs11_library_path', e.target.value)} placeholder="/usr/lib/softhsm/libsofthsm2.so" />
          <div className="grid grid-cols-2 gap-4">
            <Input label="Slot ID (optional)" type="number" value={formData.pkcs11_slot_id} onChange={e => handleChange('pkcs11_slot_id', e.target.value ? parseInt(e.target.value) : '')} />
            <Input label="Token Label" value={formData.pkcs11_token_label} onChange={e => handleChange('pkcs11_token_label', e.target.value)} />
          </div>
          <Input label="PIN" type="password" value={formData.pkcs11_pin} onChange={e => handleChange('pkcs11_pin', e.target.value)} placeholder={provider ? '(leave empty to keep)' : ''} />
        </div>
      )}

      {formData.provider_type === 'aws-cloudhsm' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Input label="Cluster ID" value={formData.aws_cluster_id} onChange={e => handleChange('aws_cluster_id', e.target.value)} />
            <Input label="Region" value={formData.aws_region} onChange={e => handleChange('aws_region', e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Input label="Access Key" value={formData.aws_access_key} onChange={e => handleChange('aws_access_key', e.target.value)} />
            <Input label="Secret Key" type="password" value={formData.aws_secret_key} onChange={e => handleChange('aws_secret_key', e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Input label="Crypto User" value={formData.aws_crypto_user} onChange={e => handleChange('aws_crypto_user', e.target.value)} />
            <Input label="Crypto Password" type="password" value={formData.aws_crypto_password} onChange={e => handleChange('aws_crypto_password', e.target.value)} />
          </div>
        </div>
      )}

      {formData.provider_type === 'azure-keyvault' && (
        <div className="space-y-4">
          <Input label="Vault URL" value={formData.azure_vault_url} onChange={e => handleChange('azure_vault_url', e.target.value)} placeholder="https://your-vault.vault.azure.net" />
          <div className="grid grid-cols-2 gap-4">
            <Input label="Tenant ID" value={formData.azure_tenant_id} onChange={e => handleChange('azure_tenant_id', e.target.value)} />
            <Input label="Client ID" value={formData.azure_client_id} onChange={e => handleChange('azure_client_id', e.target.value)} />
          </div>
          <Input label="Client Secret" type="password" value={formData.azure_client_secret} onChange={e => handleChange('azure_client_secret', e.target.value)} />
        </div>
      )}

      {formData.provider_type === 'google-kms' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Input label="Project ID" value={formData.gcp_project_id} onChange={e => handleChange('gcp_project_id', e.target.value)} />
            <Input label="Location" value={formData.gcp_location} onChange={e => handleChange('gcp_location', e.target.value)} />
          </div>
          <Input label="Key Ring" value={formData.gcp_keyring} onChange={e => handleChange('gcp_keyring', e.target.value)} />
        </div>
      )}

      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={formData.enabled} onChange={e => handleChange('enabled', e.target.checked)} />
        Enable provider
      </label>
    </FormModal>
  )
}

function KeyModal({ provider, onSave, onClose }) {
  const [formData, setFormData] = useState({
    key_label: '',
    key_type: 'rsa',
    key_size: 2048,
    purpose: 'general',
    is_exportable: false,
  })

  return (
    <FormModal
      open={true}
      onClose={onClose}
      title="Generate HSM Key"
      size="md"
      onSubmit={() => onSave(formData)}
      submitLabel="Generate Key"
    >
      <Input label="Key Label" value={formData.key_label} onChange={e => setFormData({...formData, key_label: e.target.value})} required placeholder="my-signing-key" />
      
      <div className="grid grid-cols-2 gap-4">
        <Select label="Key Type" value={formData.key_type} onChange={value => setFormData({...formData, key_type: value})} options={[{ value: 'rsa', label: 'RSA' }, { value: 'ec', label: 'ECDSA' }, { value: 'aes', label: 'AES' }]} />
        <Select
          label="Key Size"
          value={formData.key_size}
          onChange={value => setFormData({...formData, key_size: parseInt(value)})}
          options={
            formData.key_type === 'rsa' 
              ? [{ value: 2048, label: '2048' }, { value: 3072, label: '3072' }, { value: 4096, label: '4096' }]
              : formData.key_type === 'ec'
              ? [{ value: 256, label: 'P-256' }, { value: 384, label: 'P-384' }, { value: 521, label: 'P-521' }]
              : [{ value: 128, label: '128' }, { value: 256, label: '256' }]
          }
        />
      </div>

      <Select label="Purpose" value={formData.purpose} onChange={value => setFormData({...formData, purpose: value})} options={[{ value: 'general', label: 'General Purpose' }, { value: 'ca_signing', label: 'CA Signing' }, { value: 'code_signing', label: 'Code Signing' }, { value: 'encryption', label: 'Encryption' }]} />
    </FormModal>
  )
}
