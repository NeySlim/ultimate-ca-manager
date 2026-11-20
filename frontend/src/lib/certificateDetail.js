/**
 * What the certificate inspector shows, worked out from the detail the API returns:
 * the validity band, the chain from the anchor down to the certificate, the X.509
 * extensions as label, OID and value, and the history of the object.
 */
import { daysRemaining } from './utils'
import { keyAlgorithmLabel } from './keyAlgorithms'

const EC_CURVES = { secp256r1: 'P-256', prime256v1: 'P-256', secp384r1: 'P-384', secp521r1: 'P-521' }

/** Key of a certificate as people name it: "RSA 3072", "ECDSA P-256", a post-quantum name with its level. */
export function certificateKeyLabel(cert, t) {
  const type = String(cert?.key_type || '').trim()
  const ec = /^EC\s+(\S+)$/i.exec(type)
  if (ec) return `ECDSA ${EC_CURVES[ec[1].toLowerCase()] || ec[1]}`
  if (/^RSA\s+\d+$/i.test(type)) return type
  return keyAlgorithmLabel(cert?.key_algorithm || cert?.key_algo || type, t, cert?.security_level) || type || null
}

const toMs = (d) => {
  if (!d) return null
  const ms = new Date(d).getTime()
  return Number.isNaN(ms) ? null : ms
}

/** State, days left, share of the validity left (0 to 100) and the two dates. */
export function validityFacts(cert, now = new Date()) {
  const from = toMs(cert?.valid_from)
  const to = toMs(cert?.valid_to)
  const state = cert?.revoked ? 'revoked' : (cert?.status || 'valid')
  const days = to === null ? null : daysRemaining(cert.valid_to, now)
  const span = from !== null && to !== null ? to - from : 0
  const left = to === null ? 0 : to - new Date(now).getTime()
  const ratio = span > 0 ? Math.max(0, Math.min(100, (left / span) * 100)) : 0
  return { state, days, ratio, from: cert?.valid_from || null, to: cert?.valid_to || null, short: days !== null && days >= 0 && days < 30 }
}

/**
 * The chain from its top down to the certificate's issuer, as the API names it
 * (issuer first): role root for the anchor of a complete chain, intermediate otherwise.
 */
export function chainNodes(cert) {
  const status = cert?.chain_status
  const links = Array.isArray(status?.chain) ? status.chain : []
  const top = [...links].reverse()
  return top.map((link, i) => {
    const anchor = i === 0 && status.status === 'complete'
    return {
      name: link.name,
      type: link.type,
      role: anchor ? (link.type === 'trust_store' ? 'anchor' : 'root') : 'intermediate',
      level: i + 1,
      issuing: i === top.length - 1,
      cross: link.cross_certificate_id != null,
    }
  })
}

const OID = {
  subject_alt_names: '2.5.29.17',
  basic_constraints: '2.5.29.19',
  key_usage: '2.5.29.15',
  extended_key_usage: '2.5.29.37',
  subject_key_identifier: '2.5.29.14',
  authority_key_identifier: '2.5.29.35',
  crl_distribution_points: '2.5.29.31',
  authority_info_access: '1.3.6.1.5.5.7.1.1',
  certificate_policies: '2.5.29.32',
  name_constraints: '2.5.29.30',
  signed_certificate_timestamps: '1.3.6.1.4.1.11129.2.4.2',
  qc_statements: '1.3.6.1.5.5.7.1.3',
}

/** One row per extension: i18n label key (or name), OID, criticality and value lines. */
export function extensionRows(ext, sanCombined) {
  const rows = []
  const add = (key, labelKey, lines, critical) => {
    const values = [].concat(lines).filter((v) => v !== null && v !== undefined && v !== '')
    if (values.length) rows.push({ key, labelKey, oid: OID[key], critical: !!critical, values })
  }
  const e = ext || {}
  const sans = e.subject_alt_names?.entries
  if (sans?.length) add('subject_alt_names', 'details.subjectAltNames', sans.map((s) => `${s.type}: ${s.value}`), e.subject_alt_names.critical)
  else if (sanCombined) add('subject_alt_names', 'details.subjectAltNames', sanCombined.split(',').map((s) => s.trim()))
  if (e.basic_constraints) {
    const bc = e.basic_constraints
    add('basic_constraints', 'details.ext.basicConstraints',
      `CA: ${bc.ca ? 'TRUE' : 'FALSE'}${bc.path_length !== null && bc.path_length !== undefined ? `, pathLen: ${bc.path_length}` : ''}`, bc.critical)
  }
  if (e.key_usage) add('key_usage', 'details.ext.keyUsage', (e.key_usage.usages || []).join(', '), e.key_usage.critical)
  if (e.extended_key_usage) add('extended_key_usage', 'details.ext.extKeyUsage', (e.extended_key_usage.usages || []).map((u) => u.name || u.oid), e.extended_key_usage.critical)
  if (e.subject_key_identifier) add('subject_key_identifier', 'details.ext.ski', e.subject_key_identifier.value)
  if (e.authority_key_identifier) add('authority_key_identifier', 'details.ext.aki', e.authority_key_identifier.key_id)
  if (e.authority_info_access) {
    const aia = e.authority_info_access
    add('authority_info_access', 'details.ext.aia', [
      ...(aia.ocsp || []).map((u) => `OCSP: ${u}`),
      ...(aia.ca_issuers || []).map((u) => `CA Issuers: ${u}`),
    ])
  }
  if (e.crl_distribution_points?.urls?.length) add('crl_distribution_points', 'details.ext.crlDP', e.crl_distribution_points.urls)
  if (e.certificate_policies?.policies?.length) {
    add('certificate_policies', 'details.ext.policies', e.certificate_policies.policies.map((p) =>
      [p.name || p.oid, ...(p.qualifiers || []).map((q) => q.value)].join(' ')))
  }
  if (e.name_constraints) {
    const nc = e.name_constraints
    add('name_constraints', 'details.ext.nameConstraints', [
      nc.permitted?.length ? `Permitted: ${nc.permitted.join(', ')}` : null,
      nc.excluded?.length ? `Excluded: ${nc.excluded.join(', ')}` : null,
    ], nc.critical)
  }
  if (e.qc_statements) {
    const qc = e.qc_statements
    add('qc_statements', 'details.ext.qcStatements', [
      qc.compliance ? 'QcCompliance' : null,
      qc.sscd ? 'QcSSCD' : null,
      qc.type ? `QcType: ${[].concat(qc.type).join(', ')}` : null,
      qc.semantics ? `Semantics: ${qc.semantics}` : null,
      qc.cc_legislation?.length ? `QcCClegislation: ${qc.cc_legislation.join(', ')}` : null,
      qc.retention_period != null ? `QcRetentionPeriod: ${qc.retention_period}` : null,
      ...(qc.pds || []).map((p) => `QcPDS ${p.language}: ${p.url}`),
    ], qc.critical)
  }
  if (e.signed_certificate_timestamps) add('signed_certificate_timestamps', 'details.ext.sct', 'Present', e.signed_certificate_timestamps.critical)
  for (const o of e.other_extensions || []) {
    rows.push({ key: `other-${o.oid}`, label: o.name || o.oid, oid: o.oid, critical: !!o.critical, values: o.value_hex ? [o.value_hex] : [], hex: true })
  }
  return rows
}

/**
 * History of the certificate, newest first: the dates its record carries, then the
 * audit entries whose resource is this certificate (each audit action once per minute).
 */
export function historyEntries(cert, logs = []) {
  const out = []
  if (cert?.created_at) {
    const imported = ['import', 'imported', 'upload'].includes(cert.source)
    out.push({ id: 'created', at: cert.created_at, kind: imported ? 'imported' : 'issued', actor: cert.created_by || '', ok: true })
  }
  if (cert?.renewed_at) out.push({ id: 'renewed', at: cert.renewed_at, kind: 'renewed', actor: '', ok: true })
  if (cert?.revoked && cert?.revoked_at) out.push({ id: 'revoked', at: cert.revoked_at, kind: 'revoked', actor: '', reason: cert.revoke_reason, ok: true })
  const mine = (logs || []).filter((l) => String(l.resource_id) === String(cert?.id) && (!l.resource_type || l.resource_type === 'certificate'))
  const audit = mine.map((l) => ({ id: `audit-${l.id}`, at: l.timestamp, kind: 'audit', action: l.action || '', details: l.details, actor: l.username || '', ok: l.success !== false }))
  // A record date the audit log also holds (same operation within two minutes) is shown once, as the audit entry
  const WORD = { issued: /creat|issu/, imported: /import/, renewed: /renew/, revoked: /revok/ }
  const told = (e) => audit.some((a) => WORD[e.kind]?.test(a.action) && Math.abs((toMs(a.at) || 0) - (toMs(e.at) || 0)) <= 120000)
  return [...out.filter((e) => !told(e)), ...audit].sort((a, b) => (toMs(b.at) || 0) - (toMs(a.at) || 0))
}

/** The latest failed ACME client order of this certificate, or null. */
export function lastAcmeFailure(cert, orders = []) {
  const id = cert?.id
  const failed = (orders || []).filter((o) => (o.certificate_id === id || o.source_certificate_id === id)
    && o.error_message && (o.last_error_at || o.status === 'invalid' || o.status === 'failed'))
  failed.sort((a, b) => (toMs(b.last_error_at || b.created_at) || 0) - (toMs(a.last_error_at || a.created_at) || 0))
  const f = failed[0]
  if (!f) return null
  // A failure older than the certificate's own renewal is settled
  if (cert?.renewed_at && toMs(f.last_error_at) !== null && toMs(f.last_error_at) < toMs(cert.renewed_at)) return null
  return f
}

