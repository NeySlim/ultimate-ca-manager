/**
 * The rows of the Review step, read from the request about to be sent: every field of its
 * body is named by the `fields` of one row, so the step shows exactly what the server gets.
 */
import { findAlgorithm } from '../../../lib/keyAlgorithms'
import { issueKeyLabel } from '../../../lib/policyAlgorithms'
import { formatDate } from '../../../lib/utils'

export const SAN_FIELDS = [['san_dns', 'DNS'], ['san_ip', 'IP'], ['san_email', 'Email'], ['san_uri', 'URI'], ['san_upn', 'UPN']]
const SUBJECT_FIELDS = [['country', 'C'], ['state', 'ST'], ['locality', 'L'], ['organization', 'O'], ['organizational_unit', 'OU'], ['email', 'E']]
const P = 'certificates.issueForm.'

export const keyDisplay = (label) => findAlgorithm(label)?.display || label || ''

const DAY_MS = 86400000
export const endDate = (days, now = Date.now()) => formatDate(new Date(now + Number(days) * DAY_MS), { time: false })

const caName = (ca) => ca?.descr || ca?.common_name || ca?.name || ''

/** "Services CA · level 2, under Example Root CA" parts for a CA of *cas*. */
function caLine(caId, cas, t) {
  const byId = new Map((cas || []).map((c) => [String(c.id), c]))
  const ca = byId.get(String(caId))
  if (!ca) return { text: String(caId ?? '') }
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

/**
 * Rows `{ id, label, lines: [{ text, muted? }], fields }` for *request*
 * (`{ kind: 'issue' | 'csr' | 'renew', body, csrInfo? }`).
 */
export function describeRequest(request, { t, templates = [], cas = [], certificate = null, now = Date.now() }) {
  const { kind, body = {}, csrInfo = null } = request
  const rows = []
  const row = (id, label, lines, fields = []) => rows.push({ id, label, lines: [].concat(lines), fields })
  const none = (key) => ({ text: t(key), muted: true })

  if (kind === 'renew') {
    const original = certificate?.valid_from && certificate?.valid_to
      ? Math.floor((Date.parse(certificate.valid_to) - Date.parse(certificate.valid_from)) / DAY_MS) : null
    row('operation', t(`${P}operation`), { text: t(`${P}operationRenew`) })
    row('template', t(`${P}template`), certificate?.template_name ? { text: certificate.template_name } : none(`${P}none`))
    row('ca', t(`${P}authority`), { text: certificate?.issuer_name || '' })
    row('keySource', t(`${P}keySource`), { text: t(`${P}keySourceRenew`) })
    row('key', t(`${P}keyAlgorithm`), { text: certificate?.key_algorithm || certificate?.key_type || '' })
    row('validity', t(`${P}validity`), body.validity_days != null
      ? { text: t(`${P}validityUntil`, { days: body.validity_days, date: endDate(body.validity_days, now) }) }
      : { text: original ? t(`${P}validityOriginal`, { days: original }) : t(`${P}validityOriginalUnknown`) },
    ['validity_days'])
    const names = SAN_FIELDS.flatMap(([field, type]) => listOf(certificate?.[field]).map((v) => `${type} : ${v}`))
    row('sans', t(`${P}sans`), names.length ? names.map((text) => ({ text })) : none(`${P}noneMasc`))
    row('advanced', t(`${P}advanced`), { text: t(`${P}advancedRenew`) })
    return { title: certificate?.cn || certificate?.common_name || '', rows }
  }

  const template = templates.find((tpl) => String(tpl.id) === String(body.template_id))
  row('operation', t(`${P}operation`), { text: t(kind === 'csr' ? `${P}operationCsr` : `${P}operationIssue`) })
  row('template', t(`${P}template`), template ? { text: template.name } : (body.template_id ? { text: `#${body.template_id}` } : none(`${P}none`)), ['template_id'])
  row('ca', t(`${P}authority`), caLine(body.ca_id, cas, t), ['ca_id'])
  if (kind === 'issue') {
    row('description', t(`${P}description`), body.description ? { text: body.description } : none(`${P}noneFem`), ['description'])
    const subject = SUBJECT_FIELDS.filter(([field]) => body[field]).map(([field, short]) => `${short}=${body[field]}`)
    if (subject.length) row('subject', t(`${P}subject`), { text: subject.join(', ') }, SUBJECT_FIELDS.map(([f]) => f))
  }
  row('certType', t(`${P}certType`), { text: t(`certificates.certType${CERT_TYPE_KEYS[body.cert_type] || 'Custom'}`) }, ['cert_type'])
  row('keySource', t(`${P}keySource`), { text: t(kind === 'csr' ? `${P}keySourceCsr` : `${P}keySourceGenerate`) })
  if (kind === 'csr') {
    row('key', t(`${P}keyAlgorithm`), { text: csrInfo?.key || t(`${P}keyFromCsr`) })
  } else if (body.hybrid) {
    row('key', t(`${P}keyAlgorithm`), { text: t(`${P}hybridPair`, { classical: keyDisplay(body.hybrid.classical), pq: keyDisplay(body.hybrid.pq) }) },
      ['key_type', 'key_size', 'hybrid'])
  } else {
    const label = issueKeyLabel(body.key_type, body.key_size)
    row('key', t(`${P}keyAlgorithm`), body.key_type ? { text: keyDisplay(label) || `${body.key_type} ${body.key_size ?? ''}`.trim() } : none(`${P}keyServerDefault`),
      ['key_type', 'key_size'])
  }
  row('validity', t(`${P}validity`), { text: t(`${P}validityUntil`, { days: body.validity_days, date: endDate(body.validity_days, now) }) }, ['validity_days'])
  const names = SAN_FIELDS.flatMap(([field, type]) => (body[field] || []).map((v) => `${type} : ${v}`))
  row('sans', t(`${P}sans`), names.length ? names.map((text) => ({ text })) : none(`${P}noneMasc`), SAN_FIELDS.map(([f]) => f))

  const changed = (body.extra_ekus?.length || 0) + (body.ocsp_must_staple ? 1 : 0) + (body.custom_extensions?.length || 0)
  row('advanced', t(`${P}advanced`), { text: t(changed ? `${P}advancedChanged` : (template ? `${P}advancedTemplate` : `${P}advancedDefault`)) })
  if (body.extra_ekus?.length) row('ekus', t(`${P}ekuAdded`), body.extra_ekus.map((text) => ({ text })), ['extra_ekus'])
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
