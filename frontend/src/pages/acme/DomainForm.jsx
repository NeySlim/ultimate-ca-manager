import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../../components/atelier'
import { Input, Select, ToggleSwitch } from '../../components/atelier/Form'
import { pickerCas, unlistedPickerCas } from '../../lib/caSelection'

export default function DomainForm({ domain, dnsProviders, cas, onSubmit, onCancel }) {
  const { t, i18n } = useTranslation()
  const [formData, setFormData] = useState({
    domain: domain?.domain || '',
    dns_provider_id: (domain?.dns_provider_id?.toString?.() ?? dnsProviders[0]?.id?.toString() ?? ''),
    issuing_ca_id: domain?.issuing_ca_id?.toString() || '',
    is_wildcard_allowed: domain?.is_wildcard_allowed ?? true,
    auto_approve: domain?.auto_approve ?? false,
  })

  // Only CAs able to sign now, plus the saved one so an existing domain keeps showing its CA
  const signingCas = pickerCas(cas, formData.issuing_ca_id)
  const unlisted = unlistedPickerCas(cas, formData.issuing_ca_id)

  const handleSubmit = (e) => {
    e.preventDefault()
    onSubmit({
      domain: formData.domain,
      dns_provider_id: formData.dns_provider_id ? parseInt(formData.dns_provider_id, 10) : null,
      issuing_ca_id: formData.issuing_ca_id ? parseInt(formData.issuing_ca_id, 10) : null,
      is_wildcard_allowed: formData.is_wildcard_allowed,
      auto_approve: formData.auto_approve,
    })
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="form-fields">
      <Input
        id="acme-domain-name"
        full
        data-autofocus=""
        label={t('acme.domainName')}
        value={formData.domain}
        onChange={(e) => setFormData(prev => ({ ...prev, domain: e.target.value.toLowerCase() }))}
        required
        placeholder="example.com"
        helperText={t('acme.domainNameHelper')}
        disabled={!!domain}
      />
      
      <Select
        id="acme-domain-provider"
        label={t('acme.provider')}
        value={formData.dns_provider_id}
        onChange={(val) => setFormData(prev => ({ ...prev, dns_provider_id: val }))}
        options={dnsProviders.map(p => ({
          value: p.id.toString(),
          label: `${p.name} (${p.provider_type})`
        }))}
        required
      />

      <Select
        id="acme-domain-ca"
        label={t('acme.issuingCA')}
        value={formData.issuing_ca_id}
        onChange={(val) => setFormData(prev => ({ ...prev, issuing_ca_id: val }))}
        options={[
          { value: '', label: t('acme.useDefaultCA') },
          ...signingCas.map(ca => ({
            value: ca.id.toString(),
            label: ca.common_name || ca.descr || `CA #${ca.id}`
          }))
        ]}
        helperText={[t('acme.issuingCAProxyHelper'), unlisted > 0 && t('cas.notListedForSigning', { count: unlisted })].filter(Boolean).join(/^(ja|zh)/.test(i18n?.language || '') ? '' : ' ')}
      />

      <ToggleSwitch
        checked={formData.is_wildcard_allowed}
        onChange={(val) => setFormData(prev => ({ ...prev, is_wildcard_allowed: val }))}
        label={t('acme.allowWildcard')}
        description={t('acme.allowWildcardDesc')}
      />

      <ToggleSwitch
        checked={formData.auto_approve}
        onChange={(val) => setFormData(prev => ({ ...prev, auto_approve: val }))}
        label={t('acme.autoApproveRequests')}
        description={t('acme.autoApproveDesc')}
      />
      {formData.auto_approve && (
        <p className="notice warn"><Icon name="warning" /><span>{t('acme.autoApproveWarning')}</span></p>
      )}
      
      </div>
      <div className="modal-actions">
        <button type="button" className="btn" data-action="close-modal" onClick={onCancel}>{t('common.cancel')}</button>
        <button type="submit" className="btn primary"><Icon name="check" />{domain ? t('common.update') : t('common.create')}</button>
      </div>
    </form>
  )
}
