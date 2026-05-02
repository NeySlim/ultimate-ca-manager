import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FloppyDisk } from '@phosphor-icons/react'
import { Input, Select, Button } from '../../components'
import { useNotification } from '../../contexts'
import ProviderTypeGrid from './ProviderTypeGrid'

export default function DnsProviderForm({ provider, providerTypes, onSubmit, onCancel }) {
  const { t } = useTranslation()
  const { showWarning } = useNotification()
  const [formData, setFormData] = useState({
    name: provider?.name || '',
    provider_type: provider?.provider_type || 'manual',
    credentials: {},
    is_default: provider?.is_default || false
  })
  
  const existingCredentialKeys = provider?.credential_keys || []
  const selectedType = providerTypes.find(pt => pt.type === formData.provider_type)
  
  const handleSubmit = (e) => {
    e.preventDefault()
    
    if (!formData.name.trim()) {
      showWarning(t('acme.providerNameRequired'))
      return
    }
    
    if (selectedType?.credentials_schema && !provider) {
      const missing = selectedType.credentials_schema
        .filter(field => field.required && !formData.credentials[field.name])
        .map(field => field.label)
      if (missing.length > 0) {
        showWarning(t('acme.missingCredentials', { fields: missing.join(', ') }))
        return
      }
    }
    
    onSubmit(formData)
  }
  
  const updateCredential = (key, value) => {
    setFormData(prev => ({
      ...prev,
      credentials: { ...prev.credentials, [key]: value }
    }))
  }
  
  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
      <Input
        label={t('common.providerName')}
        value={formData.name}
        onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
        required
        placeholder={t('acme.providerNamePlaceholder')}
      />
      
      <ProviderTypeGrid
        label={t('common.providerType')}
        providers={providerTypes}
        value={formData.provider_type}
        onChange={(val) => setFormData(prev => ({ ...prev, provider_type: val, credentials: {} }))}
        disabled={!!provider}
      />
      
      {selectedType?.credentials_schema?.length > 0 && (
        <div className="space-y-3 p-3 bg-tertiary-op50 rounded-lg">
          <p className="text-sm font-medium text-text-secondary">{t('acme.credentials')}</p>
          {selectedType.credentials_schema.map(field => {
            const hasExistingValue = existingCredentialKeys.includes(field.name)
            const isPasswordType = field.type === 'password'
            
            return (
              <div key={field.name}>
                {field.type === 'select' ? (
                  <Select
                    label={field.label}
                    value={formData.credentials[field.name] || field.default || ''}
                    onChange={(val) => updateCredential(field.name, val)}
                    options={field.options || []}
                    required={field.required && !hasExistingValue}
                  />
                ) : (
                  <Input
                    label={field.label}
                    type={isPasswordType ? 'password' : 'text'}
                    autoComplete={isPasswordType ? 'new-password' : 'off'}
                    value={formData.credentials[field.name] || ''}
                    onChange={(e) => updateCredential(field.name, e.target.value)}
                    required={field.required}
                    placeholder={field.placeholder}
                    hasExistingValue={hasExistingValue}
                    helperText={field.help}
                  />
                )}
              </div>
            )
          })}
        </div>
      )}
      
      {formData.provider_type === 'manual' && (
        <div className="p-3 bg-blue-500/10 border border-blue-500/30 rounded-lg">
          <p className="text-sm text-text-secondary">{t('acme.manualDnsInfo')}</p>
        </div>
      )}
      
      <label className="flex items-center gap-3 cursor-pointer p-2 rounded-lg hover:bg-tertiary-op50 transition-colors">
        <input
          type="checkbox"
          checked={formData.is_default}
          onChange={(e) => setFormData(prev => ({ ...prev, is_default: e.target.checked }))}
          className="w-4 h-4 rounded border-border bg-bg-tertiary text-accent-primary focus:ring-accent-primary-op50"
        />
        <span className="text-sm text-text-primary">{t('acme.setAsDefault')}</span>
      </label>
      
      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button type="submit">
          <FloppyDisk size={14} />
          {provider ? t('common.update') : t('common.create')}
        </Button>
      </div>
    </form>
  )
}
