import { useState, useEffect, useMemo } from 'react'
import { Certificate, X, Plus, CaretDown, CaretUp } from '@phosphor-icons/react'
import { Button, Select, Input, DatePicker, EkuMultiSelect } from '../../components'
import { templatesService, ekuService } from '../../services'

// Issue Certificate Form — full-featured with template, cert type, structured SANs, date picker
export function IssueCertificateForm({ cas, initialData, onSubmit, onCancel, t }) {
  const [templates, setTemplates] = useState([])
  const [selectedTemplate, setSelectedTemplate] = useState('')
  const [showSubject, setShowSubject] = useState(false)
  const [validityMode, setValidityMode] = useState('days') // 'days' or 'date'

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
    key_type: 'rsa',
    key_size: '2048',
    validity_days: '365',
    expiry_date: '',
    ocsp_must_staple: false,
    extra_ekus: [],
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
  }

  const [sans, setSans] = useState([{ type: 'dns', value: '' }])

  // Load templates on mount (exclude CA templates — CAs are created from the CAs page)
  useEffect(() => {
    templatesService.getAll().then(res => {
      const list = res?.data || res || []
      setTemplates(Array.isArray(list) ? list.filter(t => t.template_type !== 'ca') : [])
    }).catch(() => {})
  }, [])

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
        key_type: initialData.key_type || 'rsa',
        key_size: initialData.key_size || '2048',
      }))
      if (initialData.sans?.length > 0) {
        setSans(initialData.sans.filter(s => s && typeof s.type === 'string' && typeof s.value === 'string'))
      }
      setShowSubject(true)
    }
  }, [initialData])

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
    if (!templateId) return
    const tpl = templates.find(t => String(t.id) === templateId)
    if (!tpl) return

    const updates = {}

    // Map template key_type to form fields
    if (tpl.key_type) {
      const [algo, size] = tpl.key_type.split('-')
      if (algo === 'RSA') {
        updates.key_type = 'rsa'
        updates.key_size = size || '2048'
      } else if (algo === 'EC') {
        updates.key_type = 'ecdsa'
        const curveMap = { 'P256': '256', 'P384': '384', 'P521': '521' }
        updates.key_size = curveMap[size] || '256'
      }
    }
    if (tpl.validity_days) updates.validity_days = String(tpl.validity_days)

    // Map template_type to cert_type
    const typeMap = {
      'web_server': 'server', 'vpn_server': 'server',
      'client_auth': 'client', 'vpn_client': 'client',
      'email': 'email', 'code_signing': 'code_signing',
    }
    if (tpl.template_type && typeMap[tpl.template_type]) {
      updates.cert_type = typeMap[tpl.template_type]
    }

    // Apply DN template
    if (tpl.dn_template) {
      const dn = typeof tpl.dn_template === 'string' ? JSON.parse(tpl.dn_template) : tpl.dn_template
      if (dn.O) updates.organization = dn.O
      if (dn.OU) updates.organizational_unit = dn.OU
      if (dn.C) updates.country = dn.C
      if (dn.ST) updates.state = dn.ST
      if (dn.L) updates.locality = dn.L
      // Show subject section if template has DN fields
      if (dn.O || dn.OU || dn.C || dn.ST || dn.L) setShowSubject(true)
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
    ]
    return base
  }, [t])

  const sanPlaceholder = (type) => {
    const map = { dns: t('certificates.sanDnsPlaceholder'), ip: t('certificates.sanIpPlaceholder'), email: t('certificates.sanEmailPlaceholder'), uri: t('certificates.sanUriPlaceholder') }
    return map[type] || ''
  }

  // Auto-included SANs based on CN and cert type
  const autoSans = useMemo(() => {
    const items = []
    const cn = formData.cn.trim()
    if (!cn) return items
    const certType = formData.cert_type
    const isHostname = cn.includes('.') || cn.startsWith('*')
    const isEmail = cn.includes('@') && cn.split('@').pop()?.includes('.')

    if (['server', 'combined'].includes(certType) && isHostname) {
      items.push({ type: 'dns', value: cn })
    }
    if (['email', 'combined'].includes(certType) && isEmail) {
      items.push({ type: 'email', value: cn })
    }
    const subjectEmail = formData.email?.trim()
    if (['email', 'combined'].includes(certType) && subjectEmail && subjectEmail.includes('@')) {
      if (subjectEmail !== cn && !items.some(s => s.type === 'email' && s.value === subjectEmail)) {
        items.push({ type: 'email', value: subjectEmail })
      }
    }
    return items
  }, [formData.cn, formData.cert_type, formData.email])

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

  const handleSubmit = (e) => {
    e.preventDefault()
    // Build SAN arrays
    const san_dns = [], san_ip = [], san_email = [], san_uri = []
    sans.forEach(s => {
      const v = s.value.trim()
      if (!v) return
      if (s.type === 'dns') san_dns.push(v)
      else if (s.type === 'ip') san_ip.push(v)
      else if (s.type === 'email') san_email.push(v)
      else if (s.type === 'uri') san_uri.push(v)
    })

    // Calculate validity_days from date if in date mode
    let validity_days = parseInt(formData.validity_days, 10) || 365
    if (validityMode === 'date' && formData.expiry_date) {
      const expiry = new Date(formData.expiry_date)
      const now = new Date()
      validity_days = Math.max(1, Math.ceil((expiry - now) / (1000 * 60 * 60 * 24)))
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
      key_type: formData.key_type,
      key_size: formData.key_size,
      validity_days,
      ...(san_dns.length && { san_dns }),
      ...(san_ip.length && { san_ip }),
      ...(san_email.length && { san_email }),
      ...(san_uri.length && { san_uri }),
      ...(selectedTemplate && { template_id: parseInt(selectedTemplate) }),
      ...(formData.ocsp_must_staple && { ocsp_must_staple: true }),
      ...(formData.extra_ekus?.length && { extra_ekus: formData.extra_ekus }),
    }
    onSubmit(payload)
  }

  const update = (field, val) => setFormData(prev => ({ ...prev, [field]: val }))

  // Cert type options
  const certTypeOptions = [
    { value: 'server', label: t('certificates.certTypeServer') },
    { value: 'client', label: t('certificates.certTypeClient') },
    { value: 'combined', label: t('certificates.certTypeCombined') },
    { value: 'code_signing', label: t('certificates.certTypeCodeSigning') },
    { value: 'email', label: t('certificates.certTypeEmail') },
  ]

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4 max-h-[70vh] overflow-y-auto">
      {/* Template selection */}
      {templates.length > 0 && (
        <Select
          label={t('certificates.templateOptional')}
          value={selectedTemplate}
          onChange={handleTemplateChange}
          placeholder={t('certificates.noTemplate')}
          options={[
            { value: '', label: t('certificates.noTemplate') },
            ...templates.map(tpl => ({ value: String(tpl.id), label: tpl.name }))
          ]}
        />
      )}

      {/* CA + Cert Type row */}
      <div className="grid grid-cols-2 gap-4">
        <Select
          label={t('common.certificateAuthority')}
          value={formData.ca_id}
          onChange={(val) => update('ca_id', val)}
          placeholder={t('certificates.selectCA')}
          options={cas.map(ca => ({ value: String(ca.id), label: ca.descr || ca.common_name }))}
        />
        <Select
          label={t('certificates.certType')}
          value={formData.cert_type}
          onChange={(val) => update('cert_type', val)}
          options={certTypeOptions}
        />
      </div>

      {/* Custom EKU OIDs (RFC 5280 §4.2.1.12) */}
      <EkuMultiSelect
        value={formData.extra_ekus}
        onChange={(v) => update('extra_ekus', v)}
        defaults={EKU_DEFAULTS_BY_TYPE[formData.cert_type] || []}
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
                <span className="text-[10px] font-medium uppercase tracking-wider text-accent-primary-op60 w-12">{s.type}</span>
                <span className="text-xs text-text-primary font-mono flex-1">{s.value}</span>
                <span className="text-[10px] text-accent-primary-op60 italic">{t('certificates.autoIncluded')}</span>
              </div>
            ))}
          </div>
        )}

        {/* Wildcard base domain suggestion */}
        {wildcardSuggestion && (
          <div className="flex items-center gap-2 px-2.5 py-1.5 bg-status-warning-op10 border border-status-warning-op20 rounded-md">
            <span className="text-[10px] font-medium uppercase tracking-wider status-warning-text w-12">dns</span>
            <span className="text-xs text-text-secondary font-mono flex-1">{wildcardSuggestion}</span>
            <Button type="button" variant="ghost" size="sm" onClick={addWildcardBase} className="text-[10px] status-warning-text !px-1.5 !py-0.5">
              <Plus size={10} /> {t('certificates.addBaseDomain')}
            </Button>
          </div>
        )}

        {/* Additional SANs label when auto-SANs present */}
        {autoSans.length > 0 && (
          <p className="text-[10px] text-text-tertiary">{t('certificates.additionalSans')}</p>
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

      {/* Key Settings */}
      <div className="grid grid-cols-2 gap-4">
        <Select
          label={t('common.keyType')}
          value={formData.key_type}
          onChange={(val) => {
            update('key_type', val)
            update('key_size', val === 'rsa' ? '2048' : '256')
          }}
          options={[
            { value: 'rsa', label: 'RSA' },
            { value: 'ecdsa', label: 'ECDSA' },
          ]}
        />
        <Select
          label={t('common.keySize')}
          value={formData.key_size}
          onChange={(val) => update('key_size', val)}
          options={formData.key_type === 'rsa'
            ? [{ value: '2048', label: '2048 bits' }, { value: '4096', label: '4096 bits' }]
            : [{ value: '256', label: 'P-256' }, { value: '384', label: 'P-384' }]
          }
        />
      </div>

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
            max={caExpiryDate ? Math.ceil((new Date(caExpiryDate) - new Date()) / (1000 * 60 * 60 * 24)) : undefined}
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

      {/* Actions */}
      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button type="submit">
          <Certificate size={16} />
          {t('certificates.issueCertificate')}
        </Button>
      </div>
    </form>
  )
}
