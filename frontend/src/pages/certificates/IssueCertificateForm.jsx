/**
 * Issue and renewal form of the Atelier, in two steps: Configure, then Review.
 * Review reads the request about to be sent (describeRequest), and Issue is only there.
 * A form closed without issuing keeps its draft for the next opening of the same operation.
 */
import { useState, useEffect, useMemo, useRef, useId } from 'react'
import {
  CaretRight, CaretLeft, CaretDown, Check, X, Plus, ShieldCheck, Question, Warning, PushPin, CalendarBlank, Hash,
} from '@phosphor-icons/react'
import { templatesService, ekuService, toolsService } from '../../services'
import { getSanValidationError, getAutoSansFromCn } from '../../lib/sanValidate'
import { hiddenFromIssuance, listedForIssuance, signingCas, unlistedSigningCas } from '../../lib/caSelection'
import { daysRemaining, extractCN, formatDate } from '../../lib/utils'
import { ISSUE_KEY_CHOICES, issueKeyLabel, isAllowed, useEffectiveAlgorithms } from '../../lib/policyAlgorithms'
import { RENEW_MAX_DAYS, originalDurationDays } from '../../lib/renewalPrompt'
import { ISSUE_DEFAULT_LABELS, findAlgorithm, isPostQuantum, isUsable } from '../../lib/keyAlgorithms'
import { BrainpoolNotice } from '../../components/BrainpoolNotice'
import { customExtensionsPayload, emptyExtensionRow } from '../../lib/customExtensions'
import { DRAFT_FIELDS, draftOp, dropDraft, keepDraft, takeDraft } from './issue/issueDrafts'
import { CERT_TYPE_KEYS, describeRequest, keyDisplay, listOf, SAN_FIELDS } from './issue/describeRequest'
import './issue/issue.css'

const P = 'certificates.issueForm.'
const MAX_DAYS = RENEW_MAX_DAYS
const SAN_TYPES = ['dns', 'ip', 'email', 'uri', 'upn']
const SAN_LABEL = { dns: 'DNS', ip: 'IP', email: 'Email', uri: 'URI', upn: 'UPN' }
const SAN_PLACEHOLDER = { dns: 'service.example.com', ip: '192.0.2.10', email: 'alice@example.com', uri: 'https://service.example.com', upn: 'alice@example.com' }
const COMMON_EKUS = [
  ['serverAuth', '1.3.6.1.5.5.7.3.1'], ['clientAuth', '1.3.6.1.5.5.7.3.2'], ['codeSigning', '1.3.6.1.5.5.7.3.3'],
  ['emailProtection', '1.3.6.1.5.5.7.3.4'], ['timeStamping', '1.3.6.1.5.5.7.3.8'],
]
const EKU_NAME = Object.fromEntries(COMMON_EKUS.map(([name, oid]) => [oid, name]))
// EKU OIDs a cert_type implies (mirror of backend cert_profiles)
const EKU_DEFAULTS_BY_TYPE = {
  server: ['1.3.6.1.5.5.7.3.1'], client: ['1.3.6.1.5.5.7.3.2'], combined: ['1.3.6.1.5.5.7.3.1', '1.3.6.1.5.5.7.3.2'],
  code_signing: ['1.3.6.1.5.5.7.3.3'], email: ['1.3.6.1.5.5.7.3.4'], custom: [],
}
const OID_RE = /^[0-2](?:\.(?:0|[1-9]\d*)){1,15}$/
const ANY_EKU = '2.5.29.37.0'
const SUBJECT_KEYS = ['country', 'state', 'locality', 'organization', 'organizational_unit', 'email']
// Template types -> cert_type; unmapped ones are custom (the template's own KU/EKU govern)
const TYPE_MAP = {
  web_server: 'server', vpn_server: 'server', client_auth: 'client', vpn_client: 'client', piv: 'client',
  email: 'email', code_signing: 'code_signing',
}
// Entries that are UI toggles or server-driven values: a draft is kept only when an entry changed
const SNAPSHOT_SKIP = new Set(['advanced', 'showAllTemplates', 'showHiddenCas', 'keyBy'])

function freshDraft({ initialData, certificate, mode }) {
  const prefillKey = initialData?.key_type ? issueKeyLabel(initialData.key_type, initialData.key_size) : null
  const subject = Object.fromEntries(SUBJECT_KEYS.map((k) => [k, initialData?.[k] || '']))
  const original = mode === 'renew' ? originalDurationDays(certificate) : null
  return {
    template: '', ca_id: '', cn: initialData?.cn || '', description: '', keySource: 'generate', csr: '',
    key: prefillKey || '', keyBy: prefillKey ? 'user' : null,
    validityMode: 'days', validity_days: mode === 'renew' ? (original ? String(original) : '') : '365', expiry_date: '',
    sans: initialData?.sans?.filter((s) => s && typeof s.type === 'string' && typeof s.value === 'string')
      .map((s) => ({ type: String(s.type).toLowerCase(), value: s.value })) || [{ type: 'dns', value: '' }],
    advanced: SUBJECT_KEYS.some((k) => subject[k]), cert_type: 'server', extra_ekus: [], ocsp_must_staple: false,
    subject, customExt: [], hybrid: false, hybrid_classical: '', hybrid_pq: '', showAllTemplates: false, showHiddenCas: false,
  }
}

// Numbers in the interface language ("3 650" in French)
const num = (n) => Number(n).toLocaleString((typeof document !== 'undefined' && document.documentElement.lang) || undefined)

const snapshot = (d) => JSON.stringify(DRAFT_FIELDS.filter((k) => !SNAPSHOT_SKIP.has(k) && !(k === 'key' && !d.keyBy))
  .map((k) => d[k]))

/** Splits t(key, { name }) around the name, to set it in bold. */
function withName(t, key, name) {
  const marker = '\u0000'
  const parts = String(t(key, { name: marker })).split(marker)
  return parts.length === 2 ? <>{parts[0]}<strong>{name}</strong>{parts[1]}</> : parts[0]
}

function FieldError({ id, message }) {
  if (!message) return null
  return <p className="iss-error" id={id}><Warning aria-hidden="true" /><span>{message}</span></p>
}

export function Steps({ step, t }) {
  return (
    <div className="iss-steps" aria-label={t(`${P}stepsLabel`)} role="group">
      <div className={`iss-step${step === 1 ? ' is-active' : ''}`} aria-current={step === 1 ? 'step' : undefined}>
        <span className="iss-step-mark">{step === 1 ? '1' : <Check aria-hidden="true" />}</span>{t(`${P}stepConfigure`)}
      </div>
      <CaretRight aria-hidden="true" />
      <div className={`iss-step${step === 2 ? ' is-active' : ''}`} aria-current={step === 2 ? 'step' : undefined}>
        <span className="iss-step-mark">2</span>{t(`${P}stepReview`)}
      </div>
    </div>
  )
}

/**
 * @param {object} p
 * @param {'issue'|'renew'} [p.mode]
 * @param {object} [p.certificate]  the certificate a renewal starts from
 * @param {(body: object, info: { kind: string, csr?: string, certificate?: object }) => Promise<object|void>} p.onSubmit
 *   resolves to { approval: policyName } when the request now waits for approval, { cancelled: true } when the
 *   operator stepped back; throws to show the server's refusal in the Review step
 * @param {(step: number) => void} [p.onStepChange]
 * @param {boolean} [p.canUseCsr]  whether the operator may hand in a CSR (write:csrs)
 */
export function IssueCertificateForm({
  cas = [], initialData, onSubmit, onCancel, t, mode = 'issue', certificate = null, onStepChange, canUseCsr = false,
}) {
  const uid = useId().replace(/:/g, '')
  const id = (name) => `${uid}-${name}`
  const renew = mode === 'renew'
  const op = draftOp(mode, certificate?.id)
  const [initial] = useState(() => {
    const fresh = freshDraft({ initialData, certificate, mode })
    const saved = initialData ? null : takeDraft(op)
    return { fresh, saved }
  })
  const [d, setD] = useState(() => (initial.saved ? { ...initial.fresh, ...initial.saved } : initial.fresh))
  const [restored, setRestored] = useState(!!initial.saved)
  const set = (patch) => setD((prev) => ({ ...prev, ...(typeof patch === 'function' ? patch(prev) : patch) }))
  const [step, setStep] = useState(1)
  const [errors, setErrors] = useState({})
  const [announce, setAnnounce] = useState('')
  const [request, setRequest] = useState(null)
  const [reviewing, setReviewing] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [approval, setApproval] = useState(null)
  const [customOid, setCustomOid] = useState('')
  const [customOidError, setCustomOidError] = useState('')
  // #269: a ref, not state: a fast second click lands before React re-renders
  const [issuing, setIssuing] = useState(false)
  const issuingRef = useRef(false)
  const sentRef = useRef(false)
  const dRef = useRef(d)
  dRef.current = d
  const pristine = useRef(snapshot(initial.fresh))
  const reviewTitle = useRef(null)
  const firstField = useRef(null)

  // Closed without issuing: the draft waits for the next opening of the same operation
  useEffect(() => () => {
    if (!sentRef.current && snapshot(dRef.current) !== pristine.current) keepDraft(op, dRef.current)
  }, [op])
  useEffect(() => { onStepChange?.(step) }, [step, onStepChange])

  const [templates, setTemplates] = useState([])
  const [knownEkus, setKnownEkus] = useState([])
  useEffect(() => {
    if (renew) return undefined
    let cancelled = false
    ekuService.getKnown()
      .then((resp) => { if (!cancelled) setKnownEkus(resp?.data?.ekus || resp?.ekus || []) })
      .catch(() => { /* the five common EKUs and a custom OID stay available */ })
    return () => { cancelled = true }
  }, [renew])
  // Templates of the CA (with their pins) once one is chosen; CA templates are created elsewhere
  useEffect(() => {
    if (renew) return undefined
    let cancelled = false
    const load = d.ca_id ? templatesService.getForCA(d.ca_id) : templatesService.getAll()
    Promise.resolve(load).then((res) => {
      const list = res?.data || res || []
      if (!cancelled) setTemplates(Array.isArray(list) ? list.filter((tpl) => tpl.template_type !== 'ca') : [])
    }).catch(() => {})
    return () => { cancelled = true }
  }, [d.ca_id, renew])

  const offeredTemplates = useMemo(() => templates.filter((tpl) => tpl.is_active !== false), [templates])
  const hasPinned = templates.some((tpl) => tpl.is_pinned)
  const listedTemplates = useMemo(() => {
    const pinned = offeredTemplates.filter((tpl) => tpl.is_pinned)
    const list = d.ca_id && pinned.length && !d.showAllTemplates ? pinned : offeredTemplates
    // The chosen template stays listed when the pin filter would hide it
    const chosen = offeredTemplates.find((tpl) => String(tpl.id) === d.template)
    return chosen && !list.includes(chosen) ? [...list, chosen] : list
  }, [offeredTemplates, d.ca_id, d.showAllTemplates, d.template])
  const template = offeredTemplates.find((tpl) => String(tpl.id) === d.template) || null
  const ext = useMemo(() => {
    let value = template?.extensions_template
    if (typeof value === 'string') { try { value = JSON.parse(value) } catch { value = null } }
    return value || {}
  }, [template])
  const templateSanTypes = Array.isArray(ext.san_types)
    ? ext.san_types.map((s) => String(s).toLowerCase()).filter((s) => SAN_TYPES.includes(s)) : []
  const enforcedSanTypes = template?.enforce_san_types && templateSanTypes.length ? templateSanTypes : null

  // Key types the policies of this CA and template allow (#397); the server enforces them regardless
  const { allowedKeyTypes, allowedDigests, fips, fipsKeys, mldsa, pqStandalone, defaultKeyType } = useEffectiveAlgorithms({
    caId: d.ca_id, templateId: d.template, enabled: !renew,
  })
  const pairLabels = useMemo(() => ISSUE_KEY_CHOICES
    .map(([type, size]) => issueKeyLabel(type, size))
    .filter((l) => isAllowed(allowedKeyTypes, l) && isUsable(findAlgorithm(l), { fips, fipsKeys, mldsa })),
  [allowedKeyTypes, fips, fipsKeys, mldsa])
  // A post-quantum key the policies refuse alone (pq_standalone) is offered in a hybrid pair only
  const singleLabels = useMemo(() => (pqStandalone ? pairLabels.filter((l) => !isPostQuantum(l)) : pairLabels),
    [pairLabels, pqStandalone])
  const noKeyAllowed = !renew && singleLabels.length === 0
  const hybridClassical = pairLabels.filter((l) => !isPostQuantum(l))
  const hybridPq = pairLabels.filter(isPostQuantum)
  const hybridAvailable = hybridClassical.length > 0 && hybridPq.length > 0
  // Each side keeps its choice while allowed, else the server default when it fits that side, else the first
  const pickHybrid = (current, allowed) => (allowed.includes(current) ? current
    : [defaultKeyType, ...ISSUE_DEFAULT_LABELS].find((l) => l && allowed.includes(l)) ?? allowed[0] ?? '')
  const hybridChoice = { classical: pickHybrid(d.hybrid_classical, hybridClassical), pq: pickHybrid(d.hybrid_pq, hybridPq) }
  const csrMode = !renew && canUseCsr && d.keySource === 'csr'
  const isHybrid = d.hybrid && hybridAvailable && !csrMode

  // The server's default key for this CA and template, until the user or a template picks one
  useEffect(() => {
    if (renew) return
    const label = defaultKeyType && findAlgorithm(defaultKeyType)?.issue ? defaultKeyType : ''
    setD((prev) => (prev.keyBy || prev.key === label ? prev : { ...prev, key: label }))
  }, [defaultKeyType, renew])
  // A key the policies forbid switches to the server default, else one of its family, else the first allowed
  useEffect(() => {
    if (renew || noKeyAllowed) return
    setD((prev) => {
      if ((!prev.key && !allowedKeyTypes) || singleLabels.includes(prev.key)) return prev
      const family = findAlgorithm(prev.key)?.issue?.[0]
      const def = !prev.keyBy && singleLabels.includes(defaultKeyType) ? defaultKeyType : null
      const next = def || singleLabels.find((l) => findAlgorithm(l)?.issue?.[0] === family) || singleLabels[0]
      return next === prev.key ? prev : { ...prev, key: next }
    })
  }, [singleLabels, allowedKeyTypes, noKeyAllowed, defaultKeyType, renew])

  const selectedCa = cas.find((ca) => String(ca.id) === String(d.ca_id))
  const caExpiry = useMemo(() => {
    const value = selectedCa?.valid_to || selectedCa?.expires || selectedCa?.expiry
    return typeof value === 'string' ? value.split('T')[0] : null
  }, [selectedCa])
  const caDaysLeft = caExpiry ? daysRemaining(caExpiry) : null
  const maxDays = renew ? MAX_DAYS : Math.max(1, Math.min(MAX_DAYS, caDaysLeft ?? MAX_DAYS))
  const today = useMemo(() => new Date().toISOString().split('T')[0], [])

  const issuingCas = listedForIssuance(signingCas(cas), d.showHiddenCas, d.ca_id)
  const hiddenCount = hiddenFromIssuance(signingCas(cas), d.ca_id)
  const unlisted = unlistedSigningCas(cas)

  const applyTemplate = (templateId) => {
    const tpl = templateId ? offeredTemplates.find((x) => String(x.id) === templateId) : null
    const tplKey = tpl?.key_type && findAlgorithm(tpl.key_type)?.issue ? tpl.key_type : null
    setErrors({})
    set((prev) => {
      const next = { template: templateId }
      // A keyless template releases only a template's key, never the user's own choice
      if (tplKey) Object.assign(next, { key: tplKey, keyBy: 'template' })
      else if (prev.keyBy === 'template') Object.assign(next, { key: '', keyBy: null })
      if (!tpl) return next
      if (tpl.validity_days) next.validity_days = String(tpl.validity_days)
      if (tpl.template_type) next.cert_type = TYPE_MAP[tpl.template_type] || 'custom'
      const dn = typeof tpl.dn_template === 'string' ? JSON.parse(tpl.dn_template || '{}') : (tpl.dn_template || {})
      const subject = { ...prev.subject }
      for (const [field, key] of [['O', 'organization'], ['OU', 'organizational_unit'], ['C', 'country'], ['ST', 'state'], ['L', 'locality']]) {
        if (dn[field]) subject[key] = dn[field]
      }
      // A placeholder like "{email}" of the built-in templates is not an address
      const email = dn.emailAddress && !/[{}]/.test(dn.emailAddress) ? dn.emailAddress.trim() : ''
      if (email) subject.email = email
      next.subject = subject
      if (['O', 'OU', 'C', 'ST', 'L'].some((f) => dn[f]) || email) next.advanced = true
      return next
    })
    setAnnounce(tpl ? t(`${P}templateApplied`, { name: tpl.name }) : '')
  }

  const autoSans = useMemo(() => (csrMode || renew ? [] : getAutoSansFromCn({
    cn: d.cn, certType: d.cert_type, subjectEmail: d.subject.email,
  })), [d.cn, d.cert_type, d.subject.email, csrMode, renew])
  const wildcardBase = useMemo(() => {
    const cn = d.cn.trim()
    if (!cn.startsWith('*.') || csrMode) return null
    const base = cn.slice(2)
    if (!base.includes('.') || d.sans.some((s) => s.type === 'dns' && s.value === base)) return null
    return base
  }, [d.cn, d.sans, csrMode])

  const defaultEkus = useMemo(() => {
    const names = ext.extended_key_usage
    if (template && Array.isArray(names) && names.length) {
      const byName = Object.fromEntries([...knownEkus.map((e) => [String(e.name).toLowerCase(), e.oid]),
        ...COMMON_EKUS.map(([n, oid]) => [n.toLowerCase(), oid])])
      return names.map((n) => (OID_RE.test(n) ? n : byName[String(n).toLowerCase()])).filter(Boolean)
    }
    return EKU_DEFAULTS_BY_TYPE[d.cert_type] || []
  }, [ext, template, knownEkus, d.cert_type])
  const ekuLabel = (oid) => (EKU_NAME[oid] ? t(`${P}eku.${EKU_NAME[oid]}`) : (knownEkus.find((e) => e.oid === oid)?.name || oid))

  // --- Request -------------------------------------------------------------------------------
  const validityDays = () => (d.validityMode === 'date' && d.expiry_date
    ? Math.max(1, daysRemaining(d.expiry_date) ?? 1) : parseInt(d.validity_days, 10))

  function validate() {
    const e = {}
    if (renew) {
      const text = String(d.validity_days ?? '').trim()
      if (text && !(/^\d+$/.test(text) && Number(text) >= 1 && Number(text) <= MAX_DAYS)) {
        e.days = t(`${P}validityInvalid`, { max: MAX_DAYS })
      }
      return e
    }
    // In the order of the fields on screen: the first one in error takes the focus
    if (!d.ca_id) e.ca = t(`${P}caRequired`)
    if (!csrMode && !d.cn.trim()) e.cn = t(`${P}cnRequired`)
    if (csrMode && !d.csr.includes('BEGIN CERTIFICATE REQUEST')) e.csr = t(`${P}csrInvalid`)
    if (noKeyAllowed && !csrMode) e.key = t('certificates.noKeyTypeAllowedByPolicy')
    if (d.validityMode === 'date') {
      if (!d.expiry_date || d.expiry_date <= today || (caExpiry && d.expiry_date > caExpiry)) {
        e.days = caExpiry ? t(`${P}dateInvalidCa`, { date: formatDate(caExpiry, { time: false }) }) : t(`${P}dateInvalid`)
      }
    } else {
      const days = Number(d.validity_days)
      if (!Number.isInteger(days) || days < 1 || days > maxDays) e.days = t(`${P}validityInvalid`, { max: maxDays })
    }
    d.sans.forEach((s, i) => {
      if (!s.value.trim()) return
      if (enforcedSanTypes && !enforcedSanTypes.includes(s.type)) {
        e[`san-${i}`] = t(`${P}sanTypeRefused`, { type: SAN_LABEL[s.type], template: template?.name })
        return
      }
      const err = getSanValidationError(s.type, s.value, { i18nNs: 'certificates' })
      if (err) e[`san-${i}`] = t(err.key, err.params)
    })
    if (!e.cn) {
      const autoErr = autoSans.map((s) => getSanValidationError(s.type, s.value, { i18nNs: 'certificates' })).find(Boolean)
      if (autoErr) e.cn = t(autoErr.key, autoErr.params)
    }
    customExtensionsPayload(d.customExt).errors.forEach((err, i) => { if (err) e[`ext-${i}`] = t(err) })
    return e
  }

  function buildRequest() {
    if (renew) {
      const text = String(d.validity_days ?? '').trim()
      const original = originalDurationDays(certificate)
      // Left at the original duration (or empty), nothing is sent and the server keeps it exactly
      const body = text === '' || (original && text === String(original)) ? {} : { validity_days: Number(text) }
      return { kind: 'renew', body }
    }
    const buckets = Object.fromEntries(SAN_FIELDS.map(([field]) => [field, []]))
    const push = (type, value) => {
      const v = value.trim()
      const list = buckets[`san_${type}`]
      if (v && list && !list.includes(v)) list.push(v)
    }
    autoSans.forEach((s) => push(s.type, s.value))
    d.sans.forEach((s) => push(s.type, s.value))
    const sanBody = Object.fromEntries(Object.entries(buckets).filter(([, v]) => v.length))
    const extEntries = customExtensionsPayload(d.customExt).entries
    const common = {
      ca_id: d.ca_id,
      validity_days: validityDays(),
      cert_type: d.cert_type,
      ...sanBody,
      ...(d.template && { template_id: parseInt(d.template, 10) }),
      ...(d.extra_ekus.length && { extra_ekus: d.extra_ekus }),
      ...(extEntries.length && { custom_extensions: extEntries }),
    }
    if (csrMode) return { kind: 'csr', body: common, csr: d.csr.trim() }
    const pair = findAlgorithm(d.key)?.issue
    const subject = Object.fromEntries(SUBJECT_KEYS.filter((k) => d.subject[k]?.trim()).map((k) => [k, d.subject[k].trim()]))
    const body = {
      ca_id: d.ca_id,
      cn: d.cn.trim(),
      cert_type: d.cert_type,
      ...(d.description.trim() && { description: d.description.trim() }),
      ...subject,
      ...(pair && { key_type: pair[0], key_size: pair[1] }),
      ...(isHybrid && {
        key_type: findAlgorithm(hybridChoice.classical).issue[0],
        key_size: findAlgorithm(hybridChoice.classical).issue[1],
        hybrid: { classical: hybridChoice.classical, pq: hybridChoice.pq },
      }),
      validity_days: common.validity_days,
      ...sanBody,
      ...(d.template && { template_id: parseInt(d.template, 10) }),
      ...(d.ocsp_must_staple && { ocsp_must_staple: true }),
      ...(d.extra_ekus.length && { extra_ekus: d.extra_ekus }),
      ...(extEntries.length && { custom_extensions: extEntries }),
    }
    return { kind: 'issue', body }
  }

  const focusField = (key) => {
    const target = {
      cn: 'cn', ca: 'ca', csr: 'csr', days: d.validityMode === 'date' && !renew ? 'date' : 'days', key: 'key',
    }[key] || (key.startsWith('san-') ? `san-value-${key.slice(4)}` : key.startsWith('ext-') ? `ext-oid-${key.slice(4)}` : null)
    if (key.startsWith('ext-')) set({ advanced: true })
    // After the render that shows the field (an extension sits in the collapsed Advanced panel)
    setTimeout(() => document.getElementById(id(target))?.focus())
  }

  const toReview = async (event) => {
    event.preventDefault()
    if (reviewing) return
    const found = validate()
    setErrors(found)
    const first = Object.keys(found)[0]
    if (first) {
      setAnnounce(t(`${P}fixErrors`))
      focusField(first)
      return
    }
    const next = buildRequest()
    if (next.kind === 'csr') {
      setReviewing(true)
      try {
        const res = await toolsService.decodeCsr({ pem: next.csr })
        const info = res?.data || res || {}
        const key = info.public_key
        next.csrInfo = {
          subject: info.subject, cn: extractCN(info.subject) || info.subject,
          key: key ? [key.type, key.curve || key.size].filter(Boolean).join(' ') : '',
        }
      } catch (err) {
        setErrors({ csr: t(`${P}csrUnreadable`, { message: err?.message || '' }) })
        focusField('csr')
        return
      } finally {
        setReviewing(false)
      }
    }
    setAnnounce('')
    setSubmitError('')
    setRequest(next)
    setStep(2)
    setTimeout(() => reviewTitle.current?.focus())
  }

  const back = () => {
    setStep(1)
    setSubmitError('')
    setTimeout(() => firstField.current?.focus())
  }

  const issue = async () => {
    if (issuingRef.current || !request) return
    issuingRef.current = true
    setIssuing(true)
    setSubmitError('')
    try {
      const outcome = await onSubmit(request.body, { kind: request.kind, csr: request.csr, certificate })
      if (outcome?.cancelled) return
      sentRef.current = true
      dropDraft(op)
      if (outcome?.approval !== undefined) setApproval(outcome.approval || '')
    } catch (err) {
      // The refusal stays in the step; the entry is kept for a correction
      setSubmitError(err?.message || t('common.operationFailed'))
    } finally {
      issuingRef.current = false
      setIssuing(false)
    }
  }

  const resetDraft = () => {
    dropDraft(op)
    setD(initial.fresh)
    setRestored(false)
    setErrors({})
    setAnnounce('')
    setTimeout(() => firstField.current?.focus())
  }

  // --- Rendering -----------------------------------------------------------------------------
  const describedBy = (...ids) => ids.filter(Boolean).join(' ') || undefined
  const errorProps = (key, hint) => ({
    'aria-invalid': errors[key] ? 'true' : undefined,
    'aria-describedby': describedBy(hint && id(hint), errors[key] && id(`err-${key}`)),
  })
  const clearError = (key) => { if (errors[key]) setErrors(({ [key]: _gone, ...rest }) => rest) }
  const setSubject = (key, value) => set((prev) => ({ subject: { ...prev.subject, [key]: value } }))
  const updateSan = (i, patch) => { clearError(`san-${i}`); set((prev) => ({ sans: prev.sans.map((s, j) => (j === i ? { ...s, ...patch } : s)) })) }
  const updateExt = (i, patch) => { clearError(`ext-${i}`); set((prev) => ({ customExt: prev.customExt.map((r, j) => (j === i ? { ...r, ...patch } : r)) })) }
  const toggleEku = (oid, on) => set((prev) => ({ extra_ekus: on ? [...prev.extra_ekus, oid] : prev.extra_ekus.filter((x) => x !== oid) }))
  const addCustomOid = () => {
    const value = customOid.trim()
    const resolved = knownEkus.find((e) => e.name.toLowerCase() === value.toLowerCase())?.oid || value
    if (!OID_RE.test(resolved)) { setCustomOidError(t('certificates.eku.invalidOid')); return }
    if (resolved === ANY_EKU) { setCustomOidError(t('certificates.eku.anyNotAllowed')); return }
    if (!defaultEkus.includes(resolved) && !d.extra_ekus.includes(resolved)) toggleEku(resolved, true)
    setCustomOid('')
    setCustomOidError('')
  }

  const keyHint = () => {
    if (csrMode) return t(`${P}keyHintCsr`)
    if (isHybrid) return t(`${P}keyHintHybrid`)
    if (d.keyBy === 'template' && template?.key_type) return t(`${P}keyHintTemplate`, { key: keyDisplay(template.key_type) })
    if (defaultKeyType) return t(`${P}keyHintServer`, { key: keyDisplay(defaultKeyType) })
    return t(`${P}keyHintNone`)
  }

  const sanTypeOptions = (current) => {
    const allowed = enforcedSanTypes || SAN_TYPES
    return [...new Set([...allowed, current])]
  }

  const renderHint = () => {
    if (renew) {
      const names = SAN_FIELDS.flatMap(([field, type]) => listOf(certificate?.[field]).map((v) => `${type} ${v}`))
      return (
        <aside className="iss-hint" aria-labelledby={id('hint-title')}>
          <h3 id={id('hint-title')}><ShieldCheck aria-hidden="true" />{t(`${P}hintTitle`)}</h3>
          <p>{withName(t, `${P}hintRenew`, certificate?.cn || certificate?.common_name || '')}</p>
          <dl>
            <dt>{t(`${P}authority`)}</dt><dd>{certificate?.issuer_name || ''}</dd>
            <dt>{t(`${P}hintSubject`)}</dt><dd>{certificate?.subject || ''}</dd>
            <dt>{t(`${P}hintAlgorithms`)}</dt><dd>{t(`${P}hintRenewKey`, { key: certificate?.key_algorithm || certificate?.key_type || '' })}</dd>
            <dt>{t(`${P}hintValidity`)}</dt><dd>{t(`${P}hintRenewValidity`, { max: num(MAX_DAYS) })}</dd>
            <dt>{t(`${P}hintSans`)}</dt><dd>{names.length ? names.join(', ') : t(`${P}noneMasc`)}</dd>
          </dl>
          <p>{t(`${P}hintRenewFooter`)}</p>
        </aside>
      )
    }
    const defaultDays = template?.validity_days || 365
    const digest = template?.digest ? String(template.digest).toUpperCase().replace(/^SHA(\d)/, 'SHA-$1') : null
    return (
      <aside className="iss-hint" aria-labelledby={id('hint-title')} data-testid="issue-hint">
        <h3 id={id('hint-title')}><ShieldCheck aria-hidden="true" />{t(`${P}hintTitle`)}</h3>
        <p>{template ? withName(t, `${P}hintTemplate`, template.name) : t(`${P}hintNoTemplate`)}</p>
        <dl>
          <dt>{t(`${P}hintAuthorities`)}</dt>
          <dd>
            {t(`${P}caCount`, { count: issuingCas.length })}
            {unlisted > 0 && <><br /><span className="iss-muted" data-testid="unlisted-cas">{t('cas.notListedForSigning', { count: unlisted })}</span></>}
          </dd>
          <dt>{t(`${P}hintAlgorithms`)}</dt>
          <dd data-testid="hint-algorithms">
            {singleLabels.length ? singleLabels.map(keyDisplay).join(', ') : t(`${P}hintAlgorithmsNone`)}
            {pqStandalone && hybridPq.length > 0 && <><br /><span className="iss-muted">{t(`${P}hintPqPairOnly`)}</span></>}
          </dd>
          <dt>{t(`${P}hintValidity`)}</dt>
          <dd>{t(`${P}hintValidityValue`, { days: defaultDays, max: num(maxDays) })}</dd>
          <dt>{t(`${P}hintSans`)}</dt>
          <dd>{enforcedSanTypes ? enforcedSanTypes.map((s) => SAN_LABEL[s]).join(', ')
            : templateSanTypes.length ? t(`${P}hintSansSuggested`, { types: templateSanTypes.map((s) => SAN_LABEL[s]).join(', ') })
              : t(`${P}hintSansAll`)}</dd>
          {canUseCsr && <><dt>{t(`${P}hintCsr`)}</dt><dd>{t(`${P}hintCsrAccepted`)}</dd></>}
          <dt>{t(`${P}hintHashEku`)}</dt>
          <dd>
            {digest || t(`${P}hintHashCa`)} · {defaultEkus.length ? defaultEkus.map(ekuLabel).join(', ') : t(`${P}ekusNone`)}
            {allowedDigests && <><br /><span className="iss-muted">{t(`${P}hintDigestsAllowed`, { list: allowedDigests.map((x) => x.toUpperCase().replace(/^SHA(\d)/, 'SHA-$1')).join(', ') })}</span></>}
          </dd>
        </dl>
        <p>{t(`${P}hintFooter`)}</p>
      </aside>
    )
  }

  const renderConfigure = () => (
    <form onSubmit={toReview} noValidate>
      {restored && (
        <p className="iss-notice iss-draft-note" data-testid="draft-note">
          <Question aria-hidden="true" />
          <span>{t(`${P}draftRestored`)} <button type="button" className="iss-text-link" onClick={resetDraft}>{t(`${P}draftReset`)}</button></span>
        </p>
      )}
      <div className="iss-layout">
        <div className="iss-fields">
          <div className="iss-field">
            <label htmlFor={id('template')}>{t(`${P}template`)}</label>
            {renew ? (
              <select id={id('template')} ref={firstField} disabled><option>{certificate?.template_name || t(`${P}noTemplate`)}</option></select>
            ) : (
              <select id={id('template')} ref={firstField} value={d.template} aria-describedby={id('hint-template')}
                onChange={(e) => applyTemplate(e.target.value)}>
                <option value="">{t(`${P}noTemplate`)}</option>
                {listedTemplates.map((tpl) => <option key={tpl.id} value={String(tpl.id)}>{tpl.name}</option>)}
              </select>
            )}
            <small id={id('hint-template')}>
              {renew ? t(`${P}templateRenewHint`) : (template?.description || (template ? '' : t(`${P}templateNoneHint`)))}
            </small>
            {!renew && hasPinned && d.ca_id && (
              <button type="button" className="iss-text-link" onClick={() => set((prev) => ({ showAllTemplates: !prev.showAllTemplates }))}>
                <PushPin aria-hidden="true" />
                {d.showAllTemplates ? t('templates.showPinnedOnly') : t('templates.showAllTemplates', { count: offeredTemplates.length })}
              </button>
            )}
          </div>
          <div className="iss-field">
            <label htmlFor={id('ca')}>{t(`${P}authority`)}</label>
            {renew ? (
              <select id={id('ca')} disabled><option>{certificate?.issuer_name || ''}</option></select>
            ) : (
              <select id={id('ca')} value={d.ca_id} {...errorProps('ca', 'hint-ca')}
                onChange={(e) => { clearError('ca'); set({ ca_id: e.target.value }) }}>
                {!d.ca_id && <option value="">{t(`${P}selectCa`)}</option>}
                {issuingCas.map((ca) => <option key={ca.id} value={String(ca.id)}>{ca.descr || ca.common_name}</option>)}
              </select>
            )}
            <small id={id('hint-ca')}>
              {renew ? t(`${P}caRenewHint`) : t(`${P}caCount`, { count: issuingCas.length })}
            </small>
            {!renew && hiddenCount > 0 && (
              <button type="button" className="iss-text-link" onClick={() => set((prev) => ({ showHiddenCas: !prev.showHiddenCas }))}>
                {d.showHiddenCas ? t('cas.hideHiddenCas') : t('cas.showHiddenCas', { count: hiddenCount })}
              </button>
            )}
            <FieldError id={id('err-ca')} message={errors.ca} />
          </div>

          <div className="iss-field is-full">
            <label htmlFor={id('cn')}>{t(`${P}commonName`)}</label>
            <input id={id('cn')} value={renew ? (certificate?.cn || certificate?.common_name || '') : d.cn} maxLength={253}
              readOnly={renew} disabled={csrMode} autoComplete="off" spellCheck="false"
              placeholder={csrMode ? '' : 'service.example.com'} {...errorProps('cn', 'hint-cn')}
              onChange={(e) => { clearError('cn'); set({ cn: e.target.value }) }} />
            <small id={id('hint-cn')}>{t(renew ? `${P}cnRenewHint` : csrMode ? `${P}cnCsrHint` : `${P}cnHint`)}</small>
            <FieldError id={id('err-cn')} message={errors.cn} />
          </div>

          {!renew && (
            <div className="iss-field is-full">
              <label htmlFor={id('description')}>{t(`${P}description`)} <span className="iss-optional">{t(`${P}optional`)}</span></label>
              <input id={id('description')} value={d.description} maxLength={120} disabled={csrMode} autoComplete="off"
                placeholder={t(`${P}descriptionPlaceholder`)} aria-describedby={id('hint-description')}
                onChange={(e) => set({ description: e.target.value })} />
              <small id={id('hint-description')}>{t(csrMode ? `${P}descriptionCsrHint` : `${P}descriptionHint`)}</small>
            </div>
          )}

          <fieldset className="iss-field is-full">
            <legend>{t(`${P}keySource`)}</legend>
            <div className="iss-choices">
              <label className="iss-choice">
                <input type="radio" name={id('keySource')} value="generate" checked={renew || !csrMode}
                  onChange={() => set({ keySource: 'generate' })} />
                <span>{t(`${P}keyGenerate`)}<small>{t(renew ? `${P}keyGenerateRenewHint` : `${P}keyGenerateHint`)}</small></span>
              </label>
              {(renew || canUseCsr) && (
                <label className="iss-choice">
                  <input type="radio" name={id('keySource')} value="csr" checked={csrMode} disabled={renew}
                    onChange={() => { clearError('key'); set({ keySource: 'csr' }) }} />
                  <span>{t(`${P}keyCsr`)}<small>{t(renew ? `${P}keyCsrRenewHint` : `${P}keyCsrHint`)}</small></span>
                </label>
              )}
            </div>
          </fieldset>

          {csrMode && (
            <div className="iss-field is-full">
              <label htmlFor={id('csr')}>{t(`${P}csr`)}</label>
              <textarea id={id('csr')} className="iss-mono" rows={5} spellCheck="false" value={d.csr}
                placeholder="-----BEGIN CERTIFICATE REQUEST-----" {...errorProps('csr', 'hint-csr')}
                onChange={(e) => { clearError('csr'); set({ csr: e.target.value }) }} />
              <small id={id('hint-csr')}>{t(`${P}csrHint`)}</small>
              <label className="iss-text-link">
                <input type="file" accept=".csr,.pem,.req,.txt" className="iss-sr-only"
                  onChange={async (e) => {
                    const file = e.target.files?.[0]
                    if (file) { clearError('csr'); set({ csr: await file.text() }) }
                  }} />
                {t(`${P}csrFile`)}
              </label>
              <FieldError id={id('err-csr')} message={errors.csr} />
            </div>
          )}

          <div className="iss-field">
            <label htmlFor={id('key')}>{t(`${P}keyAlgorithm`)}</label>
            {renew ? (
              <select id={id('key')} disabled><option>{certificate?.key_algorithm || certificate?.key_type || ''}</option></select>
            ) : (
              <select id={id('key')} value={csrMode ? '' : (isHybrid ? hybridChoice.classical : d.key)} disabled={csrMode || isHybrid}
                {...errorProps('key', 'hint-key')}
                onChange={(e) => set({ key: e.target.value, keyBy: 'user' })}>
                {(csrMode || (!d.key && !isHybrid)) && <option value="">{t(csrMode ? `${P}keyFromCsr` : `${P}keyServerDefault`)}</option>}
                {!csrMode && (isHybrid ? hybridClassical : singleLabels).map((l) => <option key={l} value={l}>{keyDisplay(l)}</option>)}
                {!csrMode && d.key && !isHybrid && !singleLabels.includes(d.key) && <option value={d.key}>{keyDisplay(d.key)}</option>}
              </select>
            )}
            <small id={id('hint-key')}>{renew ? t(`${P}keyHintRenew`) : keyHint()}</small>
            {!renew && !csrMode && !isHybrid && <BrainpoolNotice label={d.key} />}
            <FieldError id={id('err-key')} message={errors.key || (noKeyAllowed && !csrMode ? t('certificates.noKeyTypeAllowedByPolicy') : '')} />
          </div>
          <div className="iss-field">
            <div className="iss-label-row">
              <label htmlFor={id(d.validityMode === 'date' && !renew ? 'date' : 'days')}>
                {t(d.validityMode === 'date' && !renew ? `${P}validityDate` : `${P}validityDays`)}
              </label>
              {!renew && (
                <button type="button" className="iss-text-link" aria-label={t(d.validityMode === 'date' ? `${P}useDays` : `${P}useDate`)}
                  title={t(d.validityMode === 'date' ? `${P}useDays` : `${P}useDate`)}
                  onClick={() => { clearError('days'); set((prev) => ({ validityMode: prev.validityMode === 'date' ? 'days' : 'date' })) }}>
                  {d.validityMode === 'date' ? <Hash aria-hidden="true" /> : <CalendarBlank aria-hidden="true" />}
                </button>
              )}
            </div>
            {d.validityMode === 'date' && !renew ? (
              <>
                <input id={id('date')} type="date" value={d.expiry_date} min={today} max={caExpiry || undefined}
                  {...errorProps('days', 'hint-days')}
                  onChange={(e) => { clearError('days'); set({ expiry_date: e.target.value }) }} />
              </>
            ) : (
              <>
                <input id={id('days')} type="number" min="1" max={maxDays} step="1" value={d.validity_days}
                  {...errorProps('days', 'hint-days')}
                  onChange={(e) => { clearError('days'); set({ validity_days: e.target.value }) }} />
              </>
            )}
            <small id={id('hint-days')}>
              {renew
                ? t(`${P}validityRenewHint`, { max: num(MAX_DAYS), days: originalDurationDays(certificate) ?? '' })
                : caExpiry
                  ? t(`${P}validityHintCa`, { max: num(maxDays), date: formatDate(caExpiry, { time: false }) })
                  : t(`${P}validityHint`, { max: num(maxDays) })}
            </small>
            <FieldError id={id('err-days')} message={errors.days} />
          </div>

          <fieldset className="iss-field is-full">
            <legend>{t(`${P}sansLegend`)}</legend>
            {renew ? (
              <small id={id('hint-san')}>
                {t(`${P}sansRenew`)} {SAN_FIELDS.flatMap(([field, type]) => listOf(certificate?.[field]).map((v) => `${type} ${v}`)).join(', ')}
              </small>
            ) : (
              <>
                <small id={id('hint-san')}>
                  {csrMode ? t(`${P}sansCsrHint`)
                    : t(enforcedSanTypes ? `${P}sansHintEnforced` : `${P}sansHint`, { types: (enforcedSanTypes || SAN_TYPES).map((s) => SAN_LABEL[s]).join(', ') })}
                </small>
                {autoSans.length > 0 && (
                  <p className="iss-auto" data-testid="auto-sans">
                    <span>{t(`${P}autoIncluded`)}</span>
                    {autoSans.map((s) => <span key={`${s.type}-${s.value}`}>{SAN_LABEL[s.type]} {s.value}</span>)}
                  </p>
                )}
                <div className="iss-rows">
                  {d.sans.map((s, i) => (
                    <div className="iss-san-row" key={i}>
                      <label className="iss-sr-only" htmlFor={id(`san-type-${i}`)}>{t(`${P}sanType`, { n: i + 1 })}</label>
                      <select id={id(`san-type-${i}`)} value={s.type} onChange={(e) => updateSan(i, { type: e.target.value })}>
                        {sanTypeOptions(s.type).map((type) => (
                          <option key={type} value={type}>
                            {enforcedSanTypes && !enforcedSanTypes.includes(type) ? t(`${P}sanNotAllowed`, { type: SAN_LABEL[type] }) : SAN_LABEL[type]}
                          </option>
                        ))}
                      </select>
                      <label className="iss-sr-only" htmlFor={id(`san-value-${i}`)}>{t(`${P}sanValue`, { n: i + 1 })}</label>
                      <input id={id(`san-value-${i}`)} value={s.value} placeholder={SAN_PLACEHOLDER[s.type]} autoComplete="off" spellCheck="false"
                        {...errorProps(`san-${i}`, 'hint-san')} onChange={(e) => updateSan(i, { value: e.target.value })} />
                      <button type="button" className="iss-icon-btn" aria-label={t(`${P}removeSan`, { n: i + 1 })}
                        onClick={() => { setErrors({}); set((prev) => ({ sans: prev.sans.filter((_, j) => j !== i) })) }}>
                        <X aria-hidden="true" />
                      </button>
                      <FieldError id={id(`err-san-${i}`)} message={errors[`san-${i}`]} />
                    </div>
                  ))}
                </div>
                <div className="iss-auto">
                  <button type="button" className="iss-btn is-quiet iss-add-row"
                    onClick={() => set((prev) => ({ sans: [...prev.sans, { type: (enforcedSanTypes || SAN_TYPES)[0], value: '' }] }))}>
                    <Plus aria-hidden="true" />{t(`${P}addSan`)}
                  </button>
                  {wildcardBase && (
                    <button type="button" className="iss-text-link"
                      onClick={() => set((prev) => ({ sans: [...prev.sans.filter((s) => s.value.trim()), { type: 'dns', value: wildcardBase }] }))}>
                      {t(`${P}addBaseDomain`, { domain: wildcardBase })}
                    </button>
                  )}
                </div>
              </>
            )}
          </fieldset>

          {!renew && renderAdvanced()}
        </div>
        {renderHint()}
      </div>
      <p className="iss-announce" role="status" aria-live="polite">{announce}</p>
      <div className="iss-actions">
        <button type="button" className="iss-btn" onClick={onCancel}>{t('common.cancel')}</button>
        <button type="submit" className="iss-btn is-primary" disabled={reviewing}>
          {t(`${P}toReview`)}<CaretRight aria-hidden="true" />
        </button>
      </div>
    </form>
  )

  function renderAdvanced() {
    const extras = d.extra_ekus.filter((oid) => !COMMON_EKUS.some(([, o]) => o === oid))
    return (
      <div className="iss-field is-full iss-advanced">
        <button type="button" className="iss-advanced-toggle" aria-expanded={d.advanced} aria-controls={id('advanced')}
          onClick={() => set((prev) => ({ advanced: !prev.advanced }))}>
          {d.advanced ? <CaretDown aria-hidden="true" /> : <CaretRight aria-hidden="true" />}
          <span>{t(`${P}advanced`)}</span><small>{t(`${P}advancedHint`)}</small>
        </button>
        <div className="iss-advanced-panel" id={id('advanced')} hidden={!d.advanced}>
          <div className="iss-field">
            <label htmlFor={id('certType')}>{t('certificates.certType')}</label>
            <select id={id('certType')} value={d.cert_type} disabled={!!template} aria-describedby={id('hint-certType')}
              onChange={(e) => set({ cert_type: e.target.value })}>
              {Object.entries(CERT_TYPE_KEYS).map(([value, key]) => <option key={value} value={value}>{t(`certificates.certType${key}`)}</option>)}
            </select>
            <small id={id('hint-certType')}>{template ? t('certificates.certTypeFromTemplate') : t(`${P}certTypeHint`)}</small>
            {!csrMode && (
              <label className="iss-check">
                <input type="checkbox" checked={d.ocsp_must_staple} onChange={(e) => set({ ocsp_must_staple: e.target.checked })} />
                <span>{t('certificates.ocspMustStaple')}</span>
              </label>
            )}
          </div>
          <fieldset className="iss-field">
            <legend>{t(`${P}ekus`)}</legend>
            <div className="iss-eku-list">
              {[...COMMON_EKUS.map(([, oid]) => oid), ...extras].map((oid) => {
                const locked = defaultEkus.includes(oid)
                return (
                  <label className="iss-check" key={oid}>
                    <input type="checkbox" value={oid} checked={locked || d.extra_ekus.includes(oid)} disabled={locked}
                      onChange={(e) => toggleEku(oid, e.target.checked)} />
                    <span>{ekuLabel(oid)}<small className="iss-mono">{oid}</small></span>
                  </label>
                )
              })}
            </div>
            <div className="iss-inline">
              <label className="iss-sr-only" htmlFor={id('oid')}>{t(`${P}otherOid`)}</label>
              <input id={id('oid')} className="iss-mono" value={customOid} placeholder={t(`${P}otherOid`)} autoComplete="off" spellCheck="false"
                aria-invalid={customOidError ? 'true' : undefined} aria-describedby={customOidError ? id('err-oid') : undefined}
                onChange={(e) => { setCustomOid(e.target.value); setCustomOidError('') }}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addCustomOid() } }} />
              <button type="button" className="iss-btn" onClick={addCustomOid}>{t(`${P}addOid`)}</button>
            </div>
            <FieldError id={id('err-oid')} message={customOidError} />
            <small>{defaultEkus.length
              ? t(template ? `${P}ekusFromTemplate` : `${P}ekusFromType`, { list: defaultEkus.map(ekuLabel).join(', ') })
              : t(`${P}ekusNone`)}</small>
          </fieldset>

          {!csrMode && (
            <fieldset className="iss-field is-full">
              <legend>{t(`${P}subject`)}</legend>
              <small>{t(`${P}subjectHint`)}</small>
              <div className="iss-subject">
                {[['country', 'common.country', 2], ['state', 'common.stateProvince'], ['locality', 'common.locality'],
                  ['organization', 'common.organization'], ['organizational_unit', `${P}subjectOu`], ['email', 'common.email']].map(([key, label, max]) => (
                  <div className="iss-field" key={key}>
                    <label htmlFor={id(`subject-${key}`)}>{t(label)}</label>
                    <input id={id(`subject-${key}`)} value={d.subject[key]} maxLength={max} autoComplete="off"
                      type={key === 'email' ? 'email' : 'text'} onChange={(e) => setSubject(key, e.target.value)} />
                  </div>
                ))}
              </div>
            </fieldset>
          )}

          {!csrMode && hybridAvailable && (
            <fieldset className="iss-field is-full">
              <legend>{t(`${P}hybrid`)}</legend>
              <label className="iss-check">
                <input type="checkbox" checked={d.hybrid} onChange={(e) => set({ hybrid: e.target.checked })} />
                <span>{t('certificates.hybrid.toggle')}</span>
              </label>
              <small>{t('certificates.hybrid.toggleHint')}</small>
              {isHybrid && (
                <div className="iss-subject">
                  <div className="iss-field">
                    <label htmlFor={id('hybrid-classical')}>{t('certificates.hybrid.classical')}</label>
                    <select id={id('hybrid-classical')} value={hybridChoice.classical} onChange={(e) => set({ hybrid_classical: e.target.value })}>
                      {hybridClassical.map((l) => <option key={l} value={l}>{keyDisplay(l)}</option>)}
                    </select>
                  </div>
                  <div className="iss-field">
                    <label htmlFor={id('hybrid-pq')}>{t('certificates.hybrid.pq')}</label>
                    <select id={id('hybrid-pq')} value={hybridChoice.pq} onChange={(e) => set({ hybrid_pq: e.target.value })}>
                      {hybridPq.map((l) => <option key={l} value={l}>{keyDisplay(l)}</option>)}
                    </select>
                  </div>
                </div>
              )}
            </fieldset>
          )}

          <fieldset className="iss-field is-full">
            <legend>{t('customExtensions.title')}</legend>
            <small id={id('hint-ext')}>{`${t('customExtensions.hint')} ${template ? t('customExtensions.requestHint') : ''}`.trim()}</small>
            <div className="iss-rows">
              {d.customExt.map((row, i) => (
                <div className="iss-ext-row" key={i}>
                  <label className="iss-sr-only" htmlFor={id(`ext-oid-${i}`)}>{t(`${P}extOid`, { n: i + 1 })}</label>
                  <input id={id(`ext-oid-${i}`)} className="iss-mono iss-ext-oid" value={row.oid} placeholder="1.3.6.1.4.1.32473.1"
                    autoComplete="off" spellCheck="false" inputMode="decimal" {...errorProps(`ext-${i}`, 'hint-ext')}
                    onChange={(e) => updateExt(i, { oid: e.target.value })} />
                  <label className="iss-sr-only" htmlFor={id(`ext-value-${i}`)}>{t(`${P}extValue`, { n: i + 1 })}</label>
                  <input id={id(`ext-value-${i}`)} className="iss-mono iss-ext-value" value={row.value} placeholder="0c0568656c6c6f"
                    autoComplete="off" spellCheck="false" onChange={(e) => updateExt(i, { value: e.target.value })} />
                  <button type="button" className="iss-icon-btn" aria-label={t(`${P}removeExt`, { n: i + 1 })}
                    onClick={() => { setErrors({}); set((prev) => ({ customExt: prev.customExt.filter((_, j) => j !== i) })) }}>
                    <X aria-hidden="true" />
                  </button>
                  <label className="iss-check">
                    <input type="checkbox" checked={row.critical} onChange={(e) => updateExt(i, { critical: e.target.checked })} />
                    <span>{t('customExtensions.critical')}</span>
                  </label>
                  <FieldError id={id(`err-ext-${i}`)} message={errors[`ext-${i}`]} />
                </div>
              ))}
            </div>
            {d.customExt.some((r) => r.critical) && (
              <p className="iss-notice is-warn" data-testid="custom-extensions-critical-warning">
                <Warning aria-hidden="true" /><span>{t('customExtensions.criticalWarning')}</span>
              </p>
            )}
            <button type="button" className="iss-btn is-quiet iss-add-row"
              onClick={() => set((prev) => ({ customExt: [...prev.customExt, emptyExtensionRow()] }))}>
              <Plus aria-hidden="true" />{t('customExtensions.add')}
            </button>
          </fieldset>
        </div>
      </div>
    )
  }

  const renderReview = () => {
    const { title, rows } = describeRequest(request, { t, templates: offeredTemplates, cas, certificate })
    const fields = new Set(rows.flatMap((r) => r.fields))
    const action = request.kind === 'renew' ? `${P}renewAction` : request.kind === 'csr' ? `${P}signAction` : `${P}issueAction`
    return (
      <div>
        <div className="iss-review" data-testid="issue-review" data-fields={[...fields].join(' ')}>
          <h3 ref={reviewTitle} tabIndex={-1}>{title}</h3>
          <dl>
            {rows.map((r) => (
              <div key={r.id} style={{ display: 'contents' }} data-row={r.id}>
                <dt>{r.label}</dt>
                <dd className={r.lines.some((l) => l.mono) ? 'iss-mono' : undefined}>
                  {r.lines.map((l, i) => (
                    <span key={i}>{i > 0 && <br />}<span className={l.muted === true ? 'iss-muted' : undefined}>{l.text}</span>
                      {typeof l.muted === 'string' && l.muted && <span className="iss-muted">{l.muted}</span>}</span>
                  ))}
                </dd>
              </div>
            ))}
          </dl>
        </div>
        {approval !== null ? (
          <p className="iss-notice is-warn iss-review-note" role="status" data-testid="approval-sent">
            <Warning aria-hidden="true" />
            <span>{t(request.kind === 'renew' ? `${P}approvalSentRenew` : `${P}approvalSent`, { policy: approval })}</span>
          </p>
        ) : (
          <p className="iss-notice iss-review-note">
            <Question aria-hidden="true" />
            <span>{t(request.kind === 'renew' ? `${P}reviewNoteRenew` : `${P}reviewNote`)}</span>
          </p>
        )}
        {submitError && (
          <p className="iss-notice is-bad iss-review-note" role="alert" data-testid="issue-error">
            <Warning aria-hidden="true" /><span>{submitError}</span>
          </p>
        )}
        <div className="iss-actions">
          {approval !== null ? (
            <button type="button" className="iss-btn is-primary" onClick={onCancel}>{t('common.close')}</button>
          ) : (
            <>
              <button type="button" className="iss-btn" onClick={back} disabled={issuing}>
                <CaretLeft aria-hidden="true" />{t(`${P}back`)}
              </button>
              <button type="button" className="iss-btn is-primary" onClick={issue} disabled={issuing} data-testid="issue-submit">
                <Check aria-hidden="true" />{issuing ? t(`${P}issuing`) : t(action)}
              </button>
            </>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="iss-step-body">
      <Steps step={step} t={t} />
      {step === 1 || !request ? renderConfigure() : renderReview()}
    </div>
  )
}
