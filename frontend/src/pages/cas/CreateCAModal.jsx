/**
 * CAs Page — Create CA modal (self-contained with own state + effects)
 *
 * Props:
 *   open       — boolean, whether modal is open
 *   onClose    — called when modal should close
 *   cas        — array of existing CAs (for parent CA select dropdown)
 *   onSuccess  — called with the new CA after it is created
 */
import { useState, useEffect, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { CaretRight, CaretDown, X, Plus } from '@phosphor-icons/react'
import { Modal, Input, Select, Button } from '../../components'
import { casService, hsmService } from '../../services'
import { useNotification } from '../../contexts'
import { useWebSocket } from '../../hooks'
import { extractData, cn, downloadBlob } from '../../lib/utils'
import { signingCas } from '../../lib/caSelection'
import { CA_KEY_CHOICES, POLICY_DIGESTS, caKeyLabel, isAllowed, useEffectiveAlgorithms } from '../../lib/policyAlgorithms'
import { PSS_HSM_TYPES } from '../../lib/signatureName'
import { KEY_ALGORITHMS, defaultDigestFor, groupedOptions, listAlgorithms } from '../../lib/keyAlgorithms'
import { BrainpoolNotice } from '../../components/BrainpoolNotice'
import { COMPLIANCE_PROFILE_NAMES, limitsWithProfile, useComplianceDefault, useComplianceProfiles } from '../../lib/complianceProfiles'

const EC_CA_ALGORITHMS = KEY_ALGORITHMS.filter(k => k.ca && k.ca[0] === 'ECDSA')
const VALIDITY_YEAR_PRESETS = [1, 2, 3, 5, 10, 15, 20]
const CUSTOM_VALIDITY = 'custom'
const DEFAULT_KEY_SIZE = { RSA: '3072', ECDSA: 'prime256v1' }
// ANSSI PG-083 accepts RSA-2048 until the end of 2030, ETSI TS 119 312 until the end of 2026
const RSA_2048_HORIZON = Date.UTC(2031, 0, 1)
// The API ceiling: 50 years
const MAX_CA_VALIDITY_DAYS = 18250

const ROOT_KEY_USAGE = ['keyCertSign', 'cRLSign']
const INTERMEDIATE_KEY_USAGE = ['digitalSignature', 'keyCertSign', 'cRLSign']
const CA_KU_OPTIONS = ['digitalSignature', 'keyCertSign', 'cRLSign']

const NC_TYPE_OPTIONS = [
  { value: 'dns', labelKey: 'cas.nameConstraintTypeDns' },
  { value: 'ip', labelKey: 'cas.nameConstraintTypeIp' },
  { value: 'email', labelKey: 'cas.nameConstraintTypeEmail' },
]

/**
 * Repeatable {type, value} rows for a NameConstraints subtree list.
 * Mirrors the SAN editor in IssueCertificateForm.
 */
function NameConstraintRows({ label, hint, addLabel, rows, onChange }) {
  const { t } = useTranslation()
  const typeOptions = NC_TYPE_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) }))
  const update = (idx, key, val) =>
    onChange(rows.map((r, i) => (i === idx ? { ...r, [key]: val } : r)))
  const add = () => onChange([...rows, { type: 'dns', value: '' }])
  const remove = (idx) => onChange(rows.filter((_, i) => i !== idx))

  return (
    <fieldset className="space-y-2">
      <legend className="text-xs font-medium text-text-secondary">{label}</legend>
      {rows.map((row, idx) => (
        <div key={idx} className="flex items-center gap-2">
          <div className="w-28 flex-shrink-0">
            <Select
              value={row.type}
              onChange={(val) => update(idx, 'type', val)}
              options={typeOptions}
            />
          </div>
          <div className="flex-1">
            <Input
              placeholder={t('cas.nameConstraintValuePlaceholder')}
              value={row.value}
              onChange={(e) => update(idx, 'value', e.target.value)}
            />
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => remove(idx)}
            className="flex-shrink-0 text-text-tertiary hover:text-accent-danger"
            aria-label={t('common.remove')}
          >
            <X size={14} />
          </Button>
        </div>
      ))}
      <Button type="button" variant="ghost" size="sm" onClick={add} className="text-xs">
        <Plus size={12} /> {addLabel}
      </Button>
      {hint && <p className="text-xs text-text-tertiary">{hint}</p>}
    </fieldset>
  )
}

export function CreateCAModal({ open, onClose, cas, onSuccess }) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const { muteToasts } = useWebSocket()

  const [createFormType, setCreateFormType] = useState('root')
  const [createFormParentCAId, setCreateFormParentCAId] = useState(null)
  const [createFormKeyAlgo, setCreateFormKeyAlgo] = useState('RSA')
  const [createFormKeySize, setCreateFormKeySize] = useState(DEFAULT_KEY_SIZE.RSA)
  const [createFormValidity, setCreateFormValidity] = useState('10')
  const [createFormValidityDays, setCreateFormValidityDays] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [createFormPathLength, setCreateFormPathLength] = useState('')
  const [createFormNamedUrls, setCreateFormNamedUrls] = useState(false)
  const [createFormNCPermitted, setCreateFormNCPermitted] = useState([])
  const [createFormNCExcluded, setCreateFormNCExcluded] = useState([])
  const [createFormDigest, setCreateFormDigest] = useState('auto')
  const [createFormSignatureScheme, setCreateFormSignatureScheme] = useState('pkcs1v15')
  // null = untouched (the proposal applies), '' = no profile
  const [createFormProfile, setCreateFormProfile] = useState(null)
  const [createFormKeyUsage, setCreateFormKeyUsage] = useState(ROOT_KEY_USAGE)
  const [createFormEkuServerAuth, setCreateFormEkuServerAuth] = useState(false)
  const [showCertProfile, setShowCertProfile] = useState(false)
  // #269: guard against double submits (slow RSA keygens invite double-clicks).
  // A ref, not state: state updates don't apply before React re-renders, so a
  // fast second click would slip through a state-closure guard.
  const [creating, setCreating] = useState(false)
  const creatingRef = useRef(false)

  // HSM key storage state
  const [createFormKeyStorage, setCreateFormKeyStorage] = useState('local') // 'local' | 'hsm'
  const [createFormHsmProviderId, setCreateFormHsmProviderId] = useState('')
  const [createFormHsmKeyMode, setCreateFormHsmKeyMode] = useState('generate') // 'generate' | 'existing'
  const [createFormHsmKeyLabel, setCreateFormHsmKeyLabel] = useState('')
  const [createFormHsmKeyAlgorithm, setCreateFormHsmKeyAlgorithm] = useState('RSA-3072')
  const [createFormHsmKeyId, setCreateFormHsmKeyId] = useState('')
  const [hsmProviders, setHsmProviders] = useState([])
  const [hsmKeys, setHsmKeys] = useState([])
  const [hsmLoading, setHsmLoading] = useState(false)

  // Load HSM providers when modal opens
  useEffect(() => {
    if (!open) return
    let cancelled = false
    setHsmLoading(true)
    hsmService.getProviders()
      .then(res => {
        if (cancelled) return
        const list = extractData(res) || []
        setHsmProviders(list.filter(p => p.enabled))
      })
      .catch(() => { if (!cancelled) setHsmProviders([]) })
      .finally(() => { if (!cancelled) setHsmLoading(false) })
    return () => { cancelled = true }
  }, [open])

  // Apply RFC 5280 defaults when CA type changes. No EKU on any CA unless
  // asked for: a serverAuth-only issuing CA invalidates every clientAuth
  // leaf beneath it for OpenSSL-based validators (the v2.196 API default).
  useEffect(() => {
    setCreateFormKeyUsage(createFormType === 'root' ? ROOT_KEY_USAGE : INTERMEDIATE_KEY_USAGE)
    setCreateFormEkuServerAuth(false)
  }, [createFormType])

  // Reset form when modal closes
  useEffect(() => {
    if (open) return
    setCreateFormType('root')
    setCreateFormKeyAlgo('RSA')
    setCreateFormKeySize(DEFAULT_KEY_SIZE.RSA)
    setCreateFormDigest('auto')
    setCreateFormSignatureScheme('pkcs1v15')
    setCreateFormProfile(null)
    setCreateFormKeyUsage(ROOT_KEY_USAGE)
    setCreateFormEkuServerAuth(false)
    setShowCertProfile(false)
    setShowAdvanced(false)
    setCreateFormPathLength('')
    setCreateFormNamedUrls(false)
    setCreateFormNCPermitted([])
    setCreateFormNCExcluded([])
    setCreateFormValidity('10')
    setCreateFormValidityDays('')
  }, [open])

  // Reset HSM form state when modal closes
  useEffect(() => {
    if (open) return
    setCreateFormKeyStorage('local')
    setCreateFormHsmProviderId('')
    setCreateFormHsmKeyMode('generate')
    setCreateFormHsmKeyLabel('')
    setCreateFormHsmKeyAlgorithm('RSA-3072')
    setCreateFormHsmKeyId('')
  }, [open])

  // Policies of the parent CA, or the global ones for a root/external CA (#397)
  const policyLimits = useEffectiveAlgorithms({
    caId: createFormType === 'intermediate' ? createFormParentCAId : null,
    enabled: open,
  })

  // Compliance profile: proposed from the parent CA, else the global default
  const profiles = useComplianceProfiles({ enabled: open })
  const defaultProfile = useComplianceDefault({ enabled: open })
  const parentProfile = createFormType === 'intermediate'
    ? (cas || []).find(c => String(c.id) === String(createFormParentCAId))?.compliance_profile
    : null
  const proposedProfile = COMPLIANCE_PROFILE_NAMES.includes(parentProfile) ? parentProfile : defaultProfile
  const profileName = createFormProfile ?? proposedProfile
  const profile = profiles[profileName]
  const { allowedKeyTypes, allowedDigests, allowedSchemes, horizons, requireHsm } =
    useMemo(() => limitsWithProfile(policyLimits, profile), [policyLimits, profile])
  // eu-acm: the CA key lives on an HSM
  const keyStorage = requireHsm ? 'hsm' : createFormKeyStorage
  const fips = policyLimits.fips
  const allowedLocalKeys = useMemo(
    () => CA_KEY_CHOICES.filter(([algo, size]) => isAllowed(allowedKeyTypes, caKeyLabel(algo, size))
      && (!fips || listAlgorithms({ labels: [caKeyLabel(algo, size)], fips: true }).length > 0)),
    [allowedKeyTypes, fips],
  )
  const allowedDigestChoices = useMemo(
    () => POLICY_DIGESTS.filter(d => isAllowed(allowedDigests, d)), [allowedDigests])
  const noKeyAllowed = allowedLocalKeys.length === 0
  const noDigestAllowed = allowedDigestChoices.length === 0
  // 'auto' resolves like the server: the key's own digest when allowed, else the weakest allowed
  const suggested = defaultDigestFor(createFormKeyAlgo, createFormKeySize)
  const autoDigest = allowedDigestChoices.includes(suggested) ? suggested : allowedDigestChoices[0]
  const validityDaysValue = createFormValidity === CUSTOM_VALIDITY
    ? parseInt(createFormValidityDays) : parseInt(createFormValidity) * 365
  // Load HSM signing keys when provider selected and "use existing" mode active
  useEffect(() => {
    if (keyStorage !== 'hsm' || createFormHsmKeyMode !== 'existing' || !createFormHsmProviderId) {
      setHsmKeys([])
      return
    }
    let cancelled = false
    hsmService.getSigningKeys({ providerId: parseInt(createFormHsmProviderId, 10), unused: true })
      .then(res => {
        if (cancelled) return
        setHsmKeys(extractData(res) || [])
      })
      .catch(() => { if (!cancelled) setHsmKeys([]) })
    return () => { cancelled = true }
  }, [keyStorage, createFormHsmKeyMode, createFormHsmProviderId])

  const usesRsa2048 = keyStorage === 'local'
    ? createFormKeyAlgo === 'RSA' && createFormKeySize === '2048'
    : createFormHsmKeyMode === 'generate' && createFormHsmKeyAlgorithm === 'RSA-2048'
  const rsa2048PastHorizon = createFormType !== 'external' && usesRsa2048
    && Number.isFinite(validityDaysValue) && Date.now() + validityDaysValue * 86400000 >= RSA_2048_HORIZON
  const hsmProviderType = hsmProviders.find(p => String(p.id) === createFormHsmProviderId)?.provider_type
  // Brainpool only on a PKCS#11 provider; none shown until a provider is chosen
  const hsmAlgorithms = useMemo(
    () => listAlgorithms({ generate: true, provider: hsmProviderType ?? '', fips })
      .filter(a => isAllowed(allowedKeyTypes, a.label)),
    [allowedKeyTypes, hsmProviderType, fips])
  const hsmAlgorithmOptions = useMemo(() => hsmAlgorithms.map(a => a.label), [hsmAlgorithms])
  const keyIsRsa = keyStorage === 'local'
    ? createFormKeyAlgo === 'RSA'
    : createFormHsmKeyMode === 'generate'
      ? createFormHsmKeyAlgorithm.startsWith('RSA')
      : Boolean(hsmKeys.find(k => String(k.id) === createFormHsmKeyId)?.algorithm?.startsWith('RSA'))
  const pssAvailable = keyIsRsa && (keyStorage === 'local' || PSS_HSM_TYPES.includes(hsmProviderType))
  // The schemes the profile leaves: PSS imposed under bsi
  const schemeChoices = [
    ...(isAllowed(allowedSchemes, 'rsa_pkcs1v15') ? ['pkcs1v15'] : []),
    ...(pssAvailable && isAllowed(allowedSchemes, 'rsa_pss') ? ['pss'] : []),
  ]
  const noSchemeAllowed = keyIsRsa && schemeChoices.length === 0
  const horizonLabel = keyStorage === 'local'
    ? caKeyLabel(createFormKeyAlgo, createFormKeySize)
    : createFormHsmKeyMode === 'generate' ? createFormHsmKeyAlgorithm : null
  const profileHorizon = createFormType !== 'external' ? horizons[horizonLabel] : null
  const pastProfileHorizon = Boolean(profileHorizon) && Number.isFinite(validityDaysValue)
    && Date.now() + validityDaysValue * 86400000 > Date.parse(profileHorizon) + 86400000
  const policyBlocksCreate = noDigestAllowed || noSchemeAllowed || (keyStorage === 'local'
    ? noKeyAllowed
    : createFormHsmKeyMode === 'generate' && hsmAlgorithmOptions.length === 0)

  // A key or digest the policies forbid switches to the first allowed one
  useEffect(() => {
    if (noKeyAllowed) return
    if (allowedLocalKeys.some(([a, sz]) => a === createFormKeyAlgo && sz === createFormKeySize)) return
    const [algo, size] = allowedLocalKeys.find(([a]) => a === createFormKeyAlgo) || allowedLocalKeys[0]
    setCreateFormKeyAlgo(algo)
    setCreateFormKeySize(size)
  }, [allowedLocalKeys, noKeyAllowed, createFormKeyAlgo, createFormKeySize])
  useEffect(() => {
    if (createFormDigest !== 'auto' && !allowedDigestChoices.includes(createFormDigest)) {
      setCreateFormDigest('auto')
    }
  }, [allowedDigestChoices, createFormDigest])
  useEffect(() => {
    if (schemeChoices.length && !schemeChoices.includes(createFormSignatureScheme)) {
      setCreateFormSignatureScheme(schemeChoices[0])
    }
  }, [schemeChoices.join(), createFormSignatureScheme]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (hsmAlgorithmOptions.length && !hsmAlgorithmOptions.includes(createFormHsmKeyAlgorithm)) {
      setCreateFormHsmKeyAlgorithm(hsmAlgorithmOptions[0])
    }
  }, [hsmAlgorithmOptions, createFormHsmKeyAlgorithm])

  const handleCreateCA = async (e) => {
    e.preventDefault()
    if (creatingRef.current) return
    creatingRef.current = true
    setCreating(true)
    try {
      const formData = new FormData(e.target)
      // NameConstraints: drop blank rows, trim values. External-CSR CAs get
      // their constraints from the signing CA, so never send them there.
      const cleanNC = (rows) =>
        rows
          .map((r) => ({ type: r.type, value: (r.value || '').trim() }))
          .filter((r) => r.value)
      const ncPermitted = createFormType === 'external' ? [] : cleanNC(createFormNCPermitted)
      const ncExcluded = createFormType === 'external' ? [] : cleanNC(createFormNCExcluded)
      const data = {
        commonName: formData.get('commonName'),
        organization: formData.get('organization'),
        organizationalUnit: formData.get('organizationalUnit'),
        country: formData.get('country'),
        state: formData.get('state'),
        locality: formData.get('locality'),
        description: formData.get('description'),
        keyAlgo: createFormKeyAlgo,
        keySize: createFormKeyAlgo === 'ECDSA' ? createFormKeySize : parseInt(createFormKeySize),
        type: createFormType,
        // Validity and parent are decided by the external signer in external mode
        ...(createFormType !== 'external' && {
          ...(createFormValidity === CUSTOM_VALIDITY
            ? { validityDays: parseInt(createFormValidityDays) }
            : { validityYears: parseInt(createFormValidity) }),
          parentCAId: createFormType === 'intermediate' ? createFormParentCAId : null,
        }),
        ...(createFormPathLength !== '' && { pathLength: parseInt(createFormPathLength) }),
        namedUrls: createFormNamedUrls,
        hashAlgorithm: createFormDigest,
        ...(pssAvailable && { signatureScheme: createFormSignatureScheme }),
        ...(profileName ? { complianceProfile: profileName } : createFormProfile !== null && { complianceProfile: null }),
        keyUsage: createFormKeyUsage,
        ...(createFormType === 'intermediate' && {
          extendedKeyUsage: createFormEkuServerAuth ? ['serverAuth'] : [],
        }),
        ...(ncPermitted.length && { nameConstraintsPermitted: ncPermitted }),
        ...(ncExcluded.length && { nameConstraintsExcluded: ncExcluded }),
      }

      // HSM key storage — replaces local key fields
      if (keyStorage === 'hsm') {
        if (!createFormHsmProviderId) {
          showError(t('cas.create.hsmProviderRequired'))
          return
        }
        delete data.keyAlgo
        delete data.keySize
        if (createFormHsmKeyMode === 'generate') {
          const label = (createFormHsmKeyLabel || '').trim()
          if (!label) {
            showError(t('cas.create.hsmKeyLabelRequired'))
            return
          }
          if (!/^[a-zA-Z0-9_-]+$/.test(label)) {
            showError(t('cas.create.hsmKeyLabelInvalid'))
            return
          }
          data.hsmProviderId = parseInt(createFormHsmProviderId, 10)
          data.hsmKeyLabel = label
          data.hsmKeyAlgorithm = createFormHsmKeyAlgorithm
        } else {
          if (!createFormHsmKeyId) {
            showError(t('cas.create.hsmExistingKeyRequired'))
            return
          }
          data.hsmKeyId = parseInt(createFormHsmKeyId, 10)
        }
      }

      muteToasts()
      const response = await casService.create(data)
      const created = extractData(response)
      if (created?.pending && created?.csr_pem) {
        // Hand the CSR to the user right away — it goes to the external CA.
        const name = (created.descr || created.common_name || 'ca').replace(/[^a-zA-Z0-9._-]+/g, '_')
        downloadBlob(new Blob([created.csr_pem], { type: 'application/x-pem-file' }), `${name}.csr`)
        showSuccess(t('cas.csrDownloadStarted'))
      } else {
        showSuccess(t('messages.success.create.ca'))
      }
      onClose()
      onSuccess(created)
    } catch (error) {
      showError(error.message || t('cas.createFailed'))
    } finally {
      creatingRef.current = false
      setCreating(false)
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={onClose}
      title={t('common.createCA')}
      size="lg"
    >
      <form onSubmit={handleCreateCA} className="space-y-6 p-4">
        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-text-primary">{t('cas.subjectInfo')}</h3>
          <Input name="commonName" label={t('common.commonName') + ' (CN)'} placeholder={t('cas.cnPlaceholder')} required />
          <div className="grid grid-cols-2 gap-4">
            <Input name="country" label={t('common.country') + ' (C)'} placeholder={t('common.countryPlaceholder')} maxLength={2} />
            <Input name="state" label={t('common.stateProvince') + ' (ST)'} placeholder={t('common.statePlaceholder')} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Input name="locality" label={t('cas.locality') + ' (L)'} placeholder={t('cas.localityPlaceholder')} />
            <Input name="organization" label={t('common.organization') + ' (O)'} placeholder={t('cas.orgPlaceholder')} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Input name="organizationalUnit" label={t('common.orgUnit') + ' (OU)'} placeholder={t('csrs.departmentPlaceholder')} />
            <Input name="description" label={t('common.description')} placeholder={t('cas.descriptionPlaceholder')} />
          </div>
        </div>

        <div className="space-y-2">
          <Select
            label={t('cas.complianceProfile')}
            options={[
              { value: '', label: t('cas.complianceProfileNone') },
              ...COMPLIANCE_PROFILE_NAMES.map(n => ({
                value: n,
                label: profiles[n] ? `${profiles[n].title} (${profiles[n].reference})` : n,
              })),
            ]}
            value={profileName}
            onChange={(value) => setCreateFormProfile(value)}
            helperText={
              createFormProfile === null && profileName
                ? t(COMPLIANCE_PROFILE_NAMES.includes(parentProfile) ? 'cas.complianceProfileFromParent' : 'cas.complianceProfileFromDefault')
                : t('cas.complianceProfileHelp')
            }
          />
          {requireHsm && (
            <p className="text-xs text-text-secondary">{t('cas.create.profileRequiresHsm')}</p>
          )}
        </div>

        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-text-primary">{t('cas.create.keyStorage')}</h3>
          <div className="flex gap-2">
            <label className={cn(
              'flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg border text-sm cursor-pointer transition-all',
              keyStorage === 'local'
                ? 'border-accent-primary bg-accent-primary-op10 text-accent-primary font-semibold'
                : 'border-border hover:border-border-hover text-text-secondary'
            )}>
              <input
                type="radio"
                name="keyStorage"
                value="local"
                className="sr-only"
                checked={keyStorage === 'local'}
                disabled={requireHsm}
                onChange={() => setCreateFormKeyStorage('local')}
              />
              {t('cas.create.keyStorageLocal')}
            </label>
            <label className={cn(
              'flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg border text-sm cursor-pointer transition-all',
              keyStorage === 'hsm'
                ? 'border-accent-primary bg-accent-primary-op10 text-accent-primary font-semibold'
                : 'border-border hover:border-border-hover text-text-secondary'
            )}>
              <input
                type="radio"
                name="keyStorage"
                value="hsm"
                className="sr-only"
                checked={keyStorage === 'hsm'}
                onChange={() => setCreateFormKeyStorage('hsm')}
              />
              {t('cas.create.keyStorageHsm')}
            </label>
          </div>
        </div>

        {keyStorage === 'local' && (
        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-text-primary">{t('cas.keyConfiguration')}</h3>
          <div className="grid grid-cols-2 gap-4">
            <Select
              label={t('common.keyAlgorithm')}
              options={[
                { value: 'RSA', label: 'RSA' },
                { value: 'ECDSA', label: 'ECDSA' }
              ].filter(o => noKeyAllowed || allowedLocalKeys.some(([a]) => a === o.value))}
              value={createFormKeyAlgo}
              onChange={(value) => {
                setCreateFormKeyAlgo(value)
                const sizes = allowedLocalKeys.filter(([a]) => a === value).map(([, sz]) => sz)
                setCreateFormKeySize(sizes.includes(DEFAULT_KEY_SIZE[value])
                  ? DEFAULT_KEY_SIZE[value] : sizes[0] || DEFAULT_KEY_SIZE[value])
              }}
            />
            <Select
              label={t('common.keySize')}
              options={(createFormKeyAlgo === 'ECDSA'
                ? groupedOptions(EC_CA_ALGORITHMS, t, k => k.display, k => k.ca[1])
                : [
                  { value: '2048', label: '2048 bits' },
                  { value: '3072', label: '3072 bits' },
                  { value: '4096', label: '4096 bits' }
                ]).filter(o => noKeyAllowed || allowedLocalKeys.some(([a, sz]) => a === createFormKeyAlgo && sz === o.value))}
              value={createFormKeySize}
              onChange={(value) => setCreateFormKeySize(value)}
            />
            <Select
              label={t('common.signatureAlgorithm')}
              options={[
                ...(noDigestAllowed ? [] : [{ value: 'auto', label: t('cas.create.digestAuto') }]),
                ...allowedDigestChoices.map(d => ({ value: d, label: d.toUpperCase().replace('SHA', 'SHA-') })),
              ]}
              value={createFormDigest}
              onChange={(value) => setCreateFormDigest(value)}
              helperText={
                createFormDigest === 'auto' && autoDigest
                  ? t('cas.create.digestAutoHint', { digest: autoDigest.toUpperCase() })
                  : undefined
              }
            />
          </div>
          {noKeyAllowed && (
            <p className="text-xs text-status-danger" role="alert">{t('cas.create.noKeyTypeAllowedByPolicy')}</p>
          )}
        </div>
        )}
        {noSchemeAllowed && (
          <p className="text-xs text-status-danger" role="alert">{t('cas.create.noSchemeAllowedByProfile')}</p>
        )}
        {noDigestAllowed && (
          <p className="text-xs text-status-danger" role="alert">{t('cas.create.noDigestAllowedByPolicy')}</p>
        )}
        {createFormType !== 'external' && <BrainpoolNotice label={horizonLabel} />}
        {pastProfileHorizon && (
          <div className="px-3 py-2 rounded-lg border border-status-warning bg-status-warning-op10 text-xs text-status-warning">
            {t('cas.create.profileHorizon', { key: horizonLabel, date: profileHorizon })}
          </div>
        )}
        {rsa2048PastHorizon && (
          <div className="px-3 py-2 rounded-lg border border-status-warning bg-status-warning-op10 text-xs text-status-warning">
            {t('cas.create.rsa2048Horizon')}
          </div>
        )}

        {keyStorage === 'hsm' && (
        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-text-primary">{t('cas.keyConfiguration')}</h3>
          {!hsmLoading && hsmProviders.length === 0 ? (
            <div className="px-3 py-2 rounded-lg border border-status-warning bg-status-warning-op10 text-xs text-status-warning">
              {t('cas.create.hsmNoProviders')}
            </div>
          ) : (
            <>
              <Select
                label={t('cas.create.hsmProvider')}
                options={hsmProviders.map(p => ({
                  value: p.id.toString(),
                  label: `${p.name} (${p.provider_type})`
                }))}
                value={createFormHsmProviderId}
                onChange={(v) => { setCreateFormHsmProviderId(v); setCreateFormHsmKeyId('') }}
                required
              />
              <div>
                <label className="block text-xs font-medium text-text-secondary mb-1.5">
                  {t('cas.create.hsmKeyMode')}
                </label>
                <div className="flex gap-2">
                  <label className={cn(
                    'flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg border text-sm cursor-pointer transition-all',
                    createFormHsmKeyMode === 'generate'
                      ? 'border-accent-primary bg-accent-primary-op10 text-accent-primary font-semibold'
                      : 'border-border hover:border-border-hover text-text-secondary'
                  )}>
                    <input
                      type="radio"
                      name="hsmKeyMode"
                      value="generate"
                      className="sr-only"
                      checked={createFormHsmKeyMode === 'generate'}
                      onChange={() => setCreateFormHsmKeyMode('generate')}
                    />
                    {t('cas.create.hsmKeyModeGenerate')}
                  </label>
                  <label className={cn(
                    'flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg border text-sm cursor-pointer transition-all',
                    createFormHsmKeyMode === 'existing'
                      ? 'border-accent-primary bg-accent-primary-op10 text-accent-primary font-semibold'
                      : 'border-border hover:border-border-hover text-text-secondary'
                  )}>
                    <input
                      type="radio"
                      name="hsmKeyMode"
                      value="existing"
                      className="sr-only"
                      checked={createFormHsmKeyMode === 'existing'}
                      onChange={() => setCreateFormHsmKeyMode('existing')}
                    />
                    {t('cas.create.hsmKeyModeExisting')}
                  </label>
                </div>
              </div>

              {createFormHsmKeyMode === 'generate' && (
                <div className="grid grid-cols-2 gap-4">
                  <Input
                    label={t('cas.create.hsmKeyLabel')}
                    value={createFormHsmKeyLabel}
                    onChange={(e) => setCreateFormHsmKeyLabel(e.target.value)}
                    placeholder="ca-signing-key-1"
                    helperText={t('cas.create.hsmKeyLabelHelp')}
                    required
                  />
                  <Select
                    label={t('cas.create.hsmKeyAlgorithm')}
                    options={groupedOptions(hsmAlgorithms, t, a => a.label)}
                    value={createFormHsmKeyAlgorithm}
                    onChange={(v) => setCreateFormHsmKeyAlgorithm(v)}
                  />
                </div>
              )}
              {createFormHsmKeyMode === 'generate' && hsmAlgorithmOptions.length === 0 && (
                <p className="text-xs text-status-danger" role="alert">{t('cas.create.noKeyTypeAllowedByPolicy')}</p>
              )}

              {createFormHsmKeyMode === 'existing' && (
                createFormHsmProviderId && hsmKeys.length === 0 ? (
                  <div className="px-3 py-2 rounded-lg border border-status-warning bg-status-warning-op10 text-xs text-status-warning">
                    {t('cas.create.hsmNoUnusedKeys')}
                  </div>
                ) : (
                  <Select
                    label={t('cas.create.hsmExistingKey')}
                    options={hsmKeys.map(k => ({
                      value: k.id.toString(),
                      label: `${k.label} (${k.algorithm})`
                    }))}
                    value={createFormHsmKeyId}
                    onChange={(v) => setCreateFormHsmKeyId(v)}
                    required
                  />
                )
              )}
            </>
          )}
        </div>
        )}

        {keyIsRsa && (
          <Select
            label={t('cas.signatureScheme')}
            options={schemeChoices.map(v => ({
              value: v, label: t(v === 'pss' ? 'cas.signatureSchemePss' : 'cas.signatureSchemePkcs1v15'),
            }))}
            value={createFormSignatureScheme}
            onChange={(value) => setCreateFormSignatureScheme(value)}
            helperText={pssAvailable ? t('cas.signatureSchemeHelp') : t('cas.signatureSchemeHsmUnsupported')}
          />
        )}

        {createFormType !== 'external' && (
          <div className="space-y-4">
            <Select
              label={t('common.validityPeriod')}
              options={[
                ...VALIDITY_YEAR_PRESETS.map(years => ({
                  value: String(years), label: t('cas.yearsValidity', { count: years }),
                })),
                { value: CUSTOM_VALIDITY, label: t('cas.customValidityDays') },
              ]}
              value={createFormValidity}
              onChange={(value) => setCreateFormValidity(value)}
            />
            {createFormValidity === CUSTOM_VALIDITY && (
              <Input
                name="validityDays"
                type="number"
                min={1}
                max={MAX_CA_VALIDITY_DAYS}
                required
                label={t('cas.validityDays')}
                value={createFormValidityDays}
                onChange={(e) => setCreateFormValidityDays(e.target.value)}
                helperText={t('cas.validityDaysHelp', { max: MAX_CA_VALIDITY_DAYS })}
              />
            )}
          </div>
        )}

        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-text-primary">{t('cas.caType')}</h3>
          <Select
            label={t('common.type')}
            options={[
              { value: 'root', label: t('cas.rootCASelfSigned') },
              { value: 'intermediate', label: t('cas.intermediateCASigned') },
              { value: 'external', label: t('cas.externalCASigned') }
            ]}
            value={createFormType}
            onChange={(value) => setCreateFormType(value)}
          />
          {createFormType === 'external' && (
            <p className="text-xs text-text-secondary">{t('cas.create.externalHint')}</p>
          )}
          {createFormType === 'intermediate' && (
            <Select
              label={t('cas.parentCA')}
              options={signingCas(cas).map(ca => ({
                value: ca.id.toString(),
                label: ca.name || ca.descr || ca.common_name
              }))}
              value={createFormParentCAId}
              onChange={(value) => setCreateFormParentCAId(value)}
              required
            />
          )}
        </div>

        {/* Certificate profile (RFC 5280 Key Usage / EKU) */}
        <div className="space-y-4">
          <button
            type="button"
            className="flex items-center gap-2 text-sm font-semibold text-text-secondary hover:text-text-primary transition-colors"
            onClick={() => setShowCertProfile(!showCertProfile)}
          >
            {showCertProfile ? <CaretDown size={14} /> : <CaretRight size={14} />}
            {t('cas.create.certificateProfile')}
          </button>
          {showCertProfile && (
            <div className="space-y-4 pl-2 border-l-2 border-border">
              <p className="text-xs text-text-secondary">{t('cas.create.certificateProfileHelp')}</p>
              <fieldset className="space-y-2">
                <legend className="text-xs font-medium text-text-secondary">{t('common.keyUsage')}</legend>
                {CA_KU_OPTIONS.map((ku) => (
                  <label key={ku} className="flex items-center gap-2 text-sm text-text-primary cursor-pointer">
                    <input
                      type="checkbox"
                      className="rounded border-border"
                      checked={createFormKeyUsage.includes(ku)}
                      onChange={(e) => {
                        setCreateFormKeyUsage((prev) => {
                          if (e.target.checked) {
                            return prev.includes(ku) ? prev : [...prev, ku]
                          }
                          return prev.filter((x) => x !== ku)
                        })
                      }}
                    />
                    {ku}
                  </label>
                ))}
              </fieldset>
              {createFormType === 'intermediate' && (
                <label className="flex items-center gap-2 text-sm text-text-primary cursor-pointer">
                  <input
                    type="checkbox"
                    className="rounded border-border"
                    checked={createFormEkuServerAuth}
                    onChange={(e) => setCreateFormEkuServerAuth(e.target.checked)}
                  />
                  {t('cas.create.ekuServerAuth')}
                </label>
              )}
            </div>
          )}
        </div>

        {/* Advanced Constraints (RFC 5280) */}
        <div className="space-y-4">
          <button
            type="button"
            className="flex items-center gap-2 text-sm font-semibold text-text-secondary hover:text-text-primary transition-colors"
            onClick={() => setShowAdvanced(!showAdvanced)}
          >
            {showAdvanced ? <CaretDown size={14} /> : <CaretRight size={14} />}
            {t('cas.advancedConstraints')}
          </button>
          {showAdvanced && (
            <div className="space-y-4 pl-2 border-l-2 border-border">
              <Input
                label={t('cas.pathLength')}
                type="number"
                min="0"
                value={createFormPathLength}
                onChange={(e) => setCreateFormPathLength(e.target.value)}
                placeholder={t('cas.pathLengthPlaceholder')}
              />
              {createFormType === 'external' ? (
                <p className="text-xs text-text-tertiary">{t('cas.nameConstraintsExternalNote')}</p>
              ) : (
                <>
                  <NameConstraintRows
                    label={t('cas.nameConstraintsPermitted')}
                    hint={t('cas.nameConstraintsPermittedHint')}
                    addLabel={t('cas.nameConstraintAddPermitted')}
                    rows={createFormNCPermitted}
                    onChange={setCreateFormNCPermitted}
                  />
                  <NameConstraintRows
                    label={t('cas.nameConstraintsExcluded')}
                    hint={t('cas.nameConstraintsExcludedHint')}
                    addLabel={t('cas.nameConstraintAddExcluded')}
                    rows={createFormNCExcluded}
                    onChange={setCreateFormNCExcluded}
                  />
                </>
              )}
              <label className="flex items-start gap-2 text-sm text-text-secondary cursor-pointer">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={createFormNamedUrls}
                  onChange={(e) => setCreateFormNamedUrls(e.target.checked)}
                />
                <span>
                  {t('cas.namedUrls')}
                  <span className="block text-xs text-text-tertiary">{t('cas.namedUrlsHint')}</span>
                </span>
              </label>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 pt-4 border-t border-border">
          <Button type="button" variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            type="submit"
            disabled={
              creating || policyBlocksCreate || (
              keyStorage === 'hsm' && (
                hsmProviders.length === 0 ||
                (createFormHsmKeyMode === 'existing' && !!createFormHsmProviderId && hsmKeys.length === 0)
              )
              )
            }
          >
            {creating ? t('common.creating') : t('common.createCA')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
