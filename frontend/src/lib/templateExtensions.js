/**
 * Template extensions_template helpers: qcStatements (ETSI EN 319 412-5) and
 * policy OIDs, plus a merge that keeps keys the form does not edit.
 */

export const QC_TYPES = ['esign', 'eseal', 'web']
export const QC_SEMANTICS = ['natural', 'legal', 'eidas-natural', 'eidas-legal']

// ETSI certificate policy OIDs a template can add after the CA's own policy
export const ETSI_POLICY_PRESETS = [
  { oid: '0.4.0.194112.1.0', label: 'QCP-n' },
  { oid: '0.4.0.194112.1.1', label: 'QCP-l' },
  { oid: '0.4.0.194112.1.2', label: 'QCP-n-qscd' },
  { oid: '0.4.0.194112.1.3', label: 'QCP-l-qscd' },
  { oid: '0.4.0.194112.1.4', label: 'QCP-w' },
]

export const emptyQcForm = () => ({
  compliance: false,
  cc_legislation: '',
  type: '',
  sscd: false,
  pds: [],
  retention_period: '',
  limit_currency: '',
  limit_amount: '',
  limit_exponent: '',
  semantics: '',
})

/** Form state from a stored `qc_statements` object (absent = all empty). */
export function qcFormFromStored(qc) {
  const f = emptyQcForm()
  if (!qc || typeof qc !== 'object') return f
  const lim = qc.limit_value || {}
  return {
    compliance: qc.compliance === true,
    cc_legislation: Array.isArray(qc.cc_legislation) ? qc.cc_legislation.join(', ') : '',
    type: qc.type || '',
    sscd: qc.sscd === true,
    pds: Array.isArray(qc.pds) ? qc.pds.map(p => ({ url: p?.url || '', language: p?.language || '' })) : [],
    retention_period: qc.retention_period ?? '',
    limit_currency: lim.currency || '',
    limit_amount: lim.amount ?? '',
    limit_exponent: lim.exponent ?? '',
    semantics: qc.semantics || '',
  }
}

const toInt = (v) => (v === '' || v === null || v === undefined ? null : Number.parseInt(v, 10))

/** `qc_statements` payload from the form, or null when nothing is set. */
export function qcPayloadFromForm(f) {
  if (!f) return null
  const out = {}
  if (f.compliance) out.compliance = true
  const cc = String(f.cc_legislation || '').split(/[\s,;]+/).map(s => s.trim().toUpperCase()).filter(Boolean)
  if (cc.length) out.cc_legislation = cc
  if (f.type) out.type = f.type
  if (f.sscd) out.sscd = true
  const pds = (f.pds || [])
    .map(p => ({ url: (p.url || '').trim(), language: (p.language || '').trim().toLowerCase() }))
    .filter(p => p.url || p.language)
  if (pds.length) out.pds = pds
  const ret = toInt(f.retention_period)
  if (ret !== null && !Number.isNaN(ret)) out.retention_period = ret
  const cur = String(f.limit_currency || '').trim().toUpperCase()
  const amount = toInt(f.limit_amount)
  const exponent = toInt(f.limit_exponent)
  if (cur || amount !== null || exponent !== null) {
    out.limit_value = { currency: cur, amount: amount ?? 0, exponent: exponent ?? 0 }
  }
  if (f.semantics) out.semantics = f.semantics
  return Object.keys(out).length ? out : null
}

/** Dotted OIDs from free text (one per line, comma or space separated). */
export function parsePolicyOids(text) {
  const seen = []
  for (const tok of String(text || '').split(/[\s,;]+/)) {
    const v = tok.trim()
    if (v && !seen.includes(v)) seen.push(v)
  }
  return seen
}

/**
 * extensions_template to submit: the stored object with the edited keys
 * replaced, so keys this form does not know survive an edit.
 */
export function buildExtensionsTemplate(existing, { key_usage, extended_key_usage, san_types, qc, policy_oids }) {
  const out = {
    ...(existing && typeof existing === 'object' ? existing : {}),
    key_usage,
    extended_key_usage,
    basic_constraints: { ca: false },
    san_types,
  }
  const qcPayload = qcPayloadFromForm(qc)
  if (qcPayload) out.qc_statements = qcPayload
  else delete out.qc_statements
  const oids = parsePolicyOids(policy_oids)
  if (oids.length) out.certificate_policies = oids
  else delete out.certificate_policies
  return out
}
