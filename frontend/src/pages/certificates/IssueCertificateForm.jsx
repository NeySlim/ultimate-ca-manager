import { useState, useEffect, useMemo, useRef } from 'react'
import { Certificate, X, Plus, CaretDown, CaretUp, PushPin } from '@phosphor-icons/react'
import { Button, Select, Input, DatePicker, EkuMultiSelect } from '../../components'
import { templatesService, ekuService } from '../../services'
import { getSanValidationError, getAutoSansFromCn } from '../../lib/sanValidate'
import { useNotification } from '../../contexts'
import { hiddenFromIssuance, listedForIssuance, signingCas, unlistedSigningCas } from '../../lib/caSelection'
import { HiddenCasToggle } from '../../components/cas/HiddenCasToggle'
import { daysRemaining } from '../../lib/utils'
import { ISSUE_KEY_CHOICES, issueKeyLabel, isAllowed, useEffectiveAlgorithms } from '../../lib/policyAlgorithms'
import {
  ISSUE_DEFAULT_LABELS, KEY_ALGORITHMS, algorithmName, defaultKeyChoice, findAlgorithm, groupedOptions,
  isPostQuantum, isUsable, keyFamilyOptions,
} from '../../lib/keyAlgorithms'
import { BrainpoolNotice } from '../../components/BrainpoolNotice'
import { CustomExtensionsEditor } from '../../components/CustomExtensionsEditor'
import { customExtensionsPayload } from '../../lib/customExtensions'

const ISSUE_FAMILY_OPTIONS = keyFamilyOptions('issue')

// Issue Certificate Form — full-featured with template, cert type, structured SANs, date picker
export function IssueCertificateForm({ cas, initialData, onSubmit, onCancel, t }) {
  const { showError } = useNotification()
  const [templates, setTemplates] = useState([])
  const [selectedTemplate, setSelectedTemplate] = useState('')
  const [showSubject, setShowSubject] = useState(false)
  const [validityMode, setValidityMode] = useState('days') // 'days' or 'date'
  // #269: guard against double submits (crypto work makes double-clicks easy).
  // A ref, not state: React hasn't re-rendered yet when a fast second click
  // lands, so a state-closure guard would see the stale value.
  const [issuing, setIssuing] = useState(false)
  const issuingRef = useRef(false)
  // Who set the current key: 'user', 'template' or null (server default applies)
  const keySource = useRef(null)
  const [showAllTemplates, setShowAllTemplates] = useState(false)
  const [showHiddenCas, setShowHiddenCas] = useState(false)
  const [customExtRows, setCustomExtRows] = useState([])
  const [showCustomExt, setShowCustomExt] = useState(false)

  const [formData, setFormData] = useState({
    ca_id: '',
    cn: '',
    cert_type: 'server',
    description: '',
    organization: '',
    organizational_unit: '',
    country: '',
    state: '',
    locality: '',
    email: '',
    // Empty until the server names its default key for the CA and template
    key_type: '',
    key_size: '',
    validity_days: '365',
    expiry_date: '',
    ocsp_must_staple: false,
    extra_ekus: [],
    // Hybrid pair (RFC 9763): two linked certificates, one classical, one ML-DSA
    hybrid: false,
    hybrid_classical: '',
    hybrid_pq: '',
  })

  const [knownEkus, setKnownEkus] = useState([])
  useEffect(() => {
    let cancelled = false
    ekuService.getKnown()
      .then((resp) => {
        if (!cancelled) setKnownEkus(resp?.data?.ekus || resp?.ekus || [])
      })
      .catch(() => { /* dropdown still works with custom OID input */ })
    return () => { cancelled = true }
  }, [])

  // EKU OIDs implied by the selected cert_type (must mirror backend cert_profiles)
  const EKU_DEFAULTS_BY_TYPE = {
    server:       ['1.3.6.1.5.5.7.3.1'],
    client:       ['1.3.6.1.5.5.7.3.2'],
    combined:     ['1.3.6.1.5.5.7.3.1', '1.3.6.1.5.5.7.3.2'],
    code_signing: ['1.3.6.1.5.5.7.3.3'],
    email:        ['1.3.6.1.5.5.7.3.4'],
    custom:       [],
  }

  const [sans, setSans] = useState([{ type: 'dns', value: '' }])

  // Load templates on mount (exclude CA templates — CAs are created from the CAs page)
  useEffect(() => {
    templatesService.getAll().then(res => {
      const list = res?.data || res || []
      setTemplates(Array.isArray(list) ? list.filter(t => t.template_type !== 'ca') : [])
    }).catch(() => {})
  }, [])

  // Reload templates with pin status when CA changes
  useEffect(() => {
    if (!formData.ca_id) return
    
    templatesService.getForCA(formData.ca_id).then(res => {
      const list = res?.data || res || []
      setTemplates(Array.isArray(list) ? list.filter(t => t.template_type !== 'ca') : [])
    }).catch(() => {})
  }, [formData.ca_id])

  // Filter templates based on pin status and showAllTemplates toggle
  const filteredTemplates = useMemo(() => {
    // A deactivated template is not offered
    const offered = templates.filter(t => t.is_active !== false)
    if (!formData.ca_id) return offered
    
    const pinnedTemplates = offered.filter(t => t.is_pinned)
    
    // If there are pinned templates and showAllTemplates is false, show only pinned
    if (pinnedTemplates.length > 0 && !showAllTemplates) {
      return pinnedTemplates
    }
    
    // Otherwise show all templates
    return offered
  }, [templates, formData.ca_id, showAllTemplates])

  // Check if there are any pinned templates for the current CA
  const hasPinnedTemplates = useMemo(() => {
    return templates.some(t => t.is_pinned)
  }, [templates])

  // Apply re-key initial data
  useEffect(() => {
    if (initialData) {
      setFormData(prev => ({
        ...prev,
        cn: initialData.cn || '',
        organization: initialData.organization || '',
        organizational_unit: initialData.organizational_unit || '',
        country: initialData.country || '',
        state: initialData.state || '',
        locality: initialData.locality || '',
        email: initialData.email || '',
        key_type: initialData.key_type || '',
        key_size: initialData.key_size || '',
      }))
      keySource.current = initialData.key_type ? 'user' : null
      if (initialData.sans?.length > 0) {
        setSans(initialData.sans.filter(s => s && typeof s.type === 'string' && typeof s.value === 'string'))
      }
      setShowSubject(true)
    }
  }, [initialData])

  // Key types the policies of this CA/template allow (#397); the server enforces them regardless
  const { allowedKeyTypes, fips, fipsKeys, mldsa, pqStandalone, defaultKeyType } = useEffectiveAlgorithms({
    caId: formData.ca_id, templateId: selectedTemplate,
  })
  const pairKeys = useMemo(
    () => ISSUE_KEY_CHOICES.filter(([type, size]) => isAllowed(allowedKeyTypes, issueKeyLabel(type, size))
      && isUsable(findAlgorithm(issueKeyLabel(type, size)), { fips, fipsKeys, mldsa })),
    [allowedKeyTypes, fips, fipsKeys, mldsa],
  )
  // A post-quantum key the policies refuse alone (pq_standalone) is offered in a hybrid pair only
  const allowedKeys = useMemo(
    () => (pqStandalone ? pairKeys.filter(([k, sz]) => !isPostQuantum(issueKeyLabel(k, sz))) : pairKeys),
    [pairKeys, pqStandalone],
  )
  const noKeyAllowed = allowedKeys.length === 0
  const allowedLabels = useMemo(() => pairKeys.map(([k, sz]) => issueKeyLabel(k, sz)), [pairKeys])
  const hybridClassical = allowedLabels.filter(l => !isPostQuantum(l))
  const hybridPq = allowedLabels.filter(isPostQuantum)
  const hybridAvailable = hybridClassical.length > 0 && hybridPq.length > 0
  // Each side keeps its choice while allowed, else the server default when it fits that side
  // (the form's own default until the server answers), else the first allowed
  const pickHybrid = (current, allowed) => (allowed.includes(current) ? current
    : [defaultKeyType, ...ISSUE_DEFAULT_LABELS].find(l => l && allowed.includes(l)) ?? allowed[0] ?? '')
  const hybridChoice = {
    classical: pickHybrid(formData.hybrid_classical, hybridClassical),
    pq: pickHybrid(formData.hybrid_pq, hybridPq),
  }
  const isHybrid = formData.hybrid && hybridAvailable
  // The family's default key when allowed (the server's if it is of that family), else its first allowed one
  const sizeForType = (type) => {
    const serverPair = defaultKeyType ? findAlgorithm(defaultKeyType)?.issue : null
    const preferred = (serverPair?.[0] === type ? serverPair : defaultKeyChoice('issue', type, ISSUE_DEFAULT_LABELS))?.[1]
    if (noKeyAllowed || allowedKeys.some(([k, sz]) => k === type && sz === preferred)) return preferred
    return allowedKeys.find(([k]) => k === type)?.[1] ?? preferred
  }

  // The server's default key for this CA and template, until the user picks another
  useEffect(() => {
    if (keySource.current) return
    // No default (pending, failed, none allowed): no key is named, the server decides
    const pair = (defaultKeyType && findAlgorithm(defaultKeyType)?.issue) || ['', '']
    setFormData(prev => ({ ...prev, key_type: pair[0], key_size: pair[1] }))
  }, [defaultKeyType])

  // A key the policies forbid (template default, previous CA) switches to the first allowed one;
  // with no key yet and no restriction, the server default or its own choice applies
  useEffect(() => {
    if (noKeyAllowed || (!formData.key_type && !allowedKeyTypes)) return
    if (allowedKeys.some(([k, sz]) => k === formData.key_type && sz === formData.key_size)) return
    const def = !keySource.current && findAlgorithm(defaultKeyType)?.issue
    const [type, size] = (def && allowedKeys.some(([k, sz]) => k === def[0] && sz === def[1]) ? def : null)
      || allowedKeys.find(([k]) => k === formData.key_type) || allowedKeys[0]
    setFormData(prev => ({ ...prev, key_type: type, key_size: size }))
  }, [allowedKeys, allowedKeyTypes, noKeyAllowed, defaultKeyType, formData.key_type, formData.key_size])

  // Get selected CA's expiry for max date
  const selectedCa = useMemo(() => 
    cas.find(ca => String(ca.id) === formData.ca_id),
    [cas, formData.ca_id]
  )

  const caExpiryDate = useMemo(() => {
    if (!selectedCa) return null
    const d = selectedCa.valid_to || selectedCa.expires || selectedCa.expiry
    if (!d) return null
    return typeof d === 'string' ? d.split('T')[0] : null
  }, [selectedCa])

  // Today as YYYY-MM-DD
  const today = useMemo(() => new Date().toISOString().split('T')[0], [])

  // Apply template when selected
  const handleTemplateChange = (templateId) => {
    setSelectedTemplate(templateId)
    const tpl = templateId ? templates.find(t => String(t.id) === templateId) : null
    const tplPair = tpl?.key_type ? findAlgorithm(tpl.key_type)?.issue : null
    // A keyless template (or none) releases only a template's key, never the user's own choice;
    // the key is blanked until the new pair's server default arrives (the effect above sets it)
    const released = !tplPair && keySource.current === 'template'
    if (released) keySource.current = null
    const keyPair = tplPair || (released ? ['', ''] : null)
    const keyUpdates = keyPair ? { key_type: keyPair[0], key_size: keyPair[1] } : {}
    if (tplPair) keySource.current = 'template'
    if (!tpl) {
      if (keyPair) setFormData(prev => ({ ...prev, ...keyUpdates }))
      return
    }

    const updates = { ...keyUpdates }
    if (tpl.validity_days) updates.validity_days = String(tpl.validity_days)

    // Map template_type to cert_type (unmapped types fall back to custom:
    // the template's own KU/EKU govern issuance, no profile is imposed)
    const typeMap = {
      'web_server': 'server', 'vpn_server': 'server',
      'client_auth': 'client', 'vpn_client': 'client', 'piv': 'client',
      'email': 'email', 'code_signing': 'code_signing',
    }
    if (tpl.template_type) {
      updates.cert_type = typeMap[tpl.template_type] || 'custom'
    }

    // Apply DN template
    if (tpl.dn_template) {
      const dn = typeof tpl.dn_template === 'string' ? JSON.parse(tpl.dn_template) : tpl.dn_template
      if (dn.O) updates.organization = dn.O
      if (dn.OU) updates.organizational_unit = dn.OU
      if (dn.C) updates.country = dn.C
      if (dn.ST) updates.state = dn.ST
      if (dn.L) updates.locality = dn.L
      // Skip placeholder values like "{email}" used by built-in templates
      const templateEmail = dn.emailAddress && !/[{}]/.test(dn.emailAddress) ? dn.emailAddress.trim() : ''
      if (templateEmail) updates.email = templateEmail
      // Show subject section if template has DN fields
      if (dn.O || dn.OU || dn.C || dn.ST || dn.L || templateEmail) setShowSubject(true)
    }

    setFormData(prev => ({ ...prev, ...updates }))
  }

  // SAN management
  const addSan = () => setSans(prev => [...prev, { type: 'dns', value: '' }])
  const removeSan = (idx) => setSans(prev => prev.filter((_, i) => i !== idx))
  const updateSan = (idx, field, val) => setSans(prev =>
    prev.map((s, i) => i === idx ? { ...s, [field]: val } : s)
  )

  // Suggested SAN types per cert_type
  const sanTypeOptions = useMemo(() => {
    const base = [
      { value: 'dns', label: t('certificates.sanDns') },
      { value: 'ip', label: t('certificates.sanIp') },
      { value: 'email', label: t('certificates.sanEmail') },
      { value: 'uri', label: t('certificates.sanUri') },
      { value: 'upn', label: t('certificates.sanUpn') },
    ]
    return base
  }, [t])

  const sanPlaceholder = (type) => {
    const map = {
      dns: t('certificates.sanDnsPlaceholder'),
      ip: t('certificates.sanIpPlaceholder'),
      email: t('certificates.sanEmailPlaceholder'),
      uri: t('certificates.sanUriPlaceholder'),
      upn: t('certificates.sanUpnPlaceholder'),
    }
    return map[type] || ''
  }

  // Auto-included SANs based on CN and cert type
  const autoSans = useMemo(
    () => getAutoSansFromCn({
      cn: formData.cn,
      certType: formData.cert_type,
      subjectEmail: formData.email,
    }),
    [formData.cn, formData.cert_type, formData.email],
  )

  // Wildcard → suggest base domain
  const wildcardSuggestion = useMemo(() => {
    const cn = formData.cn.trim()
    if (!cn.startsWith('*.')) return null
    const baseDomain = cn.slice(2)
    if (!baseDomain || !baseDomain.includes('.')) return null
    if (sans.some(s => s.type === 'dns' && s.value === baseDomain)) return null
    return baseDomain
  }, [formData.cn, sans])

  const addWildcardBase = () => {
    if (!wildcardSuggestion) return
    setSans(prev => [...prev, { type: 'dns', value: wildcardSuggestion }])
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (issuingRef.current) return

    const sanError = [...autoSans, ...sans]
      .map((s) => getSanValidationError(s.type, s.value, { i18nNs: 'certificates' }))
      .find(Boolean)
    if (sanError) {
      showError(t(sanError.key, sanError.params))
      return
    }
    const customExt = customExtensionsPayload(customExtRows)
    if (!customExt.valid) {
      setShowCustomExt(true)
      showError(t('customExtensions.fixErrors'))
      return
    }

    // Build SAN arrays (manual + auto-included from CN)
    const san_dns = [], san_ip = [], san_email = [], san_uri = [], san_upn = []
    const pushSan = (type, value) => {
      const v = value.trim()
      if (!v) return
      if (type === 'dns' && !san_dns.includes(v)) san_dns.push(v)
      else if (type === 'ip' && !san_ip.includes(v)) san_ip.push(v)
      else if (type === 'email' && !san_email.includes(v)) san_email.push(v)
      else if (type === 'uri' && !san_uri.includes(v)) san_uri.push(v)
      else if (type === 'upn' && !san_upn.includes(v)) san_upn.push(v)
    }
    autoSans.forEach((s) => pushSan(s.type, s.value))
    sans.forEach((s) => pushSan(s.type, s.value))

    // Calculate validity_days from date if in date mode
    let validity_days = parseInt(formData.validity_days, 10) || 365
    if (validityMode === 'date' && formData.expiry_date) {
      // Same rounding as the server, then at least a day: a validity of
      // zero is refused.
      validity_days = Math.max(1, daysRemaining(formData.expiry_date) ?? 1)
    }

    const payload = {
      ca_id: formData.ca_id,
      cn: formData.cn,
      cert_type: formData.cert_type,
      description: formData.description || undefined,
      organization: formData.organization || undefined,
      organizational_unit: formData.organizational_unit || undefined,
      country: formData.country || undefined,
      state: formData.state || undefined,
      locality: formData.locality || undefined,
      email: formData.email || undefined,
      key_type: formData.key_type || undefined,
      key_size: formData.key_size || undefined,
      ...(isHybrid && {
        key_type: findAlgorithm(hybridChoice.classical).issue[0],
        key_size: findAlgorithm(hybridChoice.classical).issue[1],
        hybrid: { classical: hybridChoice.classical, pq: hybridChoice.pq },
      }),
      validity_days,
      ...(san_dns.length && { san_dns }),
      ...(san_ip.length && { san_ip }),
      ...(san_email.length && { san_email }),
      ...(san_uri.length && { san_uri }),
      ...(san_upn.length && { san_upn }),
      ...(selectedTemplate && { template_id: parseInt(selectedTemplate) }),
      ...(formData.ocsp_must_staple && { ocsp_must_staple: true }),
      ...(formData.extra_ekus?.length && { extra_ekus: formData.extra_ekus }),
      ...(customExt.entries.length && { custom_extensions: customExt.entries }),
    }
    setIssuing(true)
    issuingRef.current = true
    try {
      await onSubmit(payload)
    } finally {
      issuingRef.current = false
      setIssuing(false)
    }
  }

  const update = (field, val) => setFormData(prev => ({ ...prev, [field]: val }))

  // Cert type options
  const certTypeOptions = [
    { value: 'server', label: t('certificates.certTypeServer') },
    { value: 'client', label: t('certificates.certTypeClient') },
    { value: 'combined', label: t('certificates.certTypeCombined') },
    { value: 'code_signing', label: t('certificates.certTypeCodeSigning') },
    { value: 'email', label: t('certificates.certTypeEmail') },
    { value: 'custom', label: t('certificates.certTypeCustom') },
  ]

  // When a template is selected it governs KU/EKU: show its EKUs as the
  // locked defaults instead of the cert_type profile
  const templateEkuDefaults = useMemo(() => {
    if (!selectedTemplate) return null
    const tpl = templates.find(tp => String(tp.id) === selectedTemplate)
    if (!tpl) return null
    let ext = tpl.extensions_template
    if (typeof ext === 'string') {
      try { ext = JSON.parse(ext) } catch { ext = null }
    }
    const names = ext?.extended_key_usage
    if (!Array.isArray(names) || names.length === 0) return null
    const byName = Object.fromEntries(knownEkus.map(e => [String(e.name).toLowerCase(), e.oid]))
    return names
      .map(n => /^[0-2](?:\.\d+)+$/.test(n) ? n : byName[String(n).toLowerCase()])
      .filter(Boolean)
  }, [selectedTemplate, templates, knownEkus])

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
      {/* Template selection */}
      {filteredTemplates.length > 0 && (
        <div className="space-y-2">
          <Select
            label={t('certificates.templateOptional')}
            value={selectedTemplate}
            onChange={handleTemplateChange}
            placeholder={t('certificates.noTemplate')}
            options={[
              { value: '', label: t('certificates.noTemplate') },
              ...filteredTemplates.map(tpl => ({ 
                value: String(tpl.id), 
                label: tpl.is_pinned ? (
                  <span className="flex items-center gap-2">
                    {tpl.name}
                    <PushPin size={14} className="text-accent-primary shrink-0" weight="fill" />
                  </span>
                ) : tpl.name
              }))
            ]}
          />
          {hasPinnedTemplates && (
            <button
              type="button"
              onClick={() => setShowAllTemplates(!showAllTemplates)}
              className="text-xs text-text-tertiary hover:text-text-secondary transition-colors"
            >
              {showAllTemplates ? t('templates.showPinnedOnly') : t('templates.showAllTemplates', { count: templates.length })}
            </button>
          )}
        </div>
      )}

      {/* CA + Cert Type row */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <Select
            label={t('common.certificateAuthority')}
            value={formData.ca_id}
            onChange={(val) => update('ca_id', val)}
            placeholder={t('certificates.selectCA')}
            options={listedForIssuance(signingCas(cas), showHiddenCas, formData.ca_id).map(ca => ({ value: String(ca.id), label: ca.descr || ca.common_name }))}
            helperText={unlistedSigningCas(cas) > 0 ? t('cas.notListedForSigning', { count: unlistedSigningCas(cas) }) : undefined}
          />
          <HiddenCasToggle count={hiddenFromIssuance(signingCas(cas), formData.ca_id)} shown={showHiddenCas} onToggle={() => setShowHiddenCas(v => !v)} />
        </div>
        <div>
          <Select
            label={t('certificates.certType')}
            value={formData.cert_type}
            onChange={(val) => update('cert_type', val)}
            options={certTypeOptions}
            disabled={!!selectedTemplate}
          />
          {selectedTemplate && (
            <p className="mt-1 text-xs text-text-tertiary">{t('certificates.certTypeFromTemplate')}</p>
          )}
        </div>
      </div>

      {/* Custom EKU OIDs (RFC 5280 §4.2.1.12) */}
      <EkuMultiSelect
        value={formData.extra_ekus}
        onChange={(v) => update('extra_ekus', v)}
        defaults={templateEkuDefaults ?? (EKU_DEFAULTS_BY_TYPE[formData.cert_type] || [])}
        knownEkus={knownEkus}
      />

      {/* CN + Description */}
      <Input 
        label={t('common.commonName')} 
        placeholder={formData.cert_type === 'email' ? t('certificates.sanEmailPlaceholder') : formData.cert_type === 'code_signing' ? 'John Doe' : 'example.com'}
        value={formData.cn}
        onChange={(e) => update('cn', e.target.value)}
        required
      />

      <Input
        label={t('common.description')}
        placeholder={t('certificates.descriptionPlaceholder')}
        value={formData.description}
        onChange={(e) => update('description', e.target.value)}
      />

      {/* Subject Details (collapsible) */}
      <div className="border border-border rounded-lg">
        <button
          type="button"
          onClick={() => setShowSubject(!showSubject)}
          className="w-full flex items-center justify-between p-3 text-sm font-medium text-text-secondary hover:text-text-primary transition-colors"
        >
          <span>{t('certificates.subjectDetails')}</span>
          {showSubject ? <CaretUp size={16} /> : <CaretDown size={16} />}
        </button>
        {showSubject && (
          <div className="px-3 pb-3 space-y-3 border-t border-border pt-3">
            <div className="grid grid-cols-3 gap-3">
              <Input
                label={t('common.country')}
                placeholder={t('common.countryPlaceholder')}
                value={formData.country}
                onChange={(e) => update('country', e.target.value)}
                maxLength={2}
              />
              <Input
                label={t('common.stateProvince')}
                placeholder={t('common.statePlaceholder')}
                value={formData.state}
                onChange={(e) => update('state', e.target.value)}
              />
              <Input
                label={t('common.locality')}
                placeholder="City"
                value={formData.locality}
                onChange={(e) => update('locality', e.target.value)}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Input
                label={t('common.organization')}
                placeholder={t('certificates.orgPlaceholder')}
                value={formData.organization}
                onChange={(e) => update('organization', e.target.value)}
              />
              <Input
                label={'OU'}
                placeholder={t('certificates.ouPlaceholder')}
                value={formData.organizational_unit}
                onChange={(e) => update('organizational_unit', e.target.value)}
              />
            </div>
            <Input
              label={t('common.email')}
              placeholder={t('certificates.emailPlaceholder')}
              value={formData.email}
              onChange={(e) => update('email', e.target.value)}
              type="email"
            />
          </div>
        )}
      </div>

      {/* Subject Alternative Names — structured */}
      <div className="space-y-2">
        <label className="block text-xs font-medium text-text-secondary">
          {t('common.subjectAltNames')}
        </label>

        {/* Auto-included SANs from CN */}
        {autoSans.length > 0 && (
          <div className="space-y-1">
            {autoSans.map((s, idx) => (
              <div key={`auto-${idx}`} className="flex items-center gap-2 px-2.5 py-1.5 bg-accent-primary-op10 border border-accent-primary-op20 rounded-md">
                <span className="text-xs font-medium uppercase tracking-wider text-accent-primary-op60 w-12">{s.type}</span>
                <span className="text-xs text-text-primary font-mono flex-1">{s.value}</span>
                <span className="text-xs text-accent-primary-op60 italic">{t('certificates.autoIncluded')}</span>
              </div>
            ))}
          </div>
        )}

        {/* Wildcard base domain suggestion */}
        {wildcardSuggestion && (
          <div className="flex items-center gap-2 px-2.5 py-1.5 bg-status-warning-op10 border border-status-warning-op20 rounded-md">
            <span className="text-xs font-medium uppercase tracking-wider status-warning-text w-12">dns</span>
            <span className="text-xs text-text-secondary font-mono flex-1">{wildcardSuggestion}</span>
            <Button type="button" variant="ghost" size="sm" onClick={addWildcardBase} className="text-xs status-warning-text !px-1.5 !py-0.5">
              <Plus size={10} /> {t('certificates.addBaseDomain')}
            </Button>
          </div>
        )}

        {/* Additional SANs label when auto-SANs present */}
        {autoSans.length > 0 && (
          <p className="text-xs text-text-tertiary">{t('certificates.additionalSans')}</p>
        )}

        <div className="space-y-2">
          {sans.map((san, idx) => (
            <div key={idx} className="flex items-center gap-2">
              <div className="w-28 flex-shrink-0">
                <Select
                  value={san.type}
                  onChange={(val) => updateSan(idx, 'type', val)}
                  options={sanTypeOptions}
                />
              </div>
              <div className="flex-1">
                <Input
                  placeholder={sanPlaceholder(san.type)}
                  value={san.value}
                  onChange={(e) => updateSan(idx, 'value', e.target.value)}
                />
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => removeSan(idx)}
                disabled={sans.length === 1 && !san.value}
                className="flex-shrink-0 text-text-tertiary hover:text-accent-danger"
              >
                <X size={14} />
              </Button>
            </div>
          ))}
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={addSan} className="text-xs">
          <Plus size={12} /> {t('certificates.addSan')}
        </Button>
      </div>

      {/* Hybrid pair (RFC 9763): offered when the policies allow a classical and an ML-DSA key */}
      {hybridAvailable && (
        <div className="flex items-start gap-3">
          <input
            type="checkbox"
            id="hybrid_pair"
            checked={formData.hybrid}
            onChange={(e) => update('hybrid', e.target.checked)}
            className="w-4 h-4 mt-0.5 rounded border-border accent-accent-primary"
          />
          <div>
            <label htmlFor="hybrid_pair" className="text-sm text-text-secondary cursor-pointer">
              {t('certificates.hybrid.toggle')}
            </label>
            <p className="text-xs text-text-tertiary">{t('certificates.hybrid.toggleHint')}</p>
          </div>
        </div>
      )}

      {isHybrid ? (
        <div className="grid grid-cols-2 gap-4">
          <Select
            label={t('certificates.hybrid.classical')}
            value={hybridChoice.classical}
            onChange={(val) => update('hybrid_classical', val)}
            options={groupedOptions(hybridClassical.map(findAlgorithm), t, k => algorithmName(k, t))}
          />
          <Select
            label={t('certificates.hybrid.pq')}
            value={hybridChoice.pq}
            onChange={(val) => update('hybrid_pq', val)}
            options={groupedOptions(hybridPq.map(findAlgorithm), t, k => algorithmName(k, t))}
          />
        </div>
      ) : (<>
      {/* Key Settings */}
      <div className="grid grid-cols-2 gap-4">
        <Select
          label={t('common.keyType')}
          value={formData.key_type}
          onChange={(val) => {
            keySource.current = 'user'
            update('key_type', val)
            update('key_size', sizeForType(val))
          }}
          options={ISSUE_FAMILY_OPTIONS.filter(o => noKeyAllowed || allowedKeys.some(([k]) => k === o.value))}
        />
        <Select
          label={t('common.keySize')}
          value={formData.key_size}
          onChange={(val) => { keySource.current = 'user'; update('key_size', val) }}
          options={groupedOptions(
            KEY_ALGORITHMS.filter(k => k.generate && k.issue && k.issue[0] === formData.key_type), t,
            k => algorithmName(k, t, 'sizeKey'), k => k.issue[1],
          ).filter(o => noKeyAllowed || allowedKeys.some(([k, sz]) => k === formData.key_type && sz === o.value))}
        />
      </div>
      <BrainpoolNotice label={issueKeyLabel(formData.key_type, formData.key_size)} />
      {noKeyAllowed && (
        <p className="text-xs text-status-danger" role="alert">{t('certificates.noKeyTypeAllowedByPolicy')}</p>
      )}
      </>)}

      {/* Validity — days or calendar */}
      <div className="space-y-2">
        <div className="flex items-center gap-3">
          <label className="text-xs font-medium text-text-secondary">{t('common.validityPeriod')}</label>
          <div className="flex items-center gap-1 bg-bg-tertiary rounded-md p-0.5 border border-border">
            <button
              type="button"
              onClick={() => setValidityMode('days')}
              className={`px-2 py-0.5 text-xs rounded transition-colors ${validityMode === 'days' ? 'bg-bg-primary text-text-primary shadow-sm' : 'text-text-tertiary hover:text-text-secondary'}`}
            >
              {t('certificates.validityDays')}
            </button>
            <button
              type="button"
              onClick={() => setValidityMode('date')}
              className={`px-2 py-0.5 text-xs rounded transition-colors ${validityMode === 'date' ? 'bg-bg-primary text-text-primary shadow-sm' : 'text-text-tertiary hover:text-text-secondary'}`}
            >
              {t('certificates.validityDate')}
            </button>
          </div>
        </div>

        {validityMode === 'days' ? (
          <Input 
            type="number"
            placeholder={t('common.validityPlaceholder')}
            value={formData.validity_days}
            onChange={(e) => update('validity_days', e.target.value)}
            min="1"
            max={caExpiryDate ? daysRemaining(caExpiryDate) : undefined}
          />
        ) : (
          <DatePicker
            value={formData.expiry_date}
            onChange={(val) => update('expiry_date', val)}
            min={today}
            max={caExpiryDate || undefined}
          />
        )}
        {caExpiryDate && (
          <p className="text-xs text-text-tertiary">
            {t('certificates.maxValidityCa', { date: caExpiryDate })}
          </p>
        )}
      </div>

      {/* OCSP Must-Staple */}
      <div className="flex items-center gap-3 py-2">
        <input
          type="checkbox"
          id="ocsp_must_staple"
          checked={formData.ocsp_must_staple}
          onChange={(e) => update('ocsp_must_staple', e.target.checked)}
          className="w-4 h-4 rounded border-border accent-accent-primary"
        />
        <label htmlFor="ocsp_must_staple" className="text-sm text-text-secondary cursor-pointer">
          {t('certificates.ocspMustStaple')}
        </label>
      </div>

      {/* Custom extensions (#437) */}
      <div className="space-y-2">
        <button
          type="button"
          onClick={() => setShowCustomExt(v => !v)}
          className="flex items-center gap-1 text-sm font-medium text-text-secondary hover:text-text-primary"
          aria-expanded={showCustomExt}
        >
          {showCustomExt ? <CaretUp size={14} /> : <CaretDown size={14} />}
          {t('customExtensions.title')}
          {customExtRows.length > 0 && <span className="text-xs text-text-tertiary">({customExtRows.length})</span>}
        </button>
        {showCustomExt && (
          <CustomExtensionsEditor
            rows={customExtRows}
            onChange={setCustomExtRows}
            t={t}
            hint={`${t('customExtensions.hint')} ${selectedTemplate ? t('customExtensions.requestHint') : ''}`.trim()}
          />
        )}
      </div>

      {/* Actions */}
      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button type="submit" disabled={issuing || noKeyAllowed}>
          <Certificate size={16} />
          {issuing ? t('common.creating') : t('certificates.issueCertificate')}
        </Button>
      </div>
    </form>
  )
}
