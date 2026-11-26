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
import { AtelierDialog, Icon } from '../../components/atelier'
import { casService, hsmService } from '../../services'
import { useNotification } from '../../contexts'
import { useWebSocket } from '../../hooks'
import { extractData, downloadBlob } from '../../lib/utils'
import { signingCas, unlistedSigningCas } from '../../lib/caSelection'
import { CA_KEY_CHOICES, POLICY_DIGESTS, caKeyLabel, isAllowed, useEffectiveAlgorithms } from '../../lib/policyAlgorithms'
import { PSS_HSM_TYPES } from '../../lib/signatureName'
import {
  CA_DEFAULT_LABELS, KEY_ALGORITHMS, algorithmForKeyType, algorithmName, defaultDigestFor, defaultKeyChoice, findAlgorithm,
  groupedOptions, isBrainpool, isPostQuantum, isUntestedOn, isUsable, keyFamilyOptions, listAlgorithms,
} from '../../lib/keyAlgorithms'
import { COMPLIANCE_PROFILE_NAMES, limitsWithProfile, useComplianceDefault, useComplianceProfiles } from '../../lib/complianceProfiles'

const CA_FAMILY_OPTIONS = keyFamilyOptions('ca')
const [DEFAULT_KEY_ALGO, DEFAULT_KEY_SIZE] = findAlgorithm(CA_DEFAULT_LABELS[0]).ca
const VALIDITY_YEAR_PRESETS = [1, 2, 3, 5, 10, 15, 20]
const CUSTOM_VALIDITY = 'custom'
// ANSSI PG-083 accepts RSA below 3072 bits until the end of 2030, ETSI TS 119 312 until the end of 2026
const SHORT_RSA_BITS = 3072
const SHORT_RSA_HORIZON = Date.UTC(2031, 0, 1)
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
/** Consecutive options of one key group (groupedOptions) as one optgroup, the others as they are. */
function groupRuns(options) {
  const runs = []
  for (const o of options) {
    const last = runs[runs.length - 1]
    if (last && last.group === o.group) last.options.push(o)
    else runs.push({ group: o.group, options: [o] })
  }
  return runs
}

function NameConstraintRows({ id, label, hint, addLabel, rows, onChange }) {
  const { t } = useTranslation()
  const update = (idx, key, val) =>
    onChange(rows.map((r, i) => (i === idx ? { ...r, [key]: val } : r)))
  const add = () => onChange([...rows, { type: 'dns', value: '' }])
  const remove = (idx) => onChange(rows.filter((_, i) => i !== idx))

  // The mockup's SAN rows of the issue form: type, value, remove; then « Ajouter »
  return (
    <fieldset className="field full">
      <legend>{label}</legend>
      {hint && <small id={`hint-${id}`}>{hint}</small>}
      <div className="row-list">
        {rows.map((row, idx) => (
          <div key={idx} className="san-row">
            <label className="sr-only" htmlFor={`${id}-type-${idx}`}>{t('cas.create.constraintType', { n: idx + 1 })}</label>
            <select id={`${id}-type-${idx}`} value={row.type} onChange={(e) => update(idx, 'type', e.target.value)}>
              {NC_TYPE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{t(o.labelKey)}</option>)}
            </select>
            <label className="sr-only" htmlFor={`${id}-value-${idx}`}>{t('cas.create.constraintValue', { n: idx + 1 })}</label>
            <input id={`${id}-value-${idx}`} placeholder={t('cas.nameConstraintValuePlaceholder')} value={row.value}
              autoComplete="off" spellCheck={false} onChange={(e) => update(idx, 'value', e.target.value)} />
            <button type="button" className="icon-btn" aria-label={t('common.remove')} onClick={() => remove(idx)}><Icon name="close" /></button>
          </div>
        ))}
      </div>
      <button type="button" className="btn quiet add-row" onClick={add}><Icon name="plus" />{addLabel}</button>
    </fieldset>
  )
}

export function CreateCAModal({ open, onClose, cas, onSuccess }) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const { muteToasts } = useWebSocket()

  const [createFormType, setCreateFormType] = useState('root')
  const [createFormParentCAId, setCreateFormParentCAId] = useState(null)
  const [createFormKeyAlgo, setCreateFormKeyAlgo] = useState(DEFAULT_KEY_ALGO)
  const [createFormKeySize, setCreateFormKeySize] = useState(DEFAULT_KEY_SIZE)
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
  const [createFormHsmKeyAlgorithm, setCreateFormHsmKeyAlgorithm] = useState(CA_DEFAULT_LABELS[0])
  const [createFormHsmKeyId, setCreateFormHsmKeyId] = useState('')
  const [hsmProviders, setHsmProviders] = useState([])
  const [hsmKeys, setHsmKeys] = useState([])
  const [hsmLoading, setHsmLoading] = useState(false)
  // The server refused the HSM list (no read:hsm) or the creation on the chosen key (403, 409)
  const [hsmDenied, setHsmDenied] = useState(false)
  const [hsmRefusal, setHsmRefusal] = useState('')

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
        setHsmDenied(false)
      })
      .catch((error) => {
        if (cancelled) return
        setHsmProviders([])
        setHsmDenied(error?.status === 403)
      })
      .finally(() => { if (!cancelled) setHsmLoading(false) })
    return () => { cancelled = true }
  }, [open])

  // A refusal belongs to the key that was tried
  useEffect(() => { setHsmRefusal('') },
    [createFormHsmKeyId, createFormHsmProviderId, createFormHsmKeyMode, createFormKeyStorage])

  // Reset form when modal closes
  useEffect(() => {
    if (open) return
    setCreateFormType('root')
    setCreateFormKeyAlgo(DEFAULT_KEY_ALGO)
    setCreateFormKeySize(DEFAULT_KEY_SIZE)
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
    setCreateFormHsmKeyAlgorithm(CA_DEFAULT_LABELS[0])
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
  const { allowedKeyTypes, allowedDigests, allowedSchemes, horizons, requireHsm, pqStandalone } =
    useMemo(() => limitsWithProfile(policyLimits, profile), [policyLimits, profile])
  // eu-acm: the CA key lives on an HSM
  const keyStorage = requireHsm ? 'hsm' : createFormKeyStorage

  // Apply RFC 5280 defaults when CA type changes. No EKU on any CA unless
  // asked for: a serverAuth-only issuing CA invalidates every clientAuth
  // leaf beneath it for OpenSSL-based validators (the v2.196 API default).
  // An ML-DSA root keeps digitalSignature, as the API gives it by default (RFC 9881).
  // The new CA's key: the local choice, the HSM key to generate, or the existing one picked
  const keyLabel = keyStorage === 'local'
    ? caKeyLabel(createFormKeyAlgo, createFormKeySize)
    : createFormHsmKeyMode === 'generate'
      ? createFormHsmKeyAlgorithm
      : hsmKeys.find(k => String(k.id) === createFormHsmKeyId)?.algorithm
  const keyRow = findAlgorithm(keyLabel)
  const mldsaKey = keyRow?.family === 'ML-DSA'
  useEffect(() => {
    setCreateFormKeyUsage(createFormType === 'root' && !mldsaKey ? ROOT_KEY_USAGE : INTERMEDIATE_KEY_USAGE)
    setCreateFormEkuServerAuth(false)
  }, [createFormType, mldsaKey])
  const { fips, fipsKeys, mldsa } = policyLimits
  const allowedLocalKeys = useMemo(
    () => CA_KEY_CHOICES.filter(([algo, size]) => isAllowed(allowedKeyTypes, caKeyLabel(algo, size))
      && isUsable(findAlgorithm(caKeyLabel(algo, size)), { fips, fipsKeys, mldsa })
      && !(pqStandalone && isPostQuantum(caKeyLabel(algo, size)))),
    [allowedKeyTypes, fips, fipsKeys, mldsa, pqStandalone],
  )
  const allowedDigestChoices = useMemo(
    () => POLICY_DIGESTS.filter(d => isAllowed(allowedDigests, d)), [allowedDigests])
  const noKeyAllowed = allowedLocalKeys.length === 0
  // The parent signs an intermediate: its key decides whether a digest applies (ML-DSA takes none)
  const parentKeyType = createFormType === 'intermediate'
    ? (cas || []).find(c => String(c.id) === String(createFormParentCAId))?.key_type
    : null
  const parentKeyRow = algorithmForKeyType(parentKeyType)
  // A key outside the registry (an HSM's RSA-8192) takes a digest
  const childHasDigest = keyRow?.digest !== null
  // A parent key outside the registry (RSA-8192) takes a digest, as on the server
  const keyHasDigest = parentKeyType ? parentKeyRow?.digest !== null : childHasDigest
  const noDigestAllowed = keyHasDigest && allowedDigestChoices.length === 0
  // 'auto' resolves like the server: the child key's digest, the parent's when the child takes none
  const suggested = (childHasDigest ? null : parentKeyRow?.digest)
    || defaultDigestFor(createFormKeyAlgo, createFormKeySize)
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

  const horizonLabel = keyStorage === 'local'
    ? caKeyLabel(createFormKeyAlgo, createFormKeySize)
    : createFormHsmKeyMode === 'generate' ? createFormHsmKeyAlgorithm : null
  const horizonRow = findAlgorithm(horizonLabel)
  const usesShortRsa = horizonRow?.family === 'RSA' && horizonRow.bits < SHORT_RSA_BITS
  const rsa2048PastHorizon = createFormType !== 'external' && usesShortRsa
    && Number.isFinite(validityDaysValue) && Date.now() + validityDaysValue * 86400000 >= SHORT_RSA_HORIZON
  const hsmProviderType = hsmProviders.find(p => String(p.id) === createFormHsmProviderId)?.provider_type
  // Brainpool only on a PKCS#11 provider; none shown until a provider is chosen. An HSM key
  // signs outside the loaded module: in FIPS mode only what every module approves (no fipsKeys)
  const hsmAlgorithms = useMemo(
    () => listAlgorithms({ generate: true, provider: hsmProviderType ?? '', fips, mldsa })
      .filter(a => isAllowed(allowedKeyTypes, a.label) && !(pqStandalone && isPostQuantum(a.label))),
    [allowedKeyTypes, hsmProviderType, fips, mldsa, pqStandalone])
  const hsmAlgorithmOptions = useMemo(() => hsmAlgorithms.map(a => a.label), [hsmAlgorithms])
  // Existing keys pass the same filters; one outside the registry (RSA-8192) is refused only in FIPS mode
  const usableHsmKeys = useMemo(() => hsmKeys.filter(k => {
    const row = findAlgorithm(k.algorithm)
    return isAllowed(allowedKeyTypes, k.algorithm) && (row ? isUsable(row, { fips, mldsa }) : !fips)
      && !(pqStandalone && isPostQuantum(k.algorithm))
  }), [hsmKeys, allowedKeyTypes, fips, mldsa, pqStandalone])
  // An HSM key synced from the token may be an RSA size the registry does not list ('RSA-8192')
  const keyIsRsa = keyRow?.family === 'RSA' || /^RSA-\d+$/.test(keyLabel ?? '')
  const pssAvailable = keyIsRsa && (keyStorage === 'local' || PSS_HSM_TYPES.includes(hsmProviderType))
  // The schemes the profile leaves: PSS imposed under bsi
  const schemeChoices = [
    ...(isAllowed(allowedSchemes, 'rsa_pkcs1v15') ? ['pkcs1v15'] : []),
    ...(pssAvailable && isAllowed(allowedSchemes, 'rsa_pss') ? ['pss'] : []),
  ]
  const noSchemeAllowed = keyIsRsa && schemeChoices.length === 0
  const profileHorizon = createFormType !== 'external' ? horizons[horizonLabel] : null
  const pastProfileHorizon = Boolean(profileHorizon) && Number.isFinite(validityDaysValue)
    && Date.now() + validityDaysValue * 86400000 > Date.parse(profileHorizon) + 86400000
  // An intermediate is signed by a parent: without one the server refuses it
  const missingParent = createFormType === 'intermediate' && !createFormParentCAId
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
  useEffect(() => {
    if (createFormHsmKeyId && !usableHsmKeys.some(k => String(k.id) === createFormHsmKeyId)) {
      setCreateFormHsmKeyId('')
    }
  }, [usableHsmKeys, createFormHsmKeyId])

  const handleCreateCA = async (e) => {
    e.preventDefault()
    if (creatingRef.current || missingParent) return
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
        // RSA bits and ML-DSA levels are numbers, curves are names
        keySize: /^\d+$/.test(createFormKeySize) ? parseInt(createFormKeySize, 10) : createFormKeySize,
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
        ...(keyHasDigest && { hashAlgorithm: createFormDigest }),
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

      setHsmRefusal('')
      muteToasts()
      const response = await casService.create(data)
      const created = extractData(response)
      if (created?.pending && created?.csr_pem) {
        // Hand the CSR to the user right away — it goes to the external CA.
        const name = created.descr || created.common_name || 'ca'
        downloadBlob(new Blob([created.csr_pem], { type: 'application/x-pem-file' }), `${name}.csr`)
        showSuccess(t('cas.csrDownloadStarted'))
      } else {
        showSuccess(t('messages.success.create.ca'))
      }
      onClose()
      onSuccess(created)
    } catch (error) {
      showError(error.message || t('cas.createFailed'))
      if (keyStorage === 'hsm' && (error?.status === 403 || error?.status === 409)) {
        setHsmRefusal(error.message || t('cas.createFailed'))
      }
    } finally {
      creatingRef.current = false
      setCreating(false)
    }
  }

  const field = (id, label, control, hint) => (
    <div className={hint?.full ? 'field full' : 'field'}>
      <label htmlFor={id}>{label}</label>
      {control}
      {hint?.text && <small id={`hint-${id}`}>{hint.text}</small>}
    </div>
  )
  const select = (id, value, onChange, options, extra = {}) => (
    <select id={id} value={value ?? ''} onChange={(e) => onChange(e.target.value)} {...extra}>
      {extra.required && !value && <option value="" disabled hidden>{t('cas.create.choose')}</option>}
      {groupRuns(options).map((run) => (run.group
        ? <optgroup key={run.group} label={run.group}>{run.options.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}</optgroup>
        : run.options.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)))}
    </select>
  )
  const warn = (text, role = 'note') => <p className="notice warn" role={role}><Icon name="warning" /><span>{text}</span></p>
  const refuse = (text) => <p className="field-error" role="alert"><Icon name="warning" /><span>{text}</span></p>
  const radio = (name, value, current, onChange, label, { disabled = false, hint } = {}) => (
    <label className="format-option">
      <input type="radio" name={name} value={value} checked={current === value} disabled={disabled} onChange={() => onChange(value)} />
      <span>{label}{hint && <small>{hint}</small>}</span>
    </label>
  )
  const toggle = (id, open, onToggle, label, sub) => (
    <button type="button" className="advanced-toggle" id={`${id}-toggle`} aria-expanded={open} aria-controls={id} onClick={onToggle}>
      <Icon name={open ? 'down' : 'right'} /><span>{label}</span>{sub && <small>{sub}</small>}
    </button>
  )
  const parentHint = unlistedSigningCas(cas) > 0 ? t('cas.notListedForSigning', { count: unlistedSigningCas(cas) }) : undefined
  const profileHint = createFormProfile === null && profileName
    ? t(COMPLIANCE_PROFILE_NAMES.includes(parentProfile) ? 'cas.complianceProfileFromParent' : 'cas.complianceProfileFromDefault')
    : t('cas.complianceProfileHelp')

  if (!open) return null
  // The mockup's setupDialog(): a modal holding a form of `.form-fields`, then Annuler and the primary action
  return (
    <AtelierDialog title={t('cas.create.title')} onClose={onClose} testId="create-ca-dialog">
      <form id="create-ca-form" onSubmit={handleCreateCA}>
        <div className="form-fields">
          {field('ca-type', t('common.type'), select('ca-type', createFormType, setCreateFormType, [
            { value: 'root', label: t('cas.rootCASelfSigned') },
            { value: 'intermediate', label: t('cas.intermediateCASigned') },
            { value: 'external', label: t('cas.externalCASigned') },
          ]), { text: createFormType === 'external' ? t('cas.create.externalHint') : undefined })}
          {createFormType === 'intermediate' && field('ca-parent', t('cas.parentCA'), select('ca-parent', createFormParentCAId, setCreateFormParentCAId,
            signingCas(cas).map((ca) => ({ value: ca.id.toString(), label: ca.name || ca.descr || ca.common_name })), { required: true, 'aria-describedby': parentHint ? 'hint-ca-parent' : undefined }),
          { text: parentHint })}

          <div className="field full">
            <label htmlFor="ca-cn">{t('common.commonName') + ' (CN)'}</label>
            <input id="ca-cn" name="commonName" placeholder={t('cas.cnPlaceholder')} required maxLength={64} autoComplete="off" />
          </div>
          {field('ca-country', t('common.country') + ' (C)', <input id="ca-country" name="country" placeholder={t('common.countryPlaceholder')} maxLength={2} autoComplete="off" />)}
          {field('ca-state', t('common.stateProvince') + ' (ST)', <input id="ca-state" name="state" placeholder={t('common.statePlaceholder')} autoComplete="off" />)}
          {field('ca-locality', t('cas.locality') + ' (L)', <input id="ca-locality" name="locality" placeholder={t('cas.localityPlaceholder')} autoComplete="off" />)}
          {field('ca-organization', t('common.organization') + ' (O)', <input id="ca-organization" name="organization" placeholder={t('cas.orgPlaceholder')} autoComplete="off" />)}
          {field('ca-ou', t('common.orgUnit') + ' (OU)', <input id="ca-ou" name="organizationalUnit" placeholder={t('csrs.departmentPlaceholder')} autoComplete="off" />)}
          {field('ca-description', t('cas.label.displayName'), <input id="ca-description" name="description" placeholder={t('cas.label.displayNamePlaceholder')} maxLength={255} autoComplete="off" />)}

          {field('ca-profile', t('cas.complianceProfile'), select('ca-profile', profileName, (v) => setCreateFormProfile(v), [
            { value: '', label: t('cas.complianceProfileNone') },
            ...COMPLIANCE_PROFILE_NAMES.map((n) => ({ value: n, label: profiles[n] ? `${profiles[n].title} (${profiles[n].reference})` : n })),
          ], { 'aria-describedby': 'hint-ca-profile' }), { full: true, text: profileHint })}
          {requireHsm && warn(t('cas.create.profileRequiresHsm'))}

          <fieldset className="field full">
            <legend>{t('cas.create.keyStorage')}</legend>
            <div className="choice-grid">
              {radio('keyStorage', 'local', keyStorage, setCreateFormKeyStorage, t('cas.create.keyStorageLocal'), { disabled: requireHsm })}
              {radio('keyStorage', 'hsm', keyStorage, setCreateFormKeyStorage, t('cas.create.keyStorageHsm'), { disabled: hsmDenied })}
            </div>
            {hsmDenied && <small>{t('cas.create.hsmNeedsRead')}</small>}
          </fieldset>

          {keyStorage === 'local' && (
            <>
              {field('ca-key-algo', t('common.keyAlgorithm'), select('ca-key-algo', createFormKeyAlgo, (value) => {
                setCreateFormKeyAlgo(value)
                const sizes = allowedLocalKeys.filter(([a]) => a === value).map(([, sz]) => sz)
                const preferred = defaultKeyChoice('ca', value, CA_DEFAULT_LABELS)?.[1]
                setCreateFormKeySize(sizes.includes(preferred) ? preferred : sizes[0] || preferred)
              }, CA_FAMILY_OPTIONS.filter((o) => noKeyAllowed || allowedLocalKeys.some(([a]) => a === o.value))))}
              {field('ca-key-size', t('common.keySize'), select('ca-key-size', createFormKeySize, (value) => setCreateFormKeySize(value),
                groupedOptions(
                  KEY_ALGORITHMS.filter((k) => k.ca && k.ca[0] === createFormKeyAlgo), t,
                  (k) => algorithmName(k, t, 'sizeKey'), (k) => k.ca[1],
                ).filter((o) => noKeyAllowed || allowedLocalKeys.some(([a, sz]) => a === createFormKeyAlgo && sz === o.value))))}
              {keyHasDigest && field('ca-digest', t('common.signatureAlgorithm'), select('ca-digest', createFormDigest, (value) => setCreateFormDigest(value), [
                ...(noDigestAllowed ? [] : [{ value: 'auto', label: t('cas.create.digestAuto') }]),
                ...allowedDigestChoices.map((d) => ({ value: d, label: d.toUpperCase().replace('SHA', 'SHA-') })),
              ]), { text: createFormDigest === 'auto' && autoDigest ? t('cas.create.digestAutoHint', { digest: autoDigest.toUpperCase() }) : undefined })}
              {noKeyAllowed && refuse(t('cas.create.noKeyTypeAllowedByPolicy'))}
            </>
          )}
          {noSchemeAllowed && refuse(t('cas.create.noSchemeAllowedByProfile'))}
          {noDigestAllowed && refuse(t('cas.create.noDigestAllowedByPolicy'))}
          {createFormType !== 'external' && isBrainpool(horizonLabel) && warn(t('common.keyGroups.brainpoolWarning'))}
          {pastProfileHorizon && warn(t('cas.create.profileHorizon', { key: horizonLabel, date: profileHorizon }), undefined)}
          {rsa2048PastHorizon && warn(t('cas.create.rsa2048Horizon'), undefined)}

          {keyStorage === 'hsm' && (
            !hsmLoading && hsmProviders.length === 0 ? warn(t('cas.create.hsmNoProviders'), undefined) : (
              <>
                {field('ca-hsm-provider', t('cas.create.hsmProvider'), select('ca-hsm-provider', createFormHsmProviderId,
                  (v) => { setCreateFormHsmProviderId(v); setCreateFormHsmKeyId('') },
                  hsmProviders.map((p) => ({ value: p.id.toString(), label: `${p.name} (${p.provider_type})` })), { required: true }))}
                <fieldset className="field">
                  <legend>{t('cas.create.hsmKeyMode')}</legend>
                  <div className="choice-grid">
                    {radio('hsmKeyMode', 'generate', createFormHsmKeyMode, setCreateFormHsmKeyMode, t('cas.create.hsmKeyModeGenerate'))}
                    {radio('hsmKeyMode', 'existing', createFormHsmKeyMode, setCreateFormHsmKeyMode, t('cas.create.hsmKeyModeExisting'))}
                  </div>
                </fieldset>
                {createFormHsmKeyMode === 'generate' && (
                  <>
                    {field('ca-hsm-label', t('cas.create.hsmKeyLabel'), <input id="ca-hsm-label" value={createFormHsmKeyLabel} required placeholder="ca-signing-key-1"
                      aria-describedby="hint-ca-hsm-label" onChange={(e) => setCreateFormHsmKeyLabel(e.target.value)} />, { text: t('cas.create.hsmKeyLabelHelp') })}
                    {field('ca-hsm-algo', t('cas.create.hsmKeyAlgorithm'), select('ca-hsm-algo', createFormHsmKeyAlgorithm, (v) => setCreateFormHsmKeyAlgorithm(v),
                      groupedOptions(hsmAlgorithms, t, (a) => a.label)))}
                    {isUntestedOn(createFormHsmKeyAlgorithm, hsmProviderType) && warn(t('hsm.mldsaUntestedGoogleKms'))}
                    {hsmAlgorithmOptions.length === 0 && refuse(t('cas.create.noKeyTypeAllowedByPolicy'))}
                  </>
                )}
                {createFormHsmKeyMode === 'existing' && (
                  createFormHsmProviderId && usableHsmKeys.length === 0 ? warn(t('cas.create.hsmNoUnusedKeys'), undefined)
                    : field('ca-hsm-key', t('cas.create.hsmExistingKey'), select('ca-hsm-key', createFormHsmKeyId, (v) => setCreateFormHsmKeyId(v),
                      usableHsmKeys.map((k) => ({ value: k.id.toString(), label: `${k.label} (${k.algorithm})` })), { required: true }))
                )}
              </>
            )
          )}
          {keyStorage === 'hsm' && hsmRefusal && refuse(hsmRefusal)}

          {keyIsRsa && field('ca-scheme', t('cas.signatureScheme'), select('ca-scheme', createFormSignatureScheme, (value) => setCreateFormSignatureScheme(value),
            schemeChoices.map((v) => ({ value: v, label: t(v === 'pss' ? 'cas.signatureSchemePss' : 'cas.signatureSchemePkcs1v15') })),
            { 'aria-describedby': 'hint-ca-scheme' }), { text: pssAvailable ? t('cas.signatureSchemeHelp') : t('cas.signatureSchemeHsmUnsupported') })}

          {createFormType !== 'external' && (
            <>
              {field('ca-validity', t('common.validityPeriod'), select('ca-validity', createFormValidity, (value) => setCreateFormValidity(value), [
                ...VALIDITY_YEAR_PRESETS.map((years) => ({ value: String(years), label: t('cas.yearsValidity', { count: years }) })),
                { value: CUSTOM_VALIDITY, label: t('cas.customValidityDays') },
              ]))}
              {createFormValidity === CUSTOM_VALIDITY && field('ca-validity-days', t('cas.validityDays'),
                <input id="ca-validity-days" name="validityDays" type="number" min={1} max={MAX_CA_VALIDITY_DAYS} required value={createFormValidityDays}
                  aria-describedby="hint-ca-validity-days" onChange={(e) => setCreateFormValidityDays(e.target.value)} />,
                { text: t('cas.validityDaysHelp', { max: MAX_CA_VALIDITY_DAYS }) })}
            </>
          )}

          {/* Certificate profile (RFC 5280 Key Usage / EKU), folded as the issue form's « Avancé » */}
          <div className="field full advanced">
            {toggle('ca-cert-profile', showCertProfile, () => setShowCertProfile(!showCertProfile), t('cas.create.certificateProfile'))}
            <div className="advanced-panel" id="ca-cert-profile" hidden={!showCertProfile}>
              {showCertProfile && (
                <>
                  <p className="field full small muted">{t('cas.create.certificateProfileHelp')}</p>
                  <fieldset className="field full eku-list">
                    <legend>{t('common.keyUsage')}</legend>
                    {CA_KU_OPTIONS.map((ku) => (
                      <label key={ku} className="checkbox-line">
                        <input type="checkbox" checked={createFormKeyUsage.includes(ku)} onChange={(e) => {
                          setCreateFormKeyUsage((prev) => (e.target.checked ? (prev.includes(ku) ? prev : [...prev, ku]) : prev.filter((x) => x !== ku)))
                        }} />
                        {ku}
                      </label>
                    ))}
                  </fieldset>
                  {createFormType === 'intermediate' && (
                    <label className="checkbox-line field full">
                      <input type="checkbox" checked={createFormEkuServerAuth} onChange={(e) => setCreateFormEkuServerAuth(e.target.checked)} />
                      {t('cas.create.ekuServerAuth')}
                    </label>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Advanced constraints (RFC 5280) */}
          <div className="field full advanced">
            {toggle('ca-constraints', showAdvanced, () => setShowAdvanced(!showAdvanced), t('cas.advancedConstraints'))}
            <div className="advanced-panel" id="ca-constraints" hidden={!showAdvanced}>
              {showAdvanced && (
                <>
                  {field('ca-pathlen', t('cas.pathLength'), <input id="ca-pathlen" type="number" min="0" value={createFormPathLength}
                    placeholder={t('cas.pathLengthPlaceholder')} onChange={(e) => setCreateFormPathLength(e.target.value)} />)}
                  {createFormType === 'external' ? (
                    <p className="field full small muted">{t('cas.nameConstraintsExternalNote')}</p>
                  ) : (
                    <>
                      <NameConstraintRows id="nc-permitted" label={t('cas.nameConstraintsPermitted')} hint={t('cas.nameConstraintsPermittedHint')}
                        addLabel={t('cas.nameConstraintAddPermitted')} rows={createFormNCPermitted} onChange={setCreateFormNCPermitted} />
                      <NameConstraintRows id="nc-excluded" label={t('cas.nameConstraintsExcluded')} hint={t('cas.nameConstraintsExcludedHint')}
                        addLabel={t('cas.nameConstraintAddExcluded')} rows={createFormNCExcluded} onChange={setCreateFormNCExcluded} />
                    </>
                  )}
                  <label className="checkbox-line field full">
                    <input type="checkbox" checked={createFormNamedUrls} onChange={(e) => setCreateFormNamedUrls(e.target.checked)} />
                    <span>{t('cas.namedUrls')}<small className="muted"> {t('cas.namedUrlsHint')}</small></span>
                  </label>
                </>
              )}
            </div>
          </div>
        </div>
        <div className="modal-actions">
          <button type="button" className="btn" onClick={onClose}>{t('common.cancel')}</button>
          <button type="submit" className="btn primary" data-write=""
            disabled={
              creating || policyBlocksCreate || missingParent || (
                keyStorage === 'hsm' && (
                  hsmProviders.length === 0
                  || (createFormHsmKeyMode === 'existing' && !!createFormHsmProviderId && usableHsmKeys.length === 0)
                )
              )
            }>
            {creating ? t('common.creating') : t('common.createCA')}
          </button>
        </div>
      </form>
    </AtelierDialog>
  )
}
