/**
 * Issue and renewal form of the Atelier, in two steps: Configure, then Review.
 * Review reads the request about to be sent (describeRequest), and Issue is only there.
 * A form closed without issuing keeps its draft for the next opening of the same operation.
 */
import { Fragment, useState, useEffect, useMemo, useRef, useId } from 'react'
import { Icon } from '../../components/atelier'
import { templatesService, ekuService, toolsService } from '../../services'
import { getSanValidationError, getAutoSansFromCn } from '../../lib/sanValidate'
import { hiddenFromIssuance, listedForIssuance, signingCas, unlistedSigningCas } from '../../lib/caSelection'
import { daysRemaining, extractCN, formatDate } from '../../lib/utils'
import { ISSUE_KEY_CHOICES, issueKeyLabel, isAllowed, useEffectiveAlgorithms } from '../../lib/policyAlgorithms'
import { RENEW_MAX_DAYS, originalDurationDays } from '../../lib/renewalPrompt'
import { ISSUE_DEFAULT_LABELS, findAlgorithm, isBrainpool, isPostQuantum, isUsable } from '../../lib/keyAlgorithms'
import { customExtensionsPayload, emptyExtensionRow } from '../../lib/customExtensions'
import { VALIDITY } from '../../constants/config'
import { DRAFT_FIELDS, draftOp, dropDraft, keepDraft, takeDraft } from './issue/issueDrafts'
import {
  CERT_TYPE_KEYS, certificateHash, certificateType, describeRequest, listOf, SAN_FIELDS,
} from './issue/describeRequest'
import { certificateKeyLabel, extKeyUsageName, keyLabel } from '../../lib/certificateDetail'

const P = 'certificates.issueForm.'
const MAX_DAYS = RENEW_MAX_DAYS
const DEFAULT_DAYS = VALIDITY.DEFAULT_DAYS
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
// TLS Feature (RFC 7633): the OCSP Must-Staple box of a renewal shows it
const MUST_STAPLE_OID = '1.3.6.1.5.5.7.1.24'
const SUBJECT_KEYS = ['country', 'state', 'locality', 'organization', 'organizational_unit', 'email']
const SUBJECT_FIELDS = [['country', 'common.country', 2], ['state', 'common.stateProvince'], ['locality', 'common.locality'],
  ['organization', 'common.organization'], ['organizational_unit', `${P}subjectOu`], ['email', 'common.email']]
const DN_KEYS = [['O', 'organization'], ['OU', 'organizational_unit'], ['C', 'country'], ['ST', 'state'], ['L', 'locality']]
// Template types -> cert_type; unmapped ones are custom (the template's own KU/EKU govern)
const TYPE_MAP = {
  web_server: 'server', vpn_server: 'server', client_auth: 'client', vpn_client: 'client', piv: 'client',
  email: 'email', code_signing: 'code_signing',
}
// Extensions UCM sets itself: the server refuses them as custom ones (RFC 5280 §4.2, one instance each)
const UCM_EXTENSIONS = {
  '2.5.29.15': 'Key Usage', '2.5.29.17': 'Subject Alternative Name', '2.5.29.19': 'Basic Constraints',
  '2.5.29.31': 'CRL Distribution Points', '2.5.29.37': 'Extended Key Usage', '1.3.6.1.5.5.7.1.1': 'Authority Information Access',
}
// Options of a list that show more of it instead of choosing
const SHOW_PINS = '__pins__'
const SHOW_HIDDEN = '__hidden__'
// Entries that are UI toggles or server-driven values: a draft is kept only when an entry changed
const SNAPSHOT_SKIP = new Set(['advanced', 'showAllTemplates', 'showHiddenCas', 'keyBy', 'daysBy'])

function freshDraft({ initialData, certificate, mode }) {
  const prefillKey = initialData?.key_type ? issueKeyLabel(initialData.key_type, initialData.key_size) : null
  const subject = Object.fromEntries(SUBJECT_KEYS.map((k) => [k, initialData?.[k] || '']))
  const original = mode === 'renew' ? originalDurationDays(certificate) : null
  return {
    template: '', ca_id: initialData?.ca_id != null ? String(initialData.ca_id) : '', cn: initialData?.cn || '',
    description: '', keySource: 'generate', csr: '',
    key: prefillKey || '', keyBy: prefillKey ? 'user' : null,
    validityMode: 'days', validity_days: mode === 'renew' ? (original ? String(original) : '') : String(DEFAULT_DAYS),
    daysBy: null, expiry_date: '',
    sans: initialData?.sans?.filter((s) => s && typeof s.type === 'string' && typeof s.value === 'string')
      .map((s) => ({ type: String(s.type).toLowerCase(), value: s.value })) || [{ type: 'dns', value: '' }],
    advanced: false, cert_type: 'server', extra_ekus: [], ocsp_must_staple: false,
    subject, customExt: [], hybrid: false, hybrid_classical: '', hybrid_pq: '', showAllTemplates: false, showHiddenCas: false,
  }
}

// Numbers in the interface language ("3 650" in French)
const num = (n) => Number(n).toLocaleString((typeof document !== 'undefined' && document.documentElement.lang) || undefined)

const snapshot = (d) => JSON.stringify(DRAFT_FIELDS.filter((k) => !SNAPSHOT_SKIP.has(k) && !(k === 'key' && !d.keyBy))
  .map((k) => d[k]))

const dnOf = (tpl) => {
  if (!tpl) return {}
  if (typeof tpl.dn_template !== 'string') return tpl.dn_template || {}
  try { return JSON.parse(tpl.dn_template || '{}') } catch { return {} }
}

/** The subject fields a template's DN sets ("{email}" placeholders of the built-in templates are no address). */
function templateSubject(tpl) {
  const dn = dnOf(tpl)
  const out = {}
  for (const [field, key] of DN_KEYS) if (dn[field]) out[key] = dn[field]
  if (dn.emailAddress && !/[{}]/.test(dn.emailAddress)) out.email = dn.emailAddress.trim()
  return out
}

/** Splits t(key, { name }) around the name, to set it in bold. */
function withName(t, key, name, params = {}) {
  const marker = '\u0000'
  const parts = String(t(key, { ...params, name: marker })).split(marker)
  return parts.length === 2 ? <>{parts[0]}<strong>{name}</strong>{parts[1]}</> : parts[0]
}

function FieldError({ id, message }) {
  if (!message) return null
  return <p className="field-error" id={id}><Icon name="warning" /><span>{message}</span></p>
}

export function Steps({ step, t }) {
  return (
    <div className="steps" aria-label={step === 1 ? t(`${P}stepsLabel`) : undefined}>
      <div className={`step${step === 1 ? ' active' : ''}`} aria-current={step === 1 ? 'step' : undefined}>
        <span>{step === 1 ? '1' : <Icon name="check" />}</span>{t(`${P}stepConfigure`)}
      </div>
      <Icon name="right" />
      <div className={`step${step === 2 ? ' active' : ''}`} aria-current={step === 2 ? 'step' : undefined}>
        <span>2</span>{t(`${P}stepReview`)}
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
 * @param {(outcome: object|undefined) => void} [p.onSent]  once the request went out; without it the Review
 *   step tells an approval itself
 * @param {(step: number) => void} [p.onStepChange]
 * @param {() => HTMLElement|null} [p.reviewFocus]  what takes the focus in the Review step (default: its title)
 * @param {boolean} [p.canUseCsr]  whether the operator may hand in a CSR (write:csrs)
 */
export function IssueCertificateForm({
  cas = [], initialData, onSubmit, onSent, onCancel, t, mode = 'issue', certificate = null, onStepChange, reviewFocus,
  canUseCsr = false,
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
  const pristine = useRef(snapshot(initial.fresh))
  // A value the form fills by itself: an untouched form stays untouched (no draft kept for it)
  const setAuto = (patch) => setD((prev) => {
    const next = { ...prev, ...(typeof patch === 'function' ? patch(prev) : patch) }
    if (snapshot(prev) === pristine.current) pristine.current = snapshot(next)
    return next
  })
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
  const reviewTitle = useRef(null)
  const firstField = useRef(null)
  const submitButton = useRef(null)
  const focusLater = (target) => setTimeout(() => (typeof target === 'string' ? document.getElementById(id(target)) : target?.current)?.focus())

  // Closed without issuing: the draft waits for the next opening of the same operation
  useEffect(() => () => {
    if (!sentRef.current && snapshot(dRef.current) !== pristine.current) keepDraft(op, dRef.current)
  }, [op])
  useEffect(() => { onStepChange?.(step) }, [step, onStepChange])

  const [templates, setTemplates] = useState([])
  const [templatesLoaded, setTemplatesLoaded] = useState(false)
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
      if (cancelled) return
      setTemplates(Array.isArray(list) ? list.filter((tpl) => tpl.template_type !== 'ca') : [])
      setTemplatesLoaded(true)
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

  const caLimit = (caId) => {
    const ca = cas.find((c) => String(c.id) === String(caId))
    const value = ca?.valid_to || ca?.expires || ca?.expiry
    const expiry = typeof value === 'string' ? value.split('T')[0] : null
    const left = expiry ? daysRemaining(expiry) : null
    const max = Math.max(1, Math.min(MAX_DAYS, left ?? MAX_DAYS))
    return { ca, expiry, max, bound: left != null && left < MAX_DAYS }
  }
  const limit = caLimit(d.ca_id)
  const selectedCa = limit.ca
  const caExpiry = limit.expiry
  const maxDays = renew ? MAX_DAYS : limit.max
  const today = useMemo(() => new Date().toISOString().split('T')[0], [])
  const defaultDays = template?.validity_days || DEFAULT_DAYS
  const caLabel = (ca) => ca?.descr || ca?.common_name || ''

  const issuingCas = listedForIssuance(signingCas(cas), d.showHiddenCas, d.ca_id)
  const hiddenCount = hiddenFromIssuance(signingCas(cas), d.ca_id)
  const unlisted = unlistedSigningCas(cas)
  const signers = signingCas(cas)

  // A sole choice is made for the user; several wait for theirs (a draft or the opener may have made it)
  const soleCa = !renew && !restored && !d.ca_id && signers.length === 1 ? String(signers[0].id) : null
  useEffect(() => {
    if (!soleCa) return
    const { max } = caLimit(soleCa)
    setAuto((prev) => ({ ca_id: soleCa, ...(prev.daysBy ? {} : { validity_days: String(Math.min(Number(prev.validity_days) || DEFAULT_DAYS, max)) }) }))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [soleCa])
  const soleTemplate = !renew && !restored && templatesLoaded && !d.template && offeredTemplates.length === 1
    ? String(offeredTemplates[0].id) : null
  useEffect(() => {
    if (soleTemplate) applyTemplate(soleTemplate, { auto: true })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [soleTemplate])

  // Values follow the template unless the user changed them and the new template still allows them
  const applyTemplate = (templateId, { auto = false } = {}) => {
    const tpl = templateId ? offeredTemplates.find((x) => String(x.id) === templateId) : null
    const tplKey = tpl?.key_type && findAlgorithm(tpl.key_type)?.issue ? tpl.key_type : null
    const prev = dRef.current
    const kept = []
    const reset = []
    const next = { template: templateId }
    if (prev.keyBy === 'user') { if (tplKey && tplKey !== prev.key) kept.push(t(`${P}keptKey`)) }
    else if (tplKey) Object.assign(next, { key: tplKey, keyBy: 'template' })
    // A keyless template releases only a template's key, never the user's own choice
    else if (prev.keyBy === 'template') Object.assign(next, { key: '', keyBy: null })
    const target = String(Math.min(tpl?.validity_days || DEFAULT_DAYS, maxDays))
    const days = Number(prev.validity_days)
    if (prev.daysBy === 'user' && prev.validityMode === 'days') {
      if (Number.isInteger(days) && days >= 1 && days <= maxDays) { if (String(days) !== target) kept.push(t(`${P}keptValidity`)) }
      else { reset.push(t(`${P}keptValidity`)); Object.assign(next, { validity_days: target, daysBy: null }) }
    } else if (prev.validityMode === 'days') next.validity_days = target
    next.cert_type = tpl ? (TYPE_MAP[tpl.template_type] || 'custom') : 'server'
    // The previous template's subject leaves with it; what the user typed stays
    const before = templateSubject(offeredTemplates.find((x) => String(x.id) === prev.template))
    const subject = Object.fromEntries(SUBJECT_KEYS.map((k) => [k, before[k] && prev.subject[k] === before[k] ? '' : prev.subject[k]]))
    Object.assign(subject, templateSubject(tpl))
    next.subject = subject
    const allowed = tpl?.enforce_san_types ? (extOf(tpl).san_types || []).map((s) => String(s).toLowerCase()) : null
    const banned = allowed?.length ? [...new Set(prev.sans.filter((s) => s.value.trim() && !allowed.includes(s.type)).map((s) => SAN_LABEL[s.type]))] : []
    setErrors({})
    ;(auto ? setAuto : set)(next)
    if (auto) return
    setAnnounce(tpl ? [
      t(`${P}templateApplied`, { name: tpl.name }),
      kept.length ? t(`${P}templateKept`, { list: kept.join(', ') }) : '',
      reset.length ? t(`${P}templateReset`, { list: reset.join(', ') }) : '',
      banned.length ? t(`${P}templateBannedSans`, { types: banned.join(', ') }) : '',
    ].filter(Boolean).join(' ') : '')
  }

  // A chosen authority bounds the validity: untouched it follows, typed it shrinks and says so
  const chooseCa = (caId) => {
    clearError('ca')
    const bound = caLimit(caId)
    const prev = dRef.current
    const patch = { ca_id: caId }
    let note = ''
    if (prev.validityMode === 'days') {
      if (!prev.daysBy) patch.validity_days = String(Math.min(defaultDays, bound.max))
      else if (Number(prev.validity_days) > bound.max) {
        patch.validity_days = String(bound.max)
        note = t(`${P}validityFitted`, { days: num(bound.max), ca: caLabel(bound.ca), date: formatDate(bound.expiry, { time: false }) })
      }
    }
    set(patch)
    setAnnounce(note)
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

  const daysError = (text, max, bound) => {
    const days = Number(text)
    if (!/^\d+$/.test(String(text).trim()) || !Number.isInteger(days) || days < 1) return t(`${P}validityInvalid`, { max: num(max) })
    if (days > max) {
      return bound ? t(`${P}validityTooLongCa`, { ca: caLabel(selectedCa), date: formatDate(caExpiry, { time: false }), max: num(max) })
        : t(`${P}validityTooLong`, { max: num(max) })
    }
    return null
  }

  function extensionErrors(e) {
    const { errors: found } = customExtensionsPayload(d.customExt)
    d.customExt.forEach((row, i) => {
      const oid = String(row.oid || '').trim()
      const err = found[i]
      if (err === 'customExtensions.invalidOid') e[`ext-${i}`] = t(`${P}extOidInvalid`)
      else if (UCM_EXTENSIONS[oid]) e[`ext-${i}`] = t(`${P}extOidReserved`, { oid, name: UCM_EXTENSIONS[oid] })
      else if (err === 'customExtensions.duplicateOid') e[`ext-${i}`] = t(err)
      else if (err === 'customExtensions.emptyValue') e[`extv-${i}`] = t(`${P}extValueRequired`)
      else if (err) e[`extv-${i}`] = t(err)
    })
  }

  function validate() {
    const e = {}
    if (renew) {
      // The original duration is not sent and the server keeps it whatever its length; a typed one is bounded
      const text = String(d.validity_days ?? '').trim()
      const original = originalDurationDays(certificate)
      if (text && !(original && text === String(original))) { const err = daysError(text, MAX_DAYS, false); if (err) e.days = err }
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
      const err = daysError(d.validity_days, maxDays, limit.bound)
      if (err) e.days = err
    }
    d.sans.forEach((s, i) => {
      if (!s.value.trim()) return
      if (enforcedSanTypes && !enforcedSanTypes.includes(s.type)) {
        e[`san-${i}`] = t(`${P}sanTypeRefused`, { type: SAN_LABEL[s.type], template: template?.name })
        return
      }
      if (getSanValidationError(s.type, s.value, { i18nNs: 'certificates' })) e[`san-${i}`] = t(`${P}sanInvalid.${s.type}`)
    })
    if (!e.cn) {
      const autoErr = autoSans.map((s) => getSanValidationError(s.type, s.value, { i18nNs: 'certificates' })).find(Boolean)
      if (autoErr) e.cn = t(autoErr.key, autoErr.params)
    }
    extensionErrors(e)
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
    }[key] || (key.startsWith('san-') ? `san-value-${key.slice(4)}` : key.startsWith('extv-') ? `ext-value-${key.slice(5)}`
      : key.startsWith('ext-') ? `ext-oid-${key.slice(4)}` : null)
    // After the render that shows the field
    if (target) focusLater(target)
  }

  const toReview = async (event) => {
    event.preventDefault()
    if (reviewing) return
    const found = validate()
    setErrors(found)
    const keys = Object.keys(found)
    if (keys.length) {
      // Advanced unfolds for any error it holds, not only for the first one
      if (keys.some((k) => k.startsWith('ext-') || k.startsWith('extv-'))) set({ advanced: true })
      setAnnounce(t(`${P}fixErrors`, { count: keys.length }))
      focusField(keys[0])
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
          key: key ? keyLabel([key.type, key.curve || key.size].filter(Boolean).join(' '), t) : '',
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
    setTimeout(() => (reviewFocus?.() || reviewTitle.current)?.focus())
  }

  const back = () => {
    setStep(1)
    setSubmitError('')
    focusLater(firstField)
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
      if (onSent) onSent(outcome)
      else if (outcome?.approval !== undefined) setApproval(outcome.approval || '')
    } catch (err) {
      // The refusal stays in the step; the entry is kept for a correction and Issue takes the focus back
      setSubmitError(err?.message || t('common.operationFailed'))
      focusLater(submitButton)
    } finally {
      issuingRef.current = false
      setIssuing(false)
    }
  }

  const resetDraft = () => {
    dropDraft(op)
    setD(initial.fresh)
    pristine.current = snapshot(initial.fresh)
    setRestored(false)
    setErrors({})
    setAnnounce('')
    focusLater(firstField)
  }

  // --- Rendering -----------------------------------------------------------------------------
  const describedBy = (...ids) => ids.filter(Boolean).join(' ') || undefined
  const errorProps = (key, hint) => ({
    'aria-invalid': errors[key] ? 'true' : undefined,
    'aria-describedby': describedBy(hint && id(hint), errors[key] && id(`err-${key}`)),
  })
  const clearError = (...keys) => {
    if (keys.some((k) => errors[k])) setErrors((all) => Object.fromEntries(Object.entries(all).filter(([k]) => !keys.includes(k))))
  }
  const setSubject = (key, value) => set((prev) => ({ subject: { ...prev.subject, [key]: value } }))
  const updateSan = (i, patch) => { clearError(`san-${i}`); set((prev) => ({ sans: prev.sans.map((s, j) => (j === i ? { ...s, ...patch } : s)) })) }
  const updateExt = (i, patch) => { clearError(`ext-${i}`, `extv-${i}`); set((prev) => ({ customExt: prev.customExt.map((r, j) => (j === i ? { ...r, ...patch } : r)) })) }
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
  // A new row takes the focus; a removed one hands it to its neighbour, or to the add button
  const addSan = () => {
    const n = d.sans.length
    setErrors({})
    set((prev) => ({ sans: [...prev.sans, { type: (enforcedSanTypes || SAN_TYPES)[0], value: '' }] }))
    focusLater(`san-value-${n}`)
  }
  const removeSan = (i) => {
    const left = d.sans.length - 1
    setErrors({})
    set((prev) => ({ sans: prev.sans.filter((_, j) => j !== i) }))
    focusLater(left ? `san-value-${Math.min(i, left - 1)}` : 'san-add')
  }
  const addExt = () => {
    const n = d.customExt.length
    set((prev) => ({ customExt: [...prev.customExt, emptyExtensionRow()] }))
    focusLater(`ext-oid-${n}`)
  }
  const removeExt = (i) => {
    const left = d.customExt.length - 1
    setErrors({})
    set((prev) => ({ customExt: prev.customExt.filter((_, j) => j !== i) }))
    focusLater(left ? `ext-oid-${Math.min(i, left - 1)}` : 'ext-add')
  }

  const keyHint = () => {
    if (csrMode) return t(`${P}keyHintCsr`)
    if (noKeyAllowed) return t(`${P}hintAlgorithmsNone`)
    if (isHybrid) return t(`${P}keyHintHybrid`)
    if (d.keyBy === 'template' && template?.key_type) return t(`${P}keyHintTemplate`, { key: keyLabel(template.key_type, t) })
    if (defaultKeyType) return t(d.ca_id ? `${P}keyHintServer` : `${P}keyHintServerAny`, { key: keyLabel(defaultKeyType, t) })
    return t(`${P}keyHintNone`)
  }

  const sanTypeOptions = (current) => {
    const allowed = enforcedSanTypes || SAN_TYPES
    return [...new Set([...allowed, current])]
  }
  const serverType = ['server', 'combined'].includes(d.cert_type)
  // The name that equals the common name is not repeated as a row, as in the Atelier; when it is the
  // only name it stays, so the form and the review list the same names
  const renewCn = certificate?.cn || certificate?.common_name || ''
  const allRenewSans = SAN_FIELDS.flatMap(([field, type]) => listOf(certificate?.[field]).map((value) => ({ type, value })))
  const otherRenewSans = allRenewSans.filter((s) => s.value !== renewCn)
  const renewSans = otherRenewSans.length ? otherRenewSans : allRenewSans
  const renewSubject = SUBJECT_KEYS.filter((k) => certificate?.[k])

  const renderHint = () => {
    if (renew) {
      const hash = certificateHash(certificate)
      const types = [...new Set(allRenewSans.map((s) => s.type))]
      return (
        <aside className="field-hint" aria-labelledby={id('hint-title')} data-testid="issue-hint">
          <h3 id={id('hint-title')}><Icon name="shield" /> {t(`${P}hintTitle`)}</h3>
          <p>{withName(t, `${P}hintRenew`, certificate?.cn || certificate?.common_name || '')}</p>
          <dl>
            <dt>{t(`${P}hintAuthorities`)}</dt><dd>{certificate?.issuer_name || ''}</dd>
            <dt>{t(`${P}hintAlgorithms`)}</dt><dd>{certificateKeyLabel(certificate, t)}</dd>
            <dt>{t(`${P}hintValidity`)}</dt><dd>{t(`${P}hintRenewValidity`, { max: num(MAX_DAYS) })}</dd>
            <dt>{t(`${P}hintSans`)}</dt><dd>{types.length ? types.join(', ') : t(`${P}noneMasc`)}</dd>
            <dt>{t(`${P}hintCsr`)}</dt><dd>{t(`${P}hintCsrRenew`)}</dd>
            <dt>{t(`${P}hintHashEku`)}</dt><dd>{[hash, t(`${P}hintRenewKept`)].filter(Boolean).join(' · ')}</dd>
          </dl>
          <p>{t(`${P}hintRenewFooter`)}</p>
        </aside>
      )
    }
    const digest = template?.digest ? String(template.digest).toUpperCase().replace(/^SHA(\d)/, 'SHA-$1') : null
    const sanTypes = enforcedSanTypes || (templateSanTypes.length ? templateSanTypes : SAN_TYPES)
    return (
      <aside className="field-hint" aria-labelledby={id('hint-title')} data-testid="issue-hint">
        <h3 id={id('hint-title')}><Icon name="shield" /> {t(`${P}hintTitle`)}</h3>
        <p>{template ? withName(t, `${P}hintTemplate`, template.name) : t(`${P}hintNoTemplate`)}</p>
        <dl className="props">
          <dt>{t(`${P}hintAuthorities`)}</dt>
          <dd>
            {signers.length <= 3 ? signers.map(caLabel).join(', ') || t(`${P}noneFem`) : t(`${P}hintCaCount`, { count: signers.length })}
            {unlisted > 0 && <><br /><span className="muted" data-testid="unlisted-cas">{t(`${P}hintExcluded`, { count: unlisted })}</span></>}
          </dd>
          <dt>{t(`${P}hintAlgorithms`)}</dt>
          <dd data-testid="hint-algorithms">
            {singleLabels.length ? singleLabels.map((l) => keyLabel(l, t)).join(', ') : t(`${P}hintAlgorithmsNone`)}
            {pqStandalone && hybridPq.length > 0 && <><br /><span className="muted">{t(`${P}hintPqPairOnly`)}</span></>}
          </dd>
          <dt>{t(`${P}hintValidity`)}</dt>
          <dd>{t(`${P}hintValidityValue`, { days: num(defaultDays), max: num(maxDays) })}</dd>
          <dt>{t(`${P}hintSans`)}</dt>
          <dd>{sanTypes.map((s) => SAN_LABEL[s]).join(', ')}
            {!enforcedSanTypes && templateSanTypes.length > 0 && <span className="muted"> {t(`${P}hintSansSuggested`)}</span>}</dd>
          {canUseCsr && <><dt>{t(`${P}hintCsr`)}</dt><dd>{t(`${P}hintCsrAccepted`)}</dd></>}
          <dt>{t(`${P}hintHashEku`)}</dt>
          <dd>
            {digest || t(`${P}hintHashCa`)} · {defaultEkus.length ? defaultEkus.map(ekuLabel).join(', ') : t(`${P}ekusNone`)}
            {allowedDigests && <><br /><span className="muted">{t(`${P}hintDigestsAllowed`, { list: allowedDigests.map((x) => x.toUpperCase().replace(/^SHA(\d)/, 'SHA-$1')).join(', ') })}</span></>}
          </dd>
        </dl>
        <p>{t(`${P}hintFooter`)}</p>
      </aside>
    )
  }

  // A value the request cannot change: shown as the Atelier shows an imposed field
  const fixed = (name, value, hint, extra = {}) => (
    <input id={id(name)} value={value} readOnly autoComplete="off" aria-describedby={hint ? id(hint) : undefined} {...extra} />
  )

  const renderSans = () => {
    if (renew) {
      return (
        <fieldset className="field full">
          <legend>{t(`${P}sansLegend`)}</legend>
          <small id={id('hint-san')}>{t(`${P}sansRenew`)}</small>
          {/* The rows and buttons of an issuance, read-only: the server keeps the names; without any
              name, the empty row of the Atelier keeps its place */}
          <div className="row-list">
            {(renewSans.length ? renewSans : [{ type: 'DNS', value: '' }]).map((s, i) => (
              <div className="san-row" key={`${s.type}-${s.value}`}>
                <label className="sr-only" htmlFor={id(`san-type-${i}`)}>{t(`${P}sanType`, { n: i + 1 })}</label>
                {fixed(`san-type-${i}`, s.type)}
                <label className="sr-only" htmlFor={id(`san-value-${i}`)}>{t(`${P}sanValue`, { n: i + 1 })}</label>
                {fixed(`san-value-${i}`, s.value, 'hint-san')}
                <button type="button" className="icon-btn" disabled aria-label={t(`${P}removeSan`, { n: i + 1 })}>
                  <Icon name="close" />
                </button>
              </div>
            ))}
          </div>
          <button type="button" className="btn quiet add-row" disabled aria-describedby={id('hint-san')}>
            <Icon name="plus" />{t(`${P}addSan`)}
          </button>
        </fieldset>
      )
    }
    const types = (enforcedSanTypes || SAN_TYPES).map((s) => SAN_LABEL[s]).join(', ')
    const included = autoSans.map((s) => `${SAN_LABEL[s.type]} ${s.value}`).join(', ')
    return (
      <fieldset className="field full">
        <legend>{t(`${P}sansLegend`)}</legend>
        <small id={id('hint-san')}>
          {csrMode ? t(`${P}sansCsrHint`)
            : t(enforcedSanTypes ? `${P}sansHintEnforced` : `${P}sansHint`, { types })}
          {!csrMode && (included
            ? <span data-testid="auto-sans"> {t(`${P}autoIncluded`, { list: included })}</span>
            : serverType && <> {t(`${P}sansCnCounts`)}</>)}
        </small>
        <div className="row-list">
          {d.sans.map((s, i) => (
            <div className="san-row" key={i}>
              <label className="sr-only" htmlFor={id(`san-type-${i}`)}>{t(`${P}sanType`, { n: i + 1 })}</label>
              <select id={id(`san-type-${i}`)} value={s.type} onChange={(e) => updateSan(i, { type: e.target.value })}>
                {sanTypeOptions(s.type).map((type) => (
                  <option key={type} value={type}>
                    {enforcedSanTypes && !enforcedSanTypes.includes(type) ? t(`${P}sanNotAllowed`, { type: SAN_LABEL[type] }) : SAN_LABEL[type]}
                  </option>
                ))}
              </select>
              <label className="sr-only" htmlFor={id(`san-value-${i}`)}>{t(`${P}sanValue`, { n: i + 1 })}</label>
              <input id={id(`san-value-${i}`)} value={s.value} placeholder={SAN_PLACEHOLDER[s.type]} autoComplete="off" spellCheck="false"
                {...errorProps(`san-${i}`, 'hint-san')} onChange={(e) => updateSan(i, { value: e.target.value })} />
              <button type="button" className="icon-btn" aria-label={t(`${P}removeSan`, { n: i + 1 })} onClick={() => removeSan(i)}>
                <Icon name="close" />
              </button>
              <FieldError id={id(`err-san-${i}`)} message={errors[`san-${i}`]} />
            </div>
          ))}
        </div>
        <button type="button" id={id('san-add')} className="btn quiet add-row" onClick={addSan}>
          <Icon name="plus" />{t(`${P}addSan`)}
        </button>
        {wildcardBase && (
          <div className="row-actions">
            <button type="button" className="text-link"
              onClick={() => set((prev) => ({ sans: [...prev.sans.filter((s) => s.value.trim()), { type: 'dns', value: wildcardBase }] }))}>
              {t(`${P}addBaseDomain`, { domain: wildcardBase })}
            </button>
          </div>
        )}
      </fieldset>
    )
  }

  const renderConfigure = () => (
    <form onSubmit={toReview} noValidate>
      {restored && (
        <p className="notice draft-note" id="draft-note" data-testid="draft-note">
          <Icon name="help" />
          <span>{t(`${P}draftRestored`)} <button type="button" className="text-link" onClick={resetDraft}>{t(`${P}draftReset`)}</button></span>
        </p>
      )}
      <div id="issue-dynamic">
      <div className="form-layout">
        <div className="form-fields">
          <div className="field">
            <label htmlFor={id('template')}>{t(`${P}template`)}</label>
            {renew ? (
              fixed('template', certificate?.template_name || t(`${P}noTemplate`), 'hint-template', { ref: firstField, 'data-autofocus': '' })
            ) : (
              <select id={id('template')} ref={firstField} data-autofocus="" value={d.template} aria-describedby={id('hint-template')}
                onChange={(e) => (e.target.value === SHOW_PINS
                  ? set((prev) => ({ showAllTemplates: !prev.showAllTemplates })) : applyTemplate(e.target.value))}>
                <option value="">{t(`${P}noTemplate`)}</option>
                {listedTemplates.map((tpl) => <option key={tpl.id} value={String(tpl.id)}>{tpl.name}</option>)}
                {hasPinned && d.ca_id && (
                  <option value={SHOW_PINS}>
                    {d.showAllTemplates ? t('templates.showPinnedOnly') : t('templates.showAllTemplates', { count: offeredTemplates.length })}
                  </option>
                )}
              </select>
            )}
            <small id={id('hint-template')}>
              {renew ? t(`${P}templateRenewHint`) : (template?.description || (template ? '' : t(`${P}templateNoneHint`)))}
            </small>
          </div>
          <div className="field">
            <label htmlFor={id('ca')}>{t(`${P}authority`)}</label>
            {renew ? fixed('ca', certificate?.issuer_name || '', 'hint-ca') : (
              <select id={id('ca')} value={d.ca_id} {...errorProps('ca', 'hint-ca')}
                onChange={(e) => (e.target.value === SHOW_HIDDEN
                  ? set((prev) => ({ showHiddenCas: !prev.showHiddenCas })) : chooseCa(e.target.value))}>
                {!d.ca_id && <option value="">{t(`${P}selectCa`)}</option>}
                {issuingCas.map((ca) => <option key={ca.id} value={String(ca.id)}>{caLabel(ca)}</option>)}
                {hiddenCount > 0 && (
                  <option value={SHOW_HIDDEN}>{d.showHiddenCas ? t('cas.hideHiddenCas') : t('cas.showHiddenCas', { count: hiddenCount })}</option>
                )}
              </select>
            )}
            <small id={id('hint-ca')}>
              {renew ? t(`${P}caRenewHint`) : t(`${P}caCount`, { count: signers.length })}
            </small>
            <FieldError id={id('err-ca')} message={errors.ca} />
          </div>

          <div className="field full">
            <label htmlFor={id('cn')}>{t(`${P}commonName`)}</label>
            <input id={id('cn')} value={renew ? (certificate?.cn || certificate?.common_name || '') : d.cn} maxLength={253}
              readOnly={renew} disabled={csrMode} autoComplete="off" spellCheck="false"
              placeholder={csrMode || renew ? '' : t(serverType ? `${P}cnHostPlaceholder` : `${P}cnNamePlaceholder`)}
              {...errorProps('cn', 'hint-cn')}
              onChange={(e) => { clearError('cn'); set({ cn: e.target.value }) }} />
            <small id={id('hint-cn')}>{t(renew ? `${P}cnRenewHint` : csrMode ? `${P}cnCsrHint` : serverType ? `${P}cnHint` : `${P}cnHintName`)}</small>
            <FieldError id={id('err-cn')} message={errors.cn} />
          </div>

          <div className="field full">
            <label htmlFor={id('description')}>{t(`${P}description`)} <span className="optional">{t(`${P}optional`)}</span></label>
            {renew ? fixed('description', certificate?.descr || certificate?.description || '', 'hint-description') : (
              <input id={id('description')} value={d.description} maxLength={120} disabled={csrMode} autoComplete="off"
                placeholder={t(`${P}descriptionPlaceholder`)} aria-describedby={id('hint-description')}
                onChange={(e) => set({ description: e.target.value })} />
            )}
            <small id={id('hint-description')}>{t(renew ? `${P}descriptionRenewHint` : csrMode ? `${P}descriptionCsrHint` : `${P}descriptionHint`)}</small>
          </div>

          <fieldset className="field full">
            <legend>{t(`${P}keySource`)}</legend>
            <div className="choice-grid">
              <label className="format-option">
                <input type="radio" name={id('keySource')} value="generate" checked={renew || !csrMode}
                  onChange={() => set({ keySource: 'generate' })} />
                <span>{t(`${P}keyGenerate`)}<small>{t(renew ? `${P}keyGenerateRenewHint` : `${P}keyGenerateHint`)}</small></span>
              </label>
              {(renew || canUseCsr) && (
                <label className="format-option">
                  <input type="radio" name={id('keySource')} value="csr" checked={csrMode} disabled={renew}
                    onChange={() => { clearError('key'); set({ keySource: 'csr' }) }} />
                  <span>{t(`${P}keyCsr`)}<small>{t(renew ? `${P}keyCsrRenewHint` : `${P}keyCsrHint`)}</small></span>
                </label>
              )}
            </div>
          </fieldset>

          {csrMode && (
            <div className="field full">
              <label htmlFor={id('csr')}>{t(`${P}csr`)}</label>
              <textarea id={id('csr')} className="mono" rows={5} spellCheck="false" value={d.csr}
                placeholder="-----BEGIN CERTIFICATE REQUEST-----" {...errorProps('csr', 'hint-csr')}
                onChange={(e) => { clearError('csr'); set({ csr: e.target.value }) }} />
              <small id={id('hint-csr')}>{t(`${P}csrHint`)}</small>
              <label className="text-link">
                <input type="file" accept=".csr,.pem,.req,.txt" className="sr-only"
                  onChange={async (e) => {
                    const file = e.target.files?.[0]
                    if (file) { clearError('csr'); set({ csr: await file.text() }) }
                  }} />
                {t(`${P}csrFile`)}
              </label>
              <FieldError id={id('err-csr')} message={errors.csr} />
            </div>
          )}

          <div className="field">
            <label htmlFor={id('key')}>{t(`${P}keyAlgorithm`)}</label>
            {renew ? fixed('key', certificateKeyLabel(certificate, t) || '', 'hint-key') : (
              <select id={id('key')} value={csrMode || noKeyAllowed ? '' : (isHybrid ? hybridChoice.classical : d.key)}
                disabled={csrMode || isHybrid} {...errorProps('key', 'hint-key')}
                onChange={(e) => set({ key: e.target.value, keyBy: 'user' })}>
                {noKeyAllowed && !csrMode ? <option value="">{t(`${P}noneMasc`)}</option> : (
                  <>
                    {(csrMode || (!d.key && !isHybrid)) && <option value="">{t(csrMode ? `${P}keyFromCsr` : `${P}keyServerDefault`)}</option>}
                    {!csrMode && (isHybrid ? hybridClassical : singleLabels).map((l) => <option key={l} value={l}>{keyLabel(l, t)}</option>)}
                    {!csrMode && d.key && !isHybrid && !singleLabels.includes(d.key) && <option value={d.key}>{keyLabel(d.key, t)}</option>}
                  </>
                )}
              </select>
            )}
            <small id={id('hint-key')}>{renew ? t(`${P}keyHintRenew`) : keyHint()}</small>
            {!renew && !csrMode && !isHybrid && isBrainpool(d.key) && <small className="brainpool" role="note"><Icon name="warning" /><span>{t('common.keyGroups.brainpoolWarning')}</span></small>}
            <FieldError id={id('err-key')} message={errors.key || (noKeyAllowed && !csrMode ? t('certificates.noKeyTypeAllowedByPolicy') : '')} />
          </div>
          <div className="field">
            <div className="label-row">
              <label htmlFor={id(d.validityMode === 'date' && !renew ? 'date' : 'days')}>
                {t(d.validityMode === 'date' && !renew ? `${P}validityDate` : `${P}validityDays`)}
              </label>
              {!renew && (
                <button type="button" className="text-link" aria-label={t(d.validityMode === 'date' ? `${P}useDays` : `${P}useDate`)}
                  title={t(d.validityMode === 'date' ? `${P}useDays` : `${P}useDate`)}
                  onClick={() => { clearError('days'); set((prev) => ({ validityMode: prev.validityMode === 'date' ? 'days' : 'date' })) }}>
                  {d.validityMode === 'date' ? <Icon name="rows" /> : <Icon name="clock" />}
                </button>
              )}
            </div>
            {d.validityMode === 'date' && !renew ? (
              <input id={id('date')} type="date" value={d.expiry_date} min={today} max={caExpiry || undefined}
                {...errorProps('days', 'hint-days')}
                onChange={(e) => { clearError('days'); set({ expiry_date: e.target.value }) }} />
            ) : (
              <input id={id('days')} type="number" min="1" max={maxDays} step="1" value={d.validity_days}
                {...errorProps('days', 'hint-days')}
                onChange={(e) => { clearError('days'); set({ validity_days: e.target.value, daysBy: 'user' }) }} />
            )}
            <small id={id('hint-days')}>
              {renew
                ? t(`${P}validityRenewHint`, { max: num(MAX_DAYS), days: originalDurationDays(certificate) ? num(originalDurationDays(certificate)) : '' })
                : limit.bound
                  ? t(`${P}validityHintCa`, { max: num(maxDays), date: formatDate(caExpiry, { time: false }) })
                  : t(`${P}validityHint`, { max: num(maxDays) })}
            </small>
            <FieldError id={id('err-days')} message={errors.days} />
          </div>

          {renderSans()}
          {renderAdvanced()}
        </div>
        {renderHint()}
      </div>
      </div>
      <p className="form-announce" role="status" aria-live="polite">{announce}</p>
      <div className="modal-actions">
        <button type="button" className="btn" onClick={onCancel}>{t('common.cancel')}</button>
        <button type="submit" className="btn primary" disabled={reviewing}>
          {t(`${P}toReview`)}<Icon name="right" />
        </button>
      </div>
    </form>
  )

  function advancedSummary() {
    if (renew) return t(`${P}advancedHintRenew`)
    // Folded, the line says when the template fills something in the panel
    return t(Object.keys(templateSubject(template)).length ? `${P}advancedHintTemplate` : `${P}advancedHint`)
  }

  function renderAdvanced() {
    const extras = d.extra_ekus.filter((oid) => !COMMON_EKUS.some(([, o]) => o === oid))
    return (
      <div className="field full advanced">
        <button type="button" className="advanced-toggle" aria-expanded={d.advanced} aria-controls={id('advanced')}
          onClick={() => set((prev) => ({ advanced: !prev.advanced }))}>
          {d.advanced ? <Icon name="down" /> : <Icon name="right" />}
          <span>{t(`${P}advanced`)}</span><small>{advancedSummary()}</small>
        </button>
        <div className="advanced-panel" id={id('advanced')} hidden={!d.advanced}>
          {renew ? renderAdvancedRenew() : (
            <>
              <div className="field">
                <label htmlFor={id('certType')}>{t('certificates.certType')}</label>
                <select id={id('certType')} value={d.cert_type} disabled={!!template} aria-describedby={id('hint-certType')}
                  onChange={(e) => set({ cert_type: e.target.value })}>
                  {Object.entries(CERT_TYPE_KEYS).map(([value, key]) => <option key={value} value={value}>{t(`certificates.certType${key}`)}</option>)}
                </select>
                <small id={id('hint-certType')}>{template ? t('certificates.certTypeFromTemplate') : t(`${P}certTypeHint`)}</small>
                {!csrMode && (
                  <label className="checkbox-line">
                    <input type="checkbox" checked={d.ocsp_must_staple} onChange={(e) => set({ ocsp_must_staple: e.target.checked })} />
                    <span>{t('certificates.ocspMustStaple')}</span>
                  </label>
                )}
              </div>
              <fieldset className="field">
                <legend>{t(`${P}ekus`)}</legend>
                <div className="eku-list">
                  {[...COMMON_EKUS.map(([, oid]) => oid), ...extras].map((oid) => {
                    // The template or the type sets it: shown ticked, it cannot be taken off (the API only adds)
                    const locked = defaultEkus.includes(oid)
                    return (
                      <label className="checkbox-line" key={oid}>
                        <input type="checkbox" value={oid} checked={locked || d.extra_ekus.includes(oid)}
                          aria-disabled={locked ? 'true' : undefined} aria-describedby={locked ? id('hint-ekus') : undefined}
                          onClick={(e) => { if (locked) e.preventDefault() }}
                          onChange={(e) => { if (!locked) toggleEku(oid, e.target.checked) }} />
                        <span>{ekuLabel(oid)}<small className="mono">{oid}</small></span>
                      </label>
                    )
                  })}
                </div>
                <div className="inline-row">
                  <label className="sr-only" htmlFor={id('oid')}>{t(`${P}otherOid`)}</label>
                  <input id={id('oid')} className="mono" value={customOid} placeholder={t(`${P}otherOid`)} autoComplete="off" spellCheck="false"
                    aria-invalid={customOidError ? 'true' : undefined} aria-describedby={customOidError ? id('err-oid') : undefined}
                    onChange={(e) => { setCustomOid(e.target.value); setCustomOidError('') }}
                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addCustomOid() } }} />
                  <button type="button" className="btn" onClick={addCustomOid}>{t(`${P}addOid`)}</button>
                </div>
                <FieldError id={id('err-oid')} message={customOidError} />
                <small id={id('hint-ekus')}>{defaultEkus.length
                  ? t(template ? `${P}ekusFromTemplate` : `${P}ekusFromType`, { list: defaultEkus.map(ekuLabel).join(', ') })
                  : t(`${P}ekusNone`)}</small>
              </fieldset>

              {!csrMode && (
                <fieldset className="field full">
                  <legend>{t(`${P}subject`)}</legend>
                  <small>{t(`${P}subjectHint`)}</small>
                  <div className="subject-grid">
                    {SUBJECT_FIELDS.map(([key, label, max]) => (
                      <div className="field" key={key}>
                        <label htmlFor={id(`subject-${key}`)}>{t(label)}</label>
                        <input id={id(`subject-${key}`)} value={d.subject[key]} maxLength={max} autoComplete="off"
                          type={key === 'email' ? 'email' : 'text'} onChange={(e) => setSubject(key, e.target.value)} />
                      </div>
                    ))}
                  </div>
                </fieldset>
              )}

              {!csrMode && hybridAvailable && (
                <fieldset className="field full">
                  <legend>{t(`${P}hybrid`)}</legend>
                  <label className="checkbox-line">
                    <input type="checkbox" checked={d.hybrid} onChange={(e) => set({ hybrid: e.target.checked })} />
                    <span>{t('certificates.hybrid.toggle')}</span>
                  </label>
                  <small>{t('certificates.hybrid.toggleHint')}</small>
                  {isHybrid && (
                    <div className="subject-grid">
                      <div className="field">
                        <label htmlFor={id('hybrid-classical')}>{t('certificates.hybrid.classical')}</label>
                        <select id={id('hybrid-classical')} value={hybridChoice.classical} onChange={(e) => set({ hybrid_classical: e.target.value })}>
                          {hybridClassical.map((l) => <option key={l} value={l}>{keyLabel(l, t)}</option>)}
                        </select>
                      </div>
                      <div className="field">
                        <label htmlFor={id('hybrid-pq')}>{t('certificates.hybrid.pq')}</label>
                        <select id={id('hybrid-pq')} value={hybridChoice.pq} onChange={(e) => set({ hybrid_pq: e.target.value })}>
                          {hybridPq.map((l) => <option key={l} value={l}>{keyLabel(l, t)}</option>)}
                        </select>
                      </div>
                    </div>
                  )}
                </fieldset>
              )}

              <fieldset className="field full">
                <legend>{t('customExtensions.title')}</legend>
                <small id={id('hint-ext')}>{`${t(`${P}extHint`)} ${template ? t('customExtensions.requestHint') : ''}`.trim()}</small>
                <div className="row-list">
                  {d.customExt.map((row, i) => (
                    <div className="ext-row" key={i}>
                      <label className="sr-only" htmlFor={id(`ext-oid-${i}`)}>{t(`${P}extOid`, { n: i + 1 })}</label>
                      <input id={id(`ext-oid-${i}`)} className="mono" name="extOid" value={row.oid} placeholder="1.3.6.1.4.1.32473.1"
                        autoComplete="off" spellCheck="false" inputMode="decimal" {...errorProps(`ext-${i}`, 'hint-ext')}
                        onChange={(e) => updateExt(i, { oid: e.target.value })} />
                      <label className="sr-only" htmlFor={id(`ext-value-${i}`)}>{t(`${P}extValue`, { n: i + 1 })}</label>
                      <input id={id(`ext-value-${i}`)} className="mono" name="extValue" value={row.value} placeholder={t(`${P}extValuePlaceholder`)}
                        autoComplete="off" spellCheck="false" {...errorProps(`extv-${i}`)} onChange={(e) => updateExt(i, { value: e.target.value })} />
                      <label className="checkbox-line ext-critical">
                        <input type="checkbox" checked={row.critical} onChange={(e) => updateExt(i, { critical: e.target.checked })} />
                        <span>{t('customExtensions.critical')}</span>
                      </label>
                      <button type="button" className="icon-btn" aria-label={t(`${P}removeExt`, { n: i + 1 })} onClick={() => removeExt(i)}>
                        <Icon name="close" />
                      </button>
                      <FieldError id={id(`err-ext-${i}`)} message={errors[`ext-${i}`]} />
                      <FieldError id={id(`err-extv-${i}`)} message={errors[`extv-${i}`]} />
                    </div>
                  ))}
                </div>
                {d.customExt.some((r) => r.critical) && (
                  <p className="notice warn" data-testid="custom-extensions-critical-warning">
                    <Icon name="warning" /><span>{t('customExtensions.criticalWarning')}</span>
                  </p>
                )}
                <button type="button" id={id('ext-add')} className="btn quiet add-row" onClick={addExt}>
                  <Icon name="plus" />{t('customExtensions.add')}
                </button>
              </fieldset>
            </>
          )}
        </div>
      </div>
    )
  }

  // What a renewal carries over unchanged (the server re-signs the same subject and extensions), in the
  // places of the Atelier's Advanced panel: hash and EKU side by side, then the custom extensions
  function renderAdvancedRenew() {
    const usages = certificate?.extensions?.extended_key_usage?.usages
    const ekus = Array.isArray(usages) ? usages.map((u) => u?.oid).filter(Boolean)
      : (EKU_DEFAULTS_BY_TYPE[certificateType(certificate)] || [])
    // An EKU outside the five common ones is named as the inspector names it, its OID beneath
    const named = (oid) => {
      if (EKU_NAME[oid]) return ekuLabel(oid)
      const name = (usages || []).find((u) => u?.oid === oid)?.name
      return name && name !== oid ? extKeyUsageName(name) : oid
    }
    const listed = [...COMMON_EKUS.map(([, oid]) => oid), ...ekus.filter((oid) => !EKU_NAME[oid])]
    const others = (certificate?.extensions?.other_extensions || []).filter((x) => x?.oid && x.oid !== MUST_STAPLE_OID)
    return (
      <>
        <div className="field">
          <label htmlFor={id('hash')}>{t(`${P}hash`)}</label>
          {fixed('hash', certificateHash(certificate) || '', 'hint-hash')}
          <small id={id('hint-hash')}>{t(`${P}hashRenewHint`)}</small>
          {certificate?.ocsp_must_staple && (
            <label className="checkbox-line">
              <input type="checkbox" checked readOnly aria-disabled="true" onClick={(e) => e.preventDefault()} />
              <span>{t('certificates.ocspMustStaple')}</span>
            </label>
          )}
        </div>
        <fieldset className="field">
          <legend>{t(`${P}ekus`)}</legend>
          <div className="eku-list">
            {listed.map((oid) => (
              <label className="checkbox-line" key={oid}>
                {/* Controlled without a change: React puts the box back as the certificate has it */}
                <input type="checkbox" value={oid} checked={ekus.includes(oid)} aria-disabled="true"
                  aria-describedby={id('hint-ekus')} onChange={() => {}} />
                <span>{named(oid)}{named(oid) !== oid && <small className="mono">{oid}</small>}</span>
              </label>
            ))}
          </div>
          <small id={id('hint-ekus')}>{ekus.length ? t(`${P}ekusRenew`, { list: ekus.map(named).join(', ') }) : t(`${P}ekusNone`)}</small>
        </fieldset>
        <fieldset className="field full">
          <legend>{t('customExtensions.title')}</legend>
          <small id={id('hint-ext')}>{t(`${P}extRenewHint`)}</small>
          <div className="row-list">
            {others.map((x, i) => (
              <div className="ext-row fixed" key={x.oid}>
                <label className="sr-only" htmlFor={id(`ext-oid-${i}`)}>{t(`${P}extOid`, { n: i + 1 })}</label>
                {fixed(`ext-oid-${i}`, x.oid, 'hint-ext', { className: 'mono', name: 'extOid', title: x.name || undefined })}
                <label className="sr-only" htmlFor={id(`ext-value-${i}`)}>{t(`${P}extValue`, { n: i + 1 })}</label>
                {fixed(`ext-value-${i}`, x.value_hex || '', x.critical ? 'ext-critical' : null, { name: 'extValue' })}
                <button type="button" className="icon-btn" disabled aria-label={t(`${P}removeExt`, { n: i + 1 })}>
                  <Icon name="close" />
                </button>
              </div>
            ))}
          </div>
          {others.some((x) => x.critical) && <small id={id('ext-critical')}>{t(`${P}extRenewCritical`)}</small>}
          <button type="button" className="btn quiet add-row" disabled aria-describedby={id('hint-ext')}>
            <Icon name="plus" />{t('customExtensions.add')}
          </button>
        </fieldset>
        {renewSubject.length > 0 && (
          <fieldset className="field full">
            <legend>{t(`${P}subject`)}</legend>
            <div className="subject-grid">
              {SUBJECT_FIELDS.filter(([key]) => certificate?.[key]).map(([key, label]) => (
                <div className={`field${String(certificate[key]).length > 24 ? ' wide' : ''}`} key={key}>
                  <label htmlFor={id(`subject-${key}`)}>{t(label)}</label>
                  {fixed(`subject-${key}`, certificate[key], null, { title: certificate[key] })}
                </div>
              ))}
            </div>
          </fieldset>
        )}
      </>
    )
  }

  const renderReview = () => {
    const defaults = { cert_type: template ? (TYPE_MAP[template.template_type] || 'custom') : 'server', subject: templateSubject(template) }
    const { title, rows } = describeRequest(request, {
      t, templates: offeredTemplates, cas, certificate, ekuLabel, defaultEkus, defaults,
    })
    const fields = new Set(rows.flatMap((r) => r.fields))
    const action = request.kind === 'renew' ? `${P}renewAction` : request.kind === 'csr' ? `${P}signAction` : `${P}issueAction`
    return (
      <>
        <div className="review-summary" data-testid="issue-review" data-fields={[...fields].join(' ')}>
          <h3 ref={reviewTitle} tabIndex={-1}>{title}</h3>
          <dl className="props">
            {rows.map((r) => (
              <Fragment key={r.id}>
                <dt data-row={r.id}>{r.label}</dt>
                <dd className={r.lines.some((l) => l.mono) ? 'mono' : undefined}>
                  {r.lines.map((l, i) => (
                    <Fragment key={i}>{i > 0 && <br />}{l.muted === true ? <span className="muted">{l.text}</span> : l.text}
                      {typeof l.muted === 'string' && l.muted && <span className="muted">{l.muted}</span>}</Fragment>
                  ))}
                </dd>
              </Fragment>
            ))}
          </dl>
        </div>
        {approval !== null ? (
          <div className="notice warn" style={{ marginTop: 18, marginBottom: 0 }} role="status" data-testid="approval-sent">
            <Icon name="warning" />
            <span>{t(request.kind === 'renew' ? `${P}approvalSentRenew` : `${P}approvalSent`, { policy: approval })}</span>
          </div>
        ) : (
          <div className="notice" style={{ marginTop: 18, marginBottom: 0 }}>
            <Icon name="help" />
            <span>{t(request.kind === 'renew' ? `${P}reviewNoteRenew` : `${P}reviewNote`)}</span>
          </div>
        )}
        {submitError && (
          <div className="notice bad" style={{ marginTop: 18, marginBottom: 0 }} role="alert" data-testid="issue-error">
            <Icon name="warning" /><span>{submitError}</span>
          </div>
        )}
        <span className="sr-only" role="status">{issuing ? t(`${P}issuing`) : ''}</span>
        <div className="modal-actions">
          {approval !== null ? (
            <button type="button" className="btn primary" onClick={onCancel}>{t('common.close')}</button>
          ) : (
            <>
              <button type="button" className="btn" onClick={back} disabled={issuing}>
                <Icon name="left" />{t(`${P}back`)}
              </button>
              {/* Its words stay while the request is out, so Modify does not slide; the wait is told aloud */}
              <button type="button" ref={submitButton} className="btn primary" onClick={issue} disabled={issuing}
                aria-busy={issuing ? 'true' : undefined} data-testid="issue-submit">
                <Icon name="check" />{t(action)}
              </button>
            </>
          )}
        </div>
      </>
    )
  }

  return (
    <>
      <Steps step={step} t={t} />
      {step === 1 || !request ? renderConfigure() : renderReview()}
    </>
  )
}

function extOf(tpl) {
  let value = tpl?.extensions_template
  if (typeof value === 'string') { try { value = JSON.parse(value) } catch { value = null } }
  return value || {}
}
