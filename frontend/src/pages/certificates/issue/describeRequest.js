/**
 * The rows of the Review step, read from the request about to be sent: every field of its
 * body is named by the `fields` of one row, so the step shows exactly what the server gets.
 */
import { certificateKeyLabel, keyLabel } from '../../../lib/certificateDetail'
import { issueKeyLabel } from '../../../lib/policyAlgorithms'
import { formatDate } from '../../../lib/utils'

export const SAN_FIELDS = [['san_dns', 'DNS'], ['san_ip', 'IP'], ['san_email', 'Email'], ['san_uri', 'URI'], ['san_upn', 'UPN']]
const SUBJECT_FIELDS = [['country', 'C'], ['state', 'ST'], ['locality', 'L'], ['organization', 'O'], ['organizational_unit', 'OU'], ['email', 'E']]
const P = 'certificates.issueForm.'


/** "SHA-256" from a signature algorithm such as "SHA256-RSA", or null (ML-DSA, EdDSA). */
export function certificateHash(cert) {
  const m = String(cert?.signature_algorithm || '').match(/SHA-?(\d{3})/i)
  return m ? `SHA-${m[1]}` : null
}

/** The issue form's type of a stored certificate ("server_cert" is "server"). */
export const certificateType = (cert) => String(cert?.cert_type || '').replace(/_cert$/, '') || 'custom'

const DAY_MS = 86400000
export const endDate = (days, now = Date.now()) => formatDate(new Date(now + Number(days) * DAY_MS), { time: false })

const caName = (ca) => ca?.descr || ca?.common_name || ca?.name || ''

/** "Services CA · level 2, under Example Root CA" parts for a CA of *cas*. */
function caLine(ca, cas, t) {
  const byId = new Map((cas || []).map((c) => [String(c.id), c]))
  const parent = ca.parent_id != null ? byId.get(String(ca.parent_id)) : null
  let level = 1
  for (let c = ca, seen = new Set(); c?.parent_id != null && !seen.has(c.id); level += 1) {
    seen.add(c.id)
    c = byId.get(String(c.parent_id))
    if (!c) break
  }
  const detail = parent
    ? t(`${P}caLevelUnder`, { level, parent: caName(parent) })
    : (ca.parent_id == null ? t(`${P}caLevel`, { level }) : '')
  return { text: caName(ca), muted: detail ? ` · ${detail}` : '' }
}

const sameSubject = (a = {}, b = {}) => SUBJECT_FIELDS.every(([f]) => (a[f] || '') === (b[f] || ''))

/**
 * Rows `{ id, label, lines: [{ text, muted? }], fields }` for *request*
 * (`{ kind: 'issue' | 'csr' | 'renew', body, csrInfo? }`). `defaults` are what the template (or no
 * template) gives the Advanced panel: `{ cert_type, subject }`; `defaultEkus` its EKU OIDs.
 */
export function describeRequest(request, {
  t, templates = [], cas = [], certificate = null, now = Date.now(), ekuLabel = (oid) => oid, defaultEkus = [], defaults = {},
}) {
  const { kind, body = {}, csrInfo = null } = request
  const rows = []
  const row = (id, label, lines, fields = []) => rows.push({ id, label, lines: [].concat(lines), fields })
  const none = (key) => ({ text: t(key), muted: true })
  const byId = (caId) => (cas || []).find((c) => String(c.id) === String(caId))

  if (kind === 'renew') {
    const original = certificate?.valid_from && certificate?.valid_to
      ? Math.floor((Date.parse(certificate.valid_to) - Date.parse(certificate.valid_from)) / DAY_MS) : null
    const issuer = (cas || []).find((c) => certificate?.caref && c.refid === certificate.caref)
    const days = body.validity_days ?? original
    row('operation', t(`${P}operation`), { text: t(`${P}operationRenew`) })
    row('template', t(`${P}template`), certificate?.template_name ? { text: certificate.template_name } : none(`${P}none`))
    row('ca', t(`${P}authority`), issuer ? caLine(issuer, cas, t) : { text: certificate?.issuer_name || '' })
    const description = certificate?.descr || certificate?.description
    row('description', t(`${P}description`), description ? { text: description } : none(`${P}noneFem`))
    row('keySource', t(`${P}keySource`), { text: t(`${P}keySourceRenew`) })
    row('key', t(`${P}keyAlgorithm`), { text: certificateKeyLabel(certificate, t) || '' })
    row('validity', t(`${P}validity`), days
      ? { text: t(`${P}validityUntil`, { days, date: endDate(days, now) }) }
      : { text: t(`${P}validityOriginalUnknown`) },
    ['validity_days'])
    const names = SAN_FIELDS.flatMap(([field, type]) => listOf(certificate?.[field]).map((v) => `${type} : ${v}`))
    row('sans', t(`${P}sans`), names.length ? names.map((text) => ({ text })) : none(`${P}noneMasc`))
    row('advanced', t(`${P}advanced`), { text: t(`${P}advancedRenew`) })
    return { title: certificate?.cn || certificate?.common_name || '', rows }
  }

  const template = templates.find((tpl) => String(tpl.id) === String(body.template_id))
  const ca = byId(body.ca_id)
  row('operation', t(`${P}operation`), { text: t(kind === 'csr' ? `${P}operationCsr` : `${P}operationIssue`) })
  row('template', t(`${P}template`), template ? { text: template.name } : (body.template_id ? { text: `#${body.template_id}` } : none(`${P}none`)), ['template_id'])
  row('ca', t(`${P}authority`), ca ? caLine(ca, cas, t) : { text: String(body.ca_id ?? '') }, ['ca_id'])
  if (kind === 'issue') {
    row('description', t(`${P}description`), body.description ? { text: body.description } : none(`${P}noneFem`), ['description'])
  }
  row('keySource', t(`${P}keySource`), { text: t(kind === 'csr' ? `${P}keySourceCsr` : `${P}keySourceGenerate`) })
  if (kind === 'csr') {
    row('key', t(`${P}keyAlgorithm`), { text: csrInfo?.key || t(`${P}keyFromCsr`) })
  } else if (body.hybrid) {
    row('key', t(`${P}keyAlgorithm`), { text: t(`${P}hybridPair`, { classical: keyLabel(body.hybrid.classical, t), pq: keyLabel(body.hybrid.pq, t) }) },
      ['key_type', 'key_size', 'hybrid'])
  } else {
    const label = issueKeyLabel(body.key_type, body.key_size)
    row('key', t(`${P}keyAlgorithm`), body.key_type ? { text: keyLabel(label, t) || `${body.key_type} ${body.key_size ?? ''}`.trim() } : none(`${P}keyServerDefault`),
      ['key_type', 'key_size'])
  }
  row('validity', t(`${P}validity`), { text: t(`${P}validityUntil`, { days: body.validity_days, date: endDate(body.validity_days, now) }) }, ['validity_days'])
  const names = SAN_FIELDS.flatMap(([field, type]) => (body[field] || []).map((v) => `${type} : ${v}`))
  row('sans', t(`${P}sans`), names.length ? names.map((text) => ({ text })) : none(`${P}noneMasc`), SAN_FIELDS.map(([f]) => f))

  // Advanced: the template's (or the default) values, or what changed, each named after it
  const subject = SUBJECT_FIELDS.filter(([field]) => body[field]).map(([field, short]) => `${short}=${body[field]}`)
  const typeChanged = defaults.cert_type != null && body.cert_type !== defaults.cert_type
  const subjectChanged = kind === 'issue' && !sameSubject(body, defaults.subject)
  const changed = typeChanged || subjectChanged || body.extra_ekus?.length || body.ocsp_must_staple || body.custom_extensions?.length
  // As in the Atelier, only what changed gets a line of its own; the rest is told by the Advanced line
  const subjectFields = SUBJECT_FIELDS.map(([f]) => f)
  const subjectShown = subject.length > 0 && (subjectChanged || kind !== 'issue')
  row('advanced', t(`${P}advanced`), {
    text: t(changed ? (template ? `${P}advancedChanged` : `${P}advancedChangedDefault`) : (template ? `${P}advancedTemplate` : `${P}advancedDefault`)),
  }, [...(typeChanged ? [] : ['cert_type']), ...(subjectShown ? [] : subjectFields)])
  if (typeChanged) row('certType', t(`${P}certType`), { text: t(`certificates.certType${CERT_TYPE_KEYS[body.cert_type] || 'Custom'}`) }, ['cert_type'])
  if (subjectShown) row('subject', t(`${P}subject`), { text: subject.join(', ') }, subjectFields)
  if (body.extra_ekus?.length) {
    const all = [...new Set([...defaultEkus, ...body.extra_ekus])]
    row('ekus', t(`${P}ekuRow`), all.map((oid) => ({ text: ekuLabel(oid) })), ['extra_ekus'])
  }
  if (body.ocsp_must_staple) row('ocsp', t('certificates.ocspMustStaple'), { text: t(`${P}yes`) }, ['ocsp_must_staple'])
  if (body.custom_extensions?.length) {
    row('extensions', t(`${P}extensions`), body.custom_extensions.map((x) => ({
      text: `${x.oid} = ${x.value}`, muted: x.critical ? ` · ${t(`${P}critical`)}` : '', mono: true,
    })), ['custom_extensions'])
  }
  const title = kind === 'csr' ? (csrInfo?.cn || csrInfo?.subject || '') : body.cn
  return { title, rows }
}

export const CERT_TYPE_KEYS = {
  server: 'Server', client: 'Client', combined: 'Combined', code_signing: 'CodeSigning', email: 'Email', custom: 'Custom',
}

/** A SAN list as stored on a certificate: an array, a JSON array, or a comma list. */
export function listOf(value) {
  if (Array.isArray(value)) return value.filter(Boolean)
  if (typeof value !== 'string' || !value.trim()) return []
  try {
    const parsed = JSON.parse(value)
    if (Array.isArray(parsed)) return parsed.filter(Boolean)
  } catch { /* a plain list */ }
  return value.split(',').map((v) => v.trim()).filter(Boolean)
}
