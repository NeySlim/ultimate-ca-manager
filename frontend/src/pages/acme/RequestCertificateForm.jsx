import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../../components/atelier'
import { Input, Select, Textarea, ToggleSwitch } from '../../components/atelier/Form'
import { useNotification } from '../../contexts'
import { acmeService } from '../../services'
import { ACME_CLIENT_LABELS, groupedOptions, listAlgorithms } from '../../lib/keyAlgorithms'
import { useKeyPlatform } from '../../lib/policyAlgorithms'
import { BrainpoolNotice } from '../../components/BrainpoolNotice'

const KEY_TYPES = ACME_CLIENT_LABELS

export default function RequestCertificateForm({
  onSubmit,
  onPreflight,
  onCancel,
  dnsProviders,
  caAccounts = [],
  defaultEnvironment,
  defaultEmail,
  defaultKeyType,
  preflightLoading = false,
}) {
  const { t } = useTranslation()
  const { showWarning } = useNotification()
  const platform = useKeyPlatform()
  const keyOptions = useMemo(() => listAlgorithms({ labels: ACME_CLIENT_LABELS, ...platform }), [platform])
  const defaultCaAccountId = caAccounts.find(a => a.is_default)?.id ?? null
  const [formData, setFormData] = useState({
    domains: '',
    email: defaultEmail,
    challenge_type: 'dns-01',
    environment: defaultEnvironment,
    acme_account_id: defaultCaAccountId,
    dns_provider_id: dnsProviders.find(p => p.is_default)?.id || null,
    key_type: KEY_TYPES.includes(defaultKeyType) ? defaultKeyType : null,
    key_source: 'generate',
    csr_pem: '',
    verify_dns: false,
    preflight_mode: 'full',
  })

  // Start from the configured client key type unless the caller or the user already chose one.
  useEffect(() => {
    if (KEY_TYPES.includes(defaultKeyType)) return undefined
    let active = true
    acmeService.getClientSettings()
      .then((res) => {
        const configured = res?.data?.key_type
        if (active && KEY_TYPES.includes(configured)) {
          setFormData(prev => (prev.key_type ? prev : { ...prev, key_type: configured }))
        }
      })
      .catch(() => {})
    return () => { active = false }
  }, [defaultKeyType])

  // A key type this server cannot use (FIPS mode, no ML-DSA) leaves the choice to the server default
  useEffect(() => {
    if (formData.key_type && !keyOptions.some(a => a.label === formData.key_type)) {
      setFormData(prev => ({ ...prev, key_type: null }))
    }
  }, [keyOptions, formData.key_type])

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

    if (formData.challenge_type !== 'dns-01' && domainList.some(d => d.startsWith('*.'))) {
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

    // Without a choice the server applies the configured default.
    if (formData.key_source !== 'csr' && formData.key_type) {
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
    <form onSubmit={handleSubmit} noValidate>
      {isProductionContext && (
        <div className="notice warn"><Icon name="warning" /><span><strong>{t('acme.productionWarningTitle')}</strong> {t('acme.productionWarningDesc')}</span></div>
      )}
      <div className="form-fields">
        <Textarea id="acme-request-domains" label={<>{t('acme.domains')} *</>} rows={4} value={formData.domains} required data-autofocus=""
          onChange={(e) => setFormData(prev => ({ ...prev, domains: e.target.value }))}
          placeholder={'example.com\n*.example.com\nsub.example.com'} helperText={t('acme.domainsHelper')} />
        <Input id="acme-request-email" label={t('acme.contactEmail')} type="email" full value={formData.email}
          onChange={(e) => setFormData(prev => ({ ...prev, email: e.target.value }))} required helperText={t('acme.contactEmailHelper')} />
        <Select id="acme-request-challenge" label={t('acme.challengeType')} full value={formData.challenge_type}
          onChange={(val) => setFormData(prev => ({ ...prev, challenge_type: val }))}
          options={[
            { value: 'dns-01', label: 'DNS-01 - ' + t('acme.dns01Desc') },
            { value: 'http-01', label: 'HTTP-01 - ' + t('acme.http01Desc') },
            { value: 'tls-alpn-01', label: 'TLS-ALPN-01 - ' + t('acme.tlsAlpn01Desc') }
          ]}
          helperText={t('acme.challengeTypeHelper')} />
        {formData.challenge_type === 'dns-01' && (
          <Select id="acme-request-dns" label={t('acme.provider')} full value={formData.dns_provider_id?.toString() || ''}
            onChange={(val) => setFormData(prev => ({ ...prev, dns_provider_id: val ? parseInt(val) : null }))}
            placeholder={t('acme.selectDnsProvider')}
            options={[
              { value: '', label: t('acme.manualDns') },
              ...dnsProviders.map(p => ({ value: p.id.toString(), label: p.name + (p.is_default ? ' (' + t('common.default') + ')' : '') }))
            ]}
            helperText={t('acme.dnsProviderHelper')} />
        )}
        {hasCaAccounts && (
          <Select id="acme-request-ca" label={t('acme.certificateAuthority')} full value={formData.acme_account_id != null ? String(formData.acme_account_id) : ''}
            onChange={(val) => setFormData(prev => ({ ...prev, acme_account_id: val ? parseInt(val) : null }))}
            options={[
              ...caAccounts.map(a => ({
                value: String(a.id),
                label: a.label
                  + (a.environment && a.environment !== 'custom' ? ` (${a.environment})` : '')
                  + (a.is_default ? `: ${t('common.default')}` : '')
                  + (a.is_registered ? '' : ` · ${t('acme.notRegistered')}`)
              })),
              { value: '', label: t('acme.useEnvironmentDefault') }
            ]}
            helperText={t('acme.certificateAuthorityHelper')} />
        )}
        {showEnvironmentSelect && (
          <Select id="acme-request-env" label={t('acme.environment')} full value={formData.environment}
            onChange={(val) => setFormData(prev => ({ ...prev, environment: val }))}
            options={[
              { value: 'staging', label: t('acme.staging') + ' - ' + t('acme.stagingDesc') },
              { value: 'production', label: t('acme.production') + ' - ' + t('acme.productionDesc') }
            ]} />
        )}
        <Select id="acme-request-key-source" label={t('acme.keySource')} value={formData.key_source} full={formData.key_source === 'csr'}
          onChange={(val) => setFormData(prev => ({ ...prev, key_source: val }))}
          options={[
            { value: 'generate', label: t('acme.keySourceGenerate') },
            { value: 'reuse', label: t('acme.keySourceReuse') },
            { value: 'csr', label: t('acme.keySourceCsr') },
          ]}
          helperText={t('acme.keySourceHelper')} />
        {formData.key_source === 'csr' ? (
          <Textarea id="acme-request-csr" label={<>{t('acme.csrPem')} *</>} mono rows={6} spellCheck={false} value={formData.csr_pem}
            onChange={(e) => setFormData(prev => ({ ...prev, csr_pem: e.target.value }))}
            placeholder="-----BEGIN CERTIFICATE REQUEST-----" helperText={t('acme.csrPemHelper')} />
        ) : (
          <Select id="acme-request-key" label={t('acme.keyType')} value={formData.key_type || ''}
            onChange={(val) => setFormData(prev => ({ ...prev, key_type: val }))}
            options={groupedOptions(keyOptions, t)} helperText={t('acme.keyTypeHelper')}
            after={<BrainpoolNotice atelier label={formData.key_type} />} />
        )}
        <fieldset className="field full" aria-describedby="hint-acme-preflight">
          <legend>{t('acme.preflightTitle')}</legend>
          <small id="hint-acme-preflight">{t('acme.preflightDesc')}</small>
          <div className="form-fields">
            <Select id="acme-request-preflight-mode" label={t('acme.preflightMode')} value={formData.preflight_mode}
              onChange={(val) => setFormData(prev => ({ ...prev, preflight_mode: val }))}
              options={[
                { value: 'full', label: t('acme.preflightModeFull') },
                { value: 'validate_only', label: t('acme.preflightModeValidateOnly') },
              ]} />
            <ToggleSwitch id="acme-request-verify-dns" label={t('acme.preflightVerifyDns')} checked={formData.verify_dns}
              onChange={(v) => setFormData(prev => ({ ...prev, verify_dns: v }))} />
          </div>
        </fieldset>
      </div>
      <div className="modal-actions">
        <button type="button" className="btn" data-action="close-modal" onClick={onCancel}>{t('common.cancel')}</button>
        <button type="button" className="btn" onClick={handlePreflight} disabled={preflightLoading || undefined}>
          <Icon name="search" />{preflightLoading ? t('acme.preflightRunning') : t('acme.preflightRun')}
        </button>
        <button type="submit" className="btn primary"><Icon name="upload" />{t('acme.requestCertificate')}</button>
      </div>
    </form>
  )
}
