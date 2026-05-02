import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Warning, CloudArrowUp } from '@phosphor-icons/react'
import { Input, Select, Button } from '../../components'
import { useNotification } from '../../contexts'

export default function RequestCertificateForm({ onSubmit, onCancel, dnsProviders, defaultEnvironment, defaultEmail }) {
  const { t } = useTranslation()
  const { showWarning } = useNotification()
  const [formData, setFormData] = useState({
    domains: '',
    email: defaultEmail,
    challenge_type: 'dns-01',
    environment: defaultEnvironment,
    dns_provider_id: dnsProviders.find(p => p.is_default)?.id || null
  })
  
  const handleSubmit = (e) => {
    e.preventDefault()
    
    const domainList = formData.domains
      .split(/[,\n]/)
      .map(d => d.trim())
      .filter(d => d)
    
    if (domainList.length === 0) {
      showWarning(t('acme.atLeastOneDomainRequired'))
      return
    }
    
    const domainRegex = /^(\*\.)?[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$/i
    const invalidDomains = domainList.filter(d => !domainRegex.test(d))
    if (invalidDomains.length > 0) {
      showWarning(t('acme.invalidDomainFormat', { domains: invalidDomains.join(', ') }))
      return
    }
    
    if (formData.challenge_type === 'http-01' && domainList.some(d => d.startsWith('*.'))) {
      showWarning(t('acme.wildcardRequiresDns01'))
      return
    }
    
    if (!formData.email) {
      showWarning(t('common.emailRequired'))
      return
    }
    
    onSubmit({
      ...formData,
      domains: domainList
    })
  }
  
  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
      {formData.environment === 'production' && (
        <div className="p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg flex items-start gap-2">
          <Warning size={18} className="text-yellow-500 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-yellow-600 dark:text-yellow-400">{t('acme.productionWarningTitle')}</p>
            <p className="text-xs text-text-secondary mt-1">{t('acme.productionWarningDesc')}</p>
          </div>
        </div>
      )}
      
      <div>
        <label className="block text-sm font-medium text-text-primary mb-1">
          {t('acme.domains')} <span className="text-red-500">*</span>
        </label>
        <textarea
          className="w-full h-24 px-3 py-2 rounded-lg border border-border bg-bg-primary text-text-primary text-sm resize-none focus:ring-2 focus:ring-accent-primary-op50 focus:border-accent-primary"
          value={formData.domains}
          onChange={(e) => setFormData(prev => ({ ...prev, domains: e.target.value }))}
          placeholder="example.com&#10;*.example.com&#10;sub.example.com"
          required
        />
        <p className="text-xs text-text-tertiary mt-1">{t('acme.domainsHelper')}</p>
      </div>
      
      <Input
        label={t('acme.contactEmail')}
        type="email"
        value={formData.email}
        onChange={(e) => setFormData(prev => ({ ...prev, email: e.target.value }))}
        required
        helperText={t('acme.contactEmailHelper')}
      />
      
      <Select
        label={t('acme.challengeType')}
        value={formData.challenge_type}
        onChange={(val) => setFormData(prev => ({ ...prev, challenge_type: val }))}
        options={[
          { value: 'dns-01', label: 'DNS-01 - ' + t('acme.dns01Desc') },
          { value: 'http-01', label: 'HTTP-01 - ' + t('acme.http01Desc') }
        ]}
        helperText={t('acme.challengeTypeHelper')}
      />
      
      {formData.challenge_type === 'dns-01' && (
        <Select
          label={t('acme.provider')}
          value={formData.dns_provider_id?.toString() || ''}
          onChange={(val) => setFormData(prev => ({ ...prev, dns_provider_id: val ? parseInt(val) : null }))}
          placeholder={t('acme.selectDnsProvider')}
          options={[
            { value: '', label: t('acme.manualDns') },
            ...dnsProviders.map(p => ({ 
              value: p.id.toString(), 
              label: p.name + (p.is_default ? ' (' + t('common.default') + ')' : '')
            }))
          ]}
          helperText={t('acme.dnsProviderHelper')}
        />
      )}
      
      <Select
        label={t('acme.environment')}
        value={formData.environment}
        onChange={(val) => setFormData(prev => ({ ...prev, environment: val }))}
        options={[
          { value: 'staging', label: t('acme.staging') + ' - ' + t('acme.stagingDesc') },
          { value: 'production', label: t('acme.production') + ' - ' + t('acme.productionDesc') }
        ]}
      />
      
      <Select
        label={t('acme.keyType')}
        value={formData.key_type || 'RSA-2048'}
        onChange={(val) => setFormData(prev => ({ ...prev, key_type: val }))}
        options={[
          { value: 'RSA-2048', label: 'RSA 2048' },
          { value: 'RSA-4096', label: 'RSA 4096' },
          { value: 'EC-P256', label: 'ECDSA P-256' },
          { value: 'EC-P384', label: 'ECDSA P-384' },
        ]}
        helperText={t('acme.keyTypeHelper')}
      />
      
      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button type="submit">
          <CloudArrowUp size={14} />
          {t('acme.requestCertificate')}
        </Button>
      </div>
    </form>
  )
}
