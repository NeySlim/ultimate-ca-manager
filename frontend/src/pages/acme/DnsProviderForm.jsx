import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../../components/atelier'
import { Input, Select } from '../../components/atelier/Form'
import { useNotification } from '../../contexts'
import ProviderTypeGrid from './ProviderTypeGrid'

// Same split as the server: anything that looks secret is one, the rest is the target
const SECRET_HINTS = ['secret', 'token', 'password', 'key']
const isSecretField = (field) =>
  field.type === 'password' || SECRET_HINTS.some(h => field.name.toLowerCase().includes(h))

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
  const savedFlags = provider?.credential_flags || {}
  const selectedType = providerTypes.find(pt => pt.type === formData.provider_type)
  // Saved text values are never shown: typing a target field asks for the saved secrets again
  const typed = (name) => String(formData.credentials[name] || '').trim() !== ''
  const flagValue = (field) => formData.credentials[field.name] ?? savedFlags[field.name] ?? field.default ?? false
  const changed = (field) => field.type === 'checkbox'
    ? field.name in formData.credentials && flagValue(field) !== (savedFlags[field.name] ?? field.default ?? false)
    : typed(field.name)
  const schema = selectedType?.credentials_schema || []
  const targetTyped = Boolean(provider) && schema.some(f => !isSecretField(f) && changed(f))
  const secretMissing = (field) => targetTyped && isSecretField(field)
    && existingCredentialKeys.includes(field.name) && !typed(field.name)
  
  const handleSubmit = (e) => {
    e.preventDefault()
    
    if (!formData.name.trim()) {
      showWarning(t('acme.providerNameRequired'))
      return
    }
    
    if (schema.some(secretMissing)) {
      showWarning(t('common.secretRequiredForTarget'))
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
      // Cloudflare: a token, or the legacy key with its email (the server refuses anything else)
      const c = formData.credentials
      if (formData.provider_type === 'cloudflare' && !c.api_token && !(c.api_key && c.email)) {
        showWarning(t('acme.credentialsEitherOr'))
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
    <form onSubmit={handleSubmit}>
      <div className="form-fields">
        <Input id="acme-dns-name" label={t('common.providerName')} full value={formData.name}
          onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))} required placeholder={t('acme.providerNamePlaceholder')} data-autofocus="" />
        <ProviderTypeGrid label={t('common.providerType')} providers={providerTypes} value={formData.provider_type}
          onChange={(val) => setFormData(prev => ({ ...prev, provider_type: val, credentials: {} }))} disabled={!!provider} />
        {selectedType?.credentials_schema?.length > 0 && (
          <fieldset className="field full">
            <legend>{t('acme.credentials')}</legend>
            <div className="form-fields">
              {selectedType.credentials_schema.map(field => {
                const hasExistingValue = existingCredentialKeys.includes(field.name)
                const isPasswordType = field.type === 'password'
                const fid = `acme-dns-cred-${field.name}`
                if (field.type === 'select') {
                  return (
                    <Select key={field.name} id={fid} label={field.label} full value={formData.credentials[field.name] || field.default || ''}
                      onChange={(val) => updateCredential(field.name, val)} options={field.options || []} required={field.required && !hasExistingValue} />
                  )
                }
                if (field.type === 'checkbox') {
                  return (
                    <div key={field.name} className="field full">
                      <label className="checkbox-line">
                        <input type="checkbox" id={fid} checked={flagValue(field)} aria-describedby={field.help ? `hint-${fid}` : undefined}
                          onChange={(e) => updateCredential(field.name, e.target.checked)} />
                        {field.label}
                      </label>
                      {field.help && <small id={`hint-${fid}`}>{field.help}</small>}
                    </div>
                  )
                }
                return (
                  <Input key={field.name} id={fid} label={field.label} full type={isPasswordType ? 'password' : 'text'} autoComplete={isPasswordType ? 'new-password' : 'off'}
                    value={formData.credentials[field.name] || ''} onChange={(e) => updateCredential(field.name, e.target.value)}
                    required={field.required} placeholder={field.placeholder} hasExistingValue={hasExistingValue && !secretMissing(field)} helperText={field.help}
                    {...(secretMissing(field) ? { required: true, error: t('common.secretRequiredForTarget') } : {})} />
                )
              })}
            </div>
          </fieldset>
        )}
        {formData.provider_type === 'manual' && (
          <p className="notice"><Icon name="help" /><span>{t('acme.manualDnsInfo')}</span></p>
        )}
        <label className="checkbox-line field full">
          <input type="checkbox" checked={formData.is_default} onChange={(e) => setFormData(prev => ({ ...prev, is_default: e.target.checked }))} />
          {t('acme.setAsDefault')}
        </label>
      </div>
      <div className="modal-actions">
        <button type="button" className="btn" data-action="close-modal" onClick={onCancel}>{t('common.cancel')}</button>
        <button type="submit" className="btn primary"><Icon name="check" />{provider ? t('common.update') : t('common.create')}</button>
      </div>
    </form>
  )
}
