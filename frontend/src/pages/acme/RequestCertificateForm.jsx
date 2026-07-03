import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Warning, CloudArrowUp, MagnifyingGlass } from '@phosphor-icons/react'
import { Input, Select, Button } from '../../components'
import { useNotification } from '../../contexts'

export default function RequestCertificateForm({
  onSubmit,
  onPreflight,
  onCancel,
  dnsProviders,
  caAccounts = [],
  defaultEnvironment,
  defaultEmail,
  preflightLoading = false,
}) {
  const { t } = useTranslation()
  const { showWarning } = useNotification()
  const defaultCaAccountId = caAccounts.find(a => a.is_default)?.id ?? null
  const [formData, setFormData] = useState({
    domains: '',
    email: defaultEmail,
    challenge_type: 'dns-01',
    environment: defaultEnvironment,
    acme_account_id: defaultCaAccountId,
    dns_provider_id: dnsProviders.find(p => p.is_default)?.id || null,
    key_type: 'RSA-2048',
    key_source: 'generate',
    csr_pem: '',
    verify_dns: false,
    preflight_mode: 'full',
  })

  const buildPayload = () => {
    const domainList = formData.domains
      .split(/[,\n]/)
      .map(d => d.trim())
      .filter(d => d)

    if (domainList.length === 0) {
      showWarning(t('acme.atLeastOneDomainRequired'))
      return null
    }

    const domainRegex = /^(\*\.)?[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$/i
    const invalidDomains = domainList.filter(d => !domainRegex.test(d))
    if (invalidDomains.length > 0) {
      showWarning(t('acme.invalidDomainFormat', { domains: invalidDomains.join(', ') }))
      return null
    }

    if (formData.challenge_type === 'http-01' && domainList.some(d => d.startsWith('*.'))) {
      showWarning(t('acme.wildcardRequiresDns01'))
      return null
    }

    if (!formData.email) {
      showWarning(t('common.emailRequired'))
      return null
    }

    if (formData.key_source === 'csr' && !formData.csr_pem.trim()) {
      showWarning(t('acme.csrRequired'))
      return null
    }

    const payload = {
      domains: domainList,
      email: formData.email,
      challenge_type: formData.challenge_type,
      environment: formData.environment,
      acme_account_id: formData.acme_account_id,
      dns_provider_id: formData.dns_provider_id,
      key_source: formData.key_source,
    }

    if (formData.key_source !== 'csr') {
      payload.key_type = formData.key_type
    }
    if (formData.key_source === 'csr') {
      payload.csr_pem = formData.csr_pem.trim()
    }

    return payload
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    const payload = buildPayload()
    if (payload) onSubmit(payload)
  }

  const handlePreflight = (e) => {
    e.preventDefault()
    const payload = buildPayload()
    if (payload) {
      onPreflight({
        ...payload,
        mode: formData.preflight_mode,
        verify_dns: formData.verify_dns,
      })
    }
  }

  const hasCaAccounts = caAccounts.length > 0
  const selectedCa = caAccounts.find(a => a.id === formData.acme_account_id)
  const showEnvironmentSelect = !hasCaAccounts || !formData.acme_account_id
  const isProductionContext = selectedCa
    ? selectedCa.environment === 'production'
    : formData.environment === 'production'

  return (
    <form className="p-4 space-y-4">
      {isProductionContext && (
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

      {hasCaAccounts && (
        <Select
          label={t('acme.certificateAuthority')}
          value={formData.acme_account_id != null ? String(formData.acme_account_id) : ''}
          onChange={(val) => setFormData(prev => ({ ...prev, acme_account_id: val ? parseInt(val) : null }))}
          options={[
            ...caAccounts.map(a => ({
              value: String(a.id),
              label: a.label
                + (a.environment && a.environment !== 'custom' ? ` (${a.environment})` : '')
                + (a.is_default ? ` — ${t('common.default')}` : '')
                + (a.is_registered ? '' : ` · ${t('acme.notRegistered')}`)
            })),
            { value: '', label: t('acme.useEnvironmentDefault') }
          ]}
          helperText={t('acme.certificateAuthorityHelper')}
        />
      )}

      {showEnvironmentSelect && (
        <Select
          label={t('acme.environment')}
          value={formData.environment}
          onChange={(val) => setFormData(prev => ({ ...prev, environment: val }))}
          options={[
            { value: 'staging', label: t('acme.staging') + ' - ' + t('acme.stagingDesc') },
            { value: 'production', label: t('acme.production') + ' - ' + t('acme.productionDesc') }
          ]}
        />
      )}

      <Select
        label={t('acme.keySource')}
        value={formData.key_source}
        onChange={(val) => setFormData(prev => ({ ...prev, key_source: val }))}
        options={[
          { value: 'generate', label: t('acme.keySourceGenerate') },
          { value: 'reuse', label: t('acme.keySourceReuse') },
          { value: 'csr', label: t('acme.keySourceCsr') },
        ]}
        helperText={t('acme.keySourceHelper')}
      />

      {formData.key_source === 'csr' && (
        <div>
          <label className="block text-sm font-medium text-text-primary mb-1">
            {t('acme.csrPem')} <span className="text-red-500">*</span>
          </label>
          <textarea
            className="w-full h-32 px-3 py-2 rounded-lg border border-border bg-bg-primary text-text-primary text-sm font-mono resize-none focus:ring-2 focus:ring-accent-primary-op50 focus:border-accent-primary"
            value={formData.csr_pem}
            onChange={(e) => setFormData(prev => ({ ...prev, csr_pem: e.target.value }))}
            placeholder="-----BEGIN CERTIFICATE REQUEST-----"
          />
          <p className="text-xs text-text-tertiary mt-1">{t('acme.csrPemHelper')}</p>
        </div>
      )}

      {formData.key_source !== 'csr' && (
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
      )}

      <div className="p-3 rounded-lg border border-border bg-bg-secondary/50 space-y-3">
        <p className="text-sm font-medium text-text-primary">{t('acme.preflightTitle')}</p>
        <p className="text-xs text-text-secondary">{t('acme.preflightDesc')}</p>
        <Select
          label={t('acme.preflightMode')}
          value={formData.preflight_mode}
          onChange={(val) => setFormData(prev => ({ ...prev, preflight_mode: val }))}
          options={[
            { value: 'full', label: t('acme.preflightModeFull') },
            { value: 'validate_only', label: t('acme.preflightModeValidateOnly') },
          ]}
        />
        <label className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer">
          <input
            type="checkbox"
            checked={formData.verify_dns}
            onChange={(e) => setFormData(prev => ({ ...prev, verify_dns: e.target.checked }))}
            className="rounded border-border"
          />
          {t('acme.preflightVerifyDns')}
        </label>
      </div>

      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button type="button" variant="secondary" onClick={handlePreflight} disabled={preflightLoading}>
          <MagnifyingGlass size={14} />
          {preflightLoading ? t('acme.preflightRunning') : t('acme.preflightRun')}
        </Button>
        <Button type="button" onClick={handleSubmit}>
          <CloudArrowUp size={14} />
          {t('acme.requestCertificate')}
        </Button>
      </div>
    </form>
  )
}
