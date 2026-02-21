/**
 * HSM Page - UCM
 * Hardware Security Module management
 * 
 * Migrated to ResponsiveLayout for consistent UX
 */
import { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { 
  Key, Plus, Trash, PencilSimple, CheckCircle, XCircle, TestTube,
  Cloud, HardDrive, ArrowsClockwise, Lock, Warning
} from '@phosphor-icons/react'
import { 
  Badge, Button, FormModal, Input, Select, ExperimentalBadge,
  CompactSection, CompactGrid, CompactField, CompactStats, CompactHeader
} from '../components'
import { ResponsiveLayout, ResponsiveDataTable } from '../components/ui/responsive'
import { useNotification, useMobile } from '../contexts'
import { usePermission } from '../hooks'
import { hsmService } from '../services'
import { ToggleSwitch } from '../components/ui/ToggleSwitch'

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
  const { t } = useTranslation()
  const { canWrite, canDelete } = usePermission()
  const [providers, setProviders] = useState([])
  const [keys, setKeys] = useState([])
  const [selectedProvider, setSelectedProvider] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [modalMode, setModalMode] = useState('create')
  const [showKeyModal, setShowKeyModal] = useState(false)
  const [testing, setTesting] = useState(false)
  const [filterType, setFilterType] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [hsmStatus, setHsmStatus] = useState(null)
  const { showSuccess, showError, showConfirm } = useNotification()
  const { isMobile } = useMobile()

  useEffect(() => {
    loadData()
    loadHsmStatus()
  }, [])

  useEffect(() => {
    if (selectedProvider) {
      loadKeys(selectedProvider.id)
    }
  }, [selectedProvider])

  const loadData = async () => {
    try {
      const response = await hsmService.getProviders()
      setProviders(response.data || [])
    } catch (error) {
      showError(t('messages.errors.loadFailed.hsmProviders'))
    } finally {
      setLoading(false)
    }
  }

  const loadHsmStatus = async () => {
    try {
      const response = await hsmService.getStatus()
      setHsmStatus(response.data)
    } catch {
      // Non-critical — ignore
    }
  }

  const loadKeys = async (providerId) => {
    try {
      const response = await hsmService.getKeys(providerId)
      setKeys(response.data || [])
    } catch (error) {
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
    const confirmed = await showConfirm(t('messages.confirm.hsm.deleteProvider', { name: provider.name }), { variant: 'danger', confirmText: t('common.delete') })
    if (!confirmed) return
    try {
      await hsmService.deleteProvider(provider.id)
      showSuccess(t('messages.success.delete.provider'))
      loadData()
      setSelectedProvider(null)
    } catch (error) {
      showError(error.message || t('messages.errors.deleteFailed.provider'))
    }
  }

  const handleTest = async (provider) => {
    setTesting(true)
    try {
      const response = await hsmService.testProvider(provider.id)
      if (response.data?.success) {
        showSuccess(response.data.message || t('messages.success.hsm.connectionOk'))
        loadData()
      } else {
        showError(response.data?.message || t('messages.errors.hsm.testFailed'))
      }
    } catch (error) {
      showError(error.message || t('messages.errors.hsm.testFailed'))
    } finally {
      setTesting(false)
    }
  }

  const handleSave = async (formData) => {
    try {
      if (modalMode === 'create') {
        await hsmService.createProvider(formData)
        showSuccess(t('messages.success.create.provider'))
      } else {
        await hsmService.updateProvider(selectedProvider.id, formData)
        showSuccess(t('messages.success.update.provider'))
      }
      setShowModal(false)
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.createFailed.provider'))
    }
  }

  const handleGenerateKey = async (keyData) => {
    try {
      await hsmService.addKey(selectedProvider.id, keyData)
      showSuccess(t('messages.success.create.key'))
      setShowKeyModal(false)
      loadKeys(selectedProvider.id)
    } catch (error) {
      showError(error.message || t('messages.errors.createFailed.generic'))
    }
  }

  const handleDeleteKey = async (key) => {
    const confirmed = await showConfirm(t('messages.confirm.hsm.deleteKey', { name: key.label }), { variant: 'danger', confirmText: t('common.delete') })
    if (!confirmed) return
    try {
      await hsmService.deleteKey(key.id)
      showSuccess(t('messages.success.delete.key'))
      loadKeys(selectedProvider.id)
    } catch (error) {
      showError(error.message || t('messages.errors.deleteFailed.key'))
    }
  }

  // Table columns with icon-bg classes
  const columns = [
    {
      key: 'name',
      header: t('common.providerName'),
      priority: 1,
      sortable: true,
      render: (val, row) => {
        const Icon = PROVIDER_ICONS[row.provider_type] || Lock
        return (
          <div className="flex items-center gap-2">
            <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${
              row.enabled ? 'icon-bg-violet' : 'icon-bg-gray'
            }`}>
              <Icon size={14} weight="duotone" />
            </div>
            <span className="font-medium truncate">{val}</span>
          </div>
        )
      },
      mobileRender: (val, row) => {
        const Icon = PROVIDER_ICONS[row.provider_type] || Lock
        return (
          <div className="flex items-center justify-between gap-2 w-full">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${
                row.enabled ? 'icon-bg-violet' : 'icon-bg-gray'
              }`}>
                <Icon size={14} weight="duotone" />
              </div>
              <span className="font-medium truncate">{val}</span>
            </div>
            <Badge variant={row.enabled ? 'success' : 'secondary'} size="sm" dot pulse={row.enabled}>
              {row.enabled ? t('common.enabled') : t('common.disabled')}
            </Badge>
          </div>
        )
      }
    },
    {
      key: 'provider_type',
      header: t('common.type'),
      priority: 2,
      sortable: true,
      hideOnMobile: true,
      render: (val) => {
        const type = PROVIDER_TYPES.find(t => t.value === val)
        const isCloud = val !== 'pkcs11'
        return (
          <Badge variant={isCloud ? 'cyan' : 'secondary'} size="sm" icon={isCloud ? Cloud : HardDrive}>
            {type?.label.split(' ')[0] || val}
          </Badge>
        )
      },
      mobileRender: (val) => {
        const type = PROVIDER_TYPES.find(t => t.value === val)
        const isCloud = val !== 'pkcs11'
        return (
          <div className="flex items-center gap-2 text-xs">
            <span className="text-text-tertiary">{t('common.type')}:</span>
            <span className="text-text-secondary">{type?.label.split(' ')[0] || val}</span>
          </div>
        )
      }
    },
    {
      key: 'enabled',
      header: t('common.status'),
      priority: 1,
      sortable: true,
      hideOnMobile: true,
      render: (val) => (
        <Badge variant={val ? 'success' : 'secondary'} size="sm" dot pulse={val}>
          {val ? t('common.enabled') : t('common.disabled')}
        </Badge>
      )
    },
    {
      key: 'key_count',
      header: t('hsm.stats.keys'),
      priority: 2,
      hideOnMobile: true,
      render: (val) => (
        <Badge variant={val > 0 ? 'purple' : 'secondary'} size="sm" icon={Key}>
          {val || 0}
        </Badge>
      )
    }
  ]

  const rowActions = (row) => [
    { label: t('common.test'), icon: TestTube, onClick: () => handleTest(row) },
    ...(canWrite('hsm') ? [{ label: t('common.edit'), icon: PencilSimple, onClick: () => handleEdit(row) }] : []),
    ...(canDelete('hsm') ? [{ label: t('common.delete'), icon: Trash, variant: 'danger', onClick: () => handleDelete(row) }] : [])
  ]

  const stats = useMemo(() => {
    const enabledCount = providers.filter(p => p.enabled).length
    const disabledCount = providers.filter(p => !p.enabled).length
    const totalKeys = providers.reduce((acc, p) => acc + (p.key_count || 0), 0)
    const cloudCount = providers.filter(p => p.provider_type !== 'pkcs11').length
    return [
      { label: t('hsm.stats.providers'), value: providers.length, icon: Lock, variant: 'primary' },
      { label: t('common.enabled'), value: enabledCount, icon: CheckCircle, variant: 'success' },
      { label: t('common.disabled'), value: disabledCount, icon: XCircle, variant: 'neutral' },
      { label: t('hsm.stats.keys'), value: totalKeys, icon: Key, variant: 'purple' },
      { label: t('hsm.stats.cloud'), value: cloudCount, icon: Cloud, variant: 'cyan' },
    ]
  }, [providers, t])

  // Help content
  // Help content now provided via FloatingHelpPanel (helpPageKey="hsm")

  // Details panel content
  const renderDetails = (provider) => {
    const Icon = PROVIDER_ICONS[provider.provider_type] || Lock
    const typeLabel = PROVIDER_TYPES.find(t => t.value === provider.provider_type)?.label || provider.provider_type

    return (
      <div className="p-3 space-y-3">
        <CompactHeader
          icon={Icon}
          iconClass={provider.enabled ? 'icon-bg-violet' : 'bg-bg-tertiary'}
          title={provider.name}
          subtitle={typeLabel}
          badge={
            <Badge variant={provider.enabled ? 'success' : 'secondary'} size="sm">
              {provider.enabled ? 'Enabled' : 'Disabled'}
            </Badge>
          }
        />

        <CompactStats stats={[
          { icon: Key, value: t('hsm.keysInHsm', { count: provider.key_count || 0 }).replace('{{count}} keys in this HSM', `${provider.key_count || 0} keys`) },
          { icon: CheckCircle, value: provider.last_connected_at ? t('common.connected') : t('common.never') },
        ]} />

        <div className="flex gap-2">
          <Button type="button" size="sm" variant="secondary" className="flex-1" onClick={() => handleTest(provider)} disabled={testing}>
            {testing ? <ArrowsClockwise size={14} className="animate-spin" /> : <TestTube size={14} />}
            {testing ? t('common.testing') : t('common.test')}
          </Button>
          {canWrite('hsm') && (
          <Button type="button" size="sm" variant="secondary" onClick={() => handleEdit(provider)}>
            <PencilSimple size={14} />
          </Button>
          )}
          {canDelete('hsm') && (
          <Button type="button" size="sm" variant="danger" onClick={() => handleDelete(provider)}>
            <Trash size={14} />
          </Button>
          )}
        </div>

        {provider.last_error && (
          <div className="p-3 rounded-lg bg-status-danger-op10 border border-status-danger-op30">
            <div className="flex items-center gap-2 text-status-danger text-xs">
              <Warning size={14} />
              <span className="font-medium">{t('hsm.connectionError')}</span>
            </div>
            <p className="text-2xs text-text-secondary mt-1">{provider.last_error}</p>
          </div>
        )}

        <CompactSection title={t('common.config')}>
          {provider.provider_type === 'pkcs11' && (
            <>
              <CompactGrid>
                <CompactField autoIcon="slotId" label={t('hsm.pkcs11Config.slotId')} value={provider.pkcs11_slot_id ?? 'Auto'} />
                <CompactField autoIcon="token" label={t('hsm.pkcs11Config.token')} value={provider.pkcs11_token_label || '-'} />
              </CompactGrid>
              <div className="mt-2 text-xs">
                <span className="text-text-tertiary block mb-0.5">{t('hsm.pkcs11Config.libraryPath')}:</span>
                <p className="font-mono text-2xs text-text-secondary break-all bg-tertiary-op50 p-1.5 rounded">
                  {provider.pkcs11_library_path || '-'}
                </p>
              </div>
            </>
          )}
          {provider.provider_type === 'aws-cloudhsm' && (
            <CompactGrid>
              <CompactField autoIcon="clusterId" label={t('hsm.awsConfig.clusterId')} value={provider.aws_cluster_id} mono />
              <CompactField autoIcon="region" label={t('hsm.awsConfig.region')} value={provider.aws_region} />
              <CompactField autoIcon="cryptoUser" label={t('hsm.awsConfig.cryptoUser')} value={provider.aws_crypto_user} />
            </CompactGrid>
          )}
          {provider.provider_type === 'azure-keyvault' && (
            <>
              <div className="text-xs mb-2">
                <span className="text-text-tertiary block mb-0.5">{t('hsm.azureConfig.vaultUrl')}:</span>
                <p className="font-mono text-2xs text-text-secondary break-all bg-tertiary-op50 p-1.5 rounded">
                  {provider.azure_vault_url || '-'}
                </p>
              </div>
              <CompactGrid>
                <CompactField autoIcon="tenant" label={t('hsm.azureConfig.tenant')} value={provider.azure_tenant_id} mono />
                <CompactField autoIcon="client" label={t('hsm.azureConfig.client')} value={provider.azure_client_id} mono />
              </CompactGrid>
            </>
          )}
          {provider.provider_type === 'google-kms' && (
            <CompactGrid>
              <CompactField autoIcon="project" label={t('hsm.gcpConfig.project')} value={provider.gcp_project_id} />
              <CompactField autoIcon="location" label={t('hsm.gcpConfig.location')} value={provider.gcp_location} />
              <CompactField autoIcon="keyRing" label={t('hsm.gcpConfig.keyRing')} value={provider.gcp_keyring} />
            </CompactGrid>
          )}
        </CompactSection>

        <CompactSection title={t('hsm.hsmKeys')}>
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs text-text-tertiary">{t('hsm.keysInHsm', { count: keys.length })}</span>
            {canWrite('hsm') && (
            <Button type="button" size="sm" variant="secondary" onClick={() => setShowKeyModal(true)}>
              <Plus size={12} /> {t('common.generate')}
            </Button>
            )}
          </div>
          {keys.length === 0 ? (
            <p className="text-xs text-text-tertiary text-center py-4">{t('hsm.noKeysInHsm')}</p>
          ) : (
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {keys.map(key => (
                <div key={key.id} className="flex items-center justify-between p-2 bg-tertiary-op50 rounded text-xs">
                  <div className="flex items-center gap-2 min-w-0">
                    <Key size={14} className="text-text-tertiary flex-shrink-0" />
                    <div className="min-w-0">
                      <p className="font-medium text-text-primary truncate">{key.label}</p>
                      <p className="text-text-tertiary">{key.key_type} {key.key_size}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={key.status === 'active' ? 'success' : 'danger'} size="sm">
                      {key.status}
                    </Badge>
                    {canDelete('hsm') && (
                    <Button type="button" size="sm" variant="ghost" onClick={() => handleDeleteKey(key)}>
                      <Trash size={12} className="text-status-danger" />
                    </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CompactSection>
      </div>
    )
  }

  return (
    <>
      {hsmStatus && !hsmStatus.ready && (
        <div className="mx-4 mt-4 mb-0 p-3 rounded-lg border border-yellow-500/30 bg-yellow-500/10 flex items-start gap-3">
          <Warning size={20} className="text-yellow-500 shrink-0 mt-0.5" weight="bold" />
          <div className="text-sm">
            <p className="font-medium text-yellow-600 dark:text-yellow-400 mb-1">
              {t('hsm.statusUnavailable')}
            </p>
            <ul className="text-text-secondary space-y-0.5 text-xs">
              {!hsmStatus.pkcs11_installed && <li>• {t('hsm.pkcs11Missing')}</li>}
              {!hsmStatus.softhsm_found && <li>• {t('hsm.softhsmMissing')}</li>}
            </ul>
            {hsmStatus.install_command && (
              <code className="block mt-2 px-2 py-1 rounded bg-bg-tertiary text-xs font-mono">
                {hsmStatus.install_command}
              </code>
            )}
          </div>
        </div>
      )}
      <ResponsiveLayout
        title={t('common.hsm')}
        subtitle={t('hsm.subtitle', { count: providers.length })}
        icon={Key}
        badge={<ExperimentalBadge />}
        stats={stats}
        helpPageKey="hsm"
        splitView={true}
        splitEmptyContent={
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
              <Lock size={24} className="text-text-tertiary" weight="duotone" />
            </div>
            <p className="text-sm text-text-secondary">{t('hsm.selectProvider')}</p>
          </div>
        }
        slideOverOpen={!!selectedProvider}
        slideOverTitle={selectedProvider?.name || 'Provider Details'}
        slideOverContent={selectedProvider && renderDetails(selectedProvider)}
        slideOverWidth="lg"
        onSlideOverClose={() => setSelectedProvider(null)}
      >
        <div className="flex flex-col h-full min-h-0">
          <ResponsiveDataTable
            data={providers}
            columns={columns}
            loading={loading}
            onRowClick={setSelectedProvider}
            selectedId={selectedProvider?.id}
            searchable
            searchPlaceholder={t('common.searchProviders')}
            searchKeys={['name', 'provider_type']}
            toolbarFilters={[
              {
                key: 'enabled',
                value: filterStatus,
                onChange: setFilterStatus,
                placeholder: t('common.allStatus'),
                options: [
                  { value: 'true', label: t('common.enabled') },
                  { value: 'false', label: t('common.disabled') }
                ]
              },
              {
                key: 'provider_type',
                value: filterType,
                onChange: setFilterType,
                placeholder: t('common.allTypes'),
                options: PROVIDER_TYPES.map(t => ({ value: t.value, label: t.label.split(' ')[0] }))
              }
            ]}
            toolbarActions={canWrite('hsm') ? (
              isMobile ? (
                <Button type="button" size="lg" onClick={handleCreate} className="w-11 h-11 p-0">
                  <Plus size={22} weight="bold" />
                </Button>
              ) : (
                <Button type="button" size="sm" onClick={handleCreate}>
                  <Plus size={16} /> {t('hsm.newProvider')}
                </Button>
              )
            ) : null}
            emptyIcon={Lock}
            emptyTitle={t('hsm.noHSM')}
            emptyDescription={t('hsm.noHSMDescription')}
            emptyAction={canWrite('hsm') ?
              <Button type="button" onClick={handleCreate}>
                <Plus size={16} /> {t('hsm.newProvider')}
              </Button>
            : null}
          />
        </div>
      </ResponsiveLayout>

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
  const { t } = useTranslation()
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

  const handleChange = (field, value) => setFormData(prev => ({ ...prev, [field]: value }))

  const buildPayload = () => {
    const config = {}
    if (formData.provider_type === 'pkcs11') {
      config.module_path = formData.pkcs11_library_path
      config.token_label = formData.pkcs11_token_label
      config.user_pin = formData.pkcs11_pin
      if (formData.pkcs11_slot_id !== '') config.slot_index = formData.pkcs11_slot_id
    } else if (formData.provider_type === 'aws-cloudhsm') {
      config.module_path = formData.pkcs11_library_path || '/opt/cloudhsm/lib/libcloudhsm_pkcs11.so'
      config.hsm_user = formData.aws_crypto_user
      config.hsm_password = formData.aws_crypto_password
      config.cluster_id = formData.aws_cluster_id
    } else if (formData.provider_type === 'azure-keyvault') {
      config.vault_url = formData.azure_vault_url
      config.tenant_id = formData.azure_tenant_id
      config.client_id = formData.azure_client_id
      config.client_secret = formData.azure_client_secret
    } else if (formData.provider_type === 'google-kms') {
      config.project_id = formData.gcp_project_id
      config.location = formData.gcp_location
      config.key_ring = formData.gcp_keyring
    }
    return { name: formData.name, type: formData.provider_type, config }
  }

  return (
    <FormModal
      open={true}
      onClose={onClose}
      title={provider ? t('hsm.editProvider') : t('hsm.newProvider')}
      size="lg"
      onSubmit={() => onSave(buildPayload())}
      submitLabel={provider ? t('common.save') : t('common.create')}
    >
      <div className="grid grid-cols-2 gap-4">
        <Input label={t('common.providerName')} value={formData.name} onChange={e => handleChange('name', e.target.value)} required />
        {!provider && (
          <Select label={t('common.providerType')} value={formData.provider_type} onChange={value => handleChange('provider_type', value)} options={PROVIDER_TYPES} />
        )}
      </div>

      {formData.provider_type === 'pkcs11' && (
        <div className="space-y-4">
          <Input label={t('hsm.pkcs11Config.libraryPath')} value={formData.pkcs11_library_path} onChange={e => handleChange('pkcs11_library_path', e.target.value)} placeholder={t('hsm.pkcs11Config.libraryPathPlaceholder')} />
          <div className="grid grid-cols-2 gap-4">
            <Input label={t('hsm.pkcs11Config.slotId')} type="number" value={formData.pkcs11_slot_id} onChange={e => handleChange('pkcs11_slot_id', e.target.value ? parseInt(e.target.value) : '')} />
            <Input label={t('hsm.pkcs11Config.tokenLabel')} value={formData.pkcs11_token_label} onChange={e => handleChange('pkcs11_token_label', e.target.value)} />
          </div>
          <Input label={t('hsm.pkcs11Config.pin')} type="password" noAutofill value={formData.pkcs11_pin === '***' ? '' : (formData.pkcs11_pin || '')} onChange={e => handleChange('pkcs11_pin', e.target.value)} hasExistingValue={provider?.pkcs11_pin === '***'} />
        </div>
      )}

      {formData.provider_type === 'aws-cloudhsm' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Input label={t('hsm.awsConfig.clusterId')} value={formData.aws_cluster_id} onChange={e => handleChange('aws_cluster_id', e.target.value)} />
            <Input label={t('hsm.awsConfig.region')} value={formData.aws_region} onChange={e => handleChange('aws_region', e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Input label={t('hsm.awsConfig.accessKey')} value={formData.aws_access_key} onChange={e => handleChange('aws_access_key', e.target.value)} />
            <Input label={t('hsm.awsConfig.secretKey')} type="password" noAutofill value={formData.aws_secret_key === '***' ? '' : (formData.aws_secret_key || '')} onChange={e => handleChange('aws_secret_key', e.target.value)} hasExistingValue={provider?.aws_secret_key === '***'} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Input label={t('hsm.awsConfig.cryptoUser')} value={formData.aws_crypto_user} onChange={e => handleChange('aws_crypto_user', e.target.value)} />
            <Input label={t('hsm.awsConfig.cryptoPassword')} type="password" noAutofill value={formData.aws_crypto_password === '***' ? '' : (formData.aws_crypto_password || '')} onChange={e => handleChange('aws_crypto_password', e.target.value)} hasExistingValue={provider?.aws_crypto_password === '***'} />
          </div>
        </div>
      )}

      {formData.provider_type === 'azure-keyvault' && (
        <div className="space-y-4">
          <Input label={t('hsm.azureConfig.vaultUrl')} value={formData.azure_vault_url} onChange={e => handleChange('azure_vault_url', e.target.value)} placeholder={t('hsm.azureConfig.vaultUrlPlaceholder')} />
          <div className="grid grid-cols-2 gap-4">
            <Input label={t('hsm.azureConfig.tenantId')} value={formData.azure_tenant_id} onChange={e => handleChange('azure_tenant_id', e.target.value)} />
            <Input label={t('common.clientId')} value={formData.azure_client_id} onChange={e => handleChange('azure_client_id', e.target.value)} />
          </div>
          <Input label={t('common.clientSecret')} type="password" noAutofill value={formData.azure_client_secret === '***' ? '' : (formData.azure_client_secret || '')} onChange={e => handleChange('azure_client_secret', e.target.value)} hasExistingValue={provider?.azure_client_secret === '***'} />
        </div>
      )}

      {formData.provider_type === 'google-kms' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Input label={t('hsm.gcpConfig.projectId')} value={formData.gcp_project_id} onChange={e => handleChange('gcp_project_id', e.target.value)} />
            <Input label={t('hsm.gcpConfig.location')} value={formData.gcp_location} onChange={e => handleChange('gcp_location', e.target.value)} />
          </div>
          <Input label={t('hsm.gcpConfig.keyRing')} value={formData.gcp_keyring} onChange={e => handleChange('gcp_keyring', e.target.value)} />
        </div>
      )}

      <ToggleSwitch
        checked={formData.enabled}
        onChange={(val) => handleChange('enabled', val)}
        label={t('common.enableProvider')}
      />
    </FormModal>
  )
}

function KeyModal({ provider, onSave, onClose }) {
  const { t } = useTranslation()
  const [formData, setFormData] = useState({
    label: '',
    key_type: 'rsa',
    key_size: '2048',
    purpose: 'signing',
    extractable: false,
  })

  const algorithmOptions = {
    rsa: [{ value: '2048', label: 'RSA-2048' }, { value: '3072', label: 'RSA-3072' }, { value: '4096', label: 'RSA-4096' }],
    ec: [{ value: '256', label: 'EC-P256' }, { value: '384', label: 'EC-P384' }, { value: '521', label: 'EC-P521' }],
    aes: [{ value: '128', label: 'AES-128' }, { value: '256', label: 'AES-256' }],
  }

  const buildAlgorithm = () => {
    const prefix = formData.key_type === 'rsa' ? 'RSA' : formData.key_type === 'ec' ? 'EC-P' : 'AES'
    return `${prefix}${formData.key_type === 'ec' ? '' : '-'}${formData.key_size}`
  }

  const handleSubmit = () => {
    onSave({
      label: formData.label,
      algorithm: buildAlgorithm(),
      purpose: formData.purpose,
      extractable: formData.extractable,
    })
  }

  return (
    <FormModal
      open={true}
      onClose={onClose}
      title={t('hsm.generateHsmKey')}
      size="md"
      onSubmit={handleSubmit}
      submitLabel={t('common.generate')}
    >
      <Input label={t('hsm.keyLabel')} value={formData.label} onChange={e => setFormData({...formData, label: e.target.value})} required placeholder={t('hsm.keyLabelPlaceholder')} />
      <div className="grid grid-cols-2 gap-4">
        <Select label={t('common.keyType')} value={formData.key_type} onChange={value => setFormData({...formData, key_type: value, key_size: value === 'rsa' ? '2048' : value === 'ec' ? '256' : '128'})} options={[{ value: 'rsa', label: 'RSA' }, { value: 'ec', label: 'ECDSA' }, { value: 'aes', label: 'AES' }]} />
        <Select
          label={t('common.keySize')}
          value={formData.key_size}
          onChange={value => setFormData({...formData, key_size: value})}
          options={algorithmOptions[formData.key_type] || algorithmOptions.rsa}
        />
      </div>
      <Select label={t('common.purpose')} value={formData.purpose} onChange={value => setFormData({...formData, purpose: value})} options={[{ value: 'signing', label: t('hsm.purposes.caSigning') }, { value: 'encryption', label: t('common.smtpEncryption') }, { value: 'wrapping', label: t('hsm.purposes.general') }, { value: 'all', label: t('common.all') }]} />
    </FormModal>
  )
}
