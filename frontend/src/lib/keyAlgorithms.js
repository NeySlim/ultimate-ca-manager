/**
 * Key algorithm registry: one row per key the product can generate or accept.
 * Forms read their lists from here; mirror of backend utils/key_algorithms.py.
 */

export const GROUP_RSA = 'rsa'
export const GROUP_NIST = 'nist'
export const GROUP_BRAINPOOL = 'brainpool'
export const GROUP_EDDSA = 'eddsa'
export const GROUP_PQ = 'pq'

// Export formats (ExportModal keys) UCM cannot yet write a post-quantum key into: PKCS#12 and JKS.
// Stored as an exclusion so a format the dialog adds stays open to every other key.
export const PQ_EXPORT_EXCLUDED = ['pkcs12', 'jks']

// Heading of each group, as an i18n key
export const KEY_GROUPS = [
  { id: GROUP_RSA, labelKey: 'common.keyGroups.rsa' },
  { id: GROUP_NIST, labelKey: 'common.keyGroups.nist' },
  { id: GROUP_BRAINPOOL, labelKey: 'common.keyGroups.brainpool' },
  { id: GROUP_EDDSA, labelKey: 'common.keyGroups.eddsa' },
  { id: GROUP_PQ, labelKey: 'common.keyGroups.pq' },
]

const rsa = (bits) => ({
  label: `RSA-${bits}`, bits, family: 'RSA', group: GROUP_RSA, display: `RSA ${bits}`,
  securityLevel: null, digest: 'sha256', fips: true, generate: true, providers: null,
  issue: ['rsa', String(bits)], ca: ['RSA', String(bits)], csr: `RSA ${bits}`,
  curveParam: null, i18nKey: `common.keyTypes.rsa${bits}`,
  sizeKey: `certificates.keySizeRsa${bits}`, csrKey: `csrs.keyRsa${bits}`, exportExcluded: [],
})

const nist = (bits, curve, digest) => ({
  label: `EC-P${bits}`, bits, family: 'EC', group: GROUP_NIST, display: `ECDSA P-${bits}`,
  securityLevel: null, digest, fips: true, generate: true, providers: null,
  issue: ['ecdsa', String(bits)], ca: ['ECDSA', curve], csr: `EC P-${bits}`,
  curveParam: `P-${bits}`, i18nKey: `common.keyTypes.ecdsaP${bits}`,
  sizeKey: `certificates.keyCurveNistP${bits}`, csrKey: `csrs.keyCurveNistP${bits}`, exportExcluded: [],
})

// Brainpool: provider-side generation is PKCS#11 only
const brainpool = (bits) => ({
  label: `EC-BP${bits}`, bits, family: 'EC', group: GROUP_BRAINPOOL, display: `Brainpool P${bits}r1`,
  securityLevel: null, digest: `sha${bits}`, fips: false, generate: true, providers: ['pkcs11'],
  issue: ['ecdsa', `brainpoolP${bits}r1`], ca: ['ECDSA', `brainpoolP${bits}r1`], csr: `EC-BP${bits}`,
  curveParam: `brainpoolP${bits}r1`, i18nKey: null, sizeKey: null, csrKey: null, exportExcluded: [],
})

// EdDSA keys only arrive through CSRs and enrollment protocols (generate: false)
const eddsa = (label, i18nKey) => ({
  label, bits: null, family: 'EDDSA', group: GROUP_EDDSA, display: label === 'ED25519' ? 'Ed25519' : 'Ed448',
  securityLevel: null, digest: null, fips: false, generate: false, providers: null,
  issue: null, ca: null, csr: null, curveParam: null, i18nKey, sizeKey: null, csrKey: null,
  exportExcluded: [],
})

// ML-DSA (FIPS 204): read and named in policies, not generated yet (generate: false)
const mldsa = (param, securityLevel) => ({
  label: `ML-DSA-${param}`, bits: null, family: 'ML-DSA', group: GROUP_PQ, display: `ML-DSA-${param}`,
  securityLevel, digest: null, fips: false, generate: false, providers: null,
  issue: null, ca: null, csr: null, curveParam: null, i18nKey: null, sizeKey: null, csrKey: null,
  exportExcluded: PQ_EXPORT_EXCLUDED,
})

export const KEY_ALGORITHMS = [
  rsa(2048), rsa(3072), rsa(4096),
  nist(256, 'prime256v1', 'sha256'), nist(384, 'secp384r1', 'sha384'), nist(521, 'secp521r1', 'sha512'),
  brainpool(256), brainpool(384), brainpool(512),
  eddsa('ED25519', 'common.keyTypes.ed25519'), eddsa('ED448', 'common.keyTypes.ed448'),
  mldsa('44', 2), mldsa('65', 3), mldsa('87', 5),
]

export const ACME_CLIENT_LABELS = ['RSA-2048', 'RSA-4096', 'EC-P256', 'EC-P384', 'EC-BP256', 'EC-BP384']
export const CSR_LABELS = ['RSA-2048', 'RSA-4096', 'EC-P256', 'EC-P384', 'EC-P521', 'EC-BP256', 'EC-BP384', 'EC-BP512']
export const TSA_LABELS = ['RSA-3072', 'RSA-2048', 'RSA-4096', 'EC-P256', 'EC-P384', 'EC-BP256', 'EC-BP384']

export function findAlgorithm(label) {
  return KEY_ALGORITHMS.find(a => a.label === label) || null
}

/** `key_type` / `key_size` / `curve` of a TSA signer request, as its API names them. */
export function signerKeyParams(label) {
  const a = findAlgorithm(label)
  if (!a) return { key_type: '', key_size: undefined, curve: undefined }
  if (a.family === 'RSA') return { key_type: 'RSA', key_size: String(a.bits), curve: undefined }
  if (a.family === 'EC') return { key_type: 'EC', key_size: undefined, curve: a.curveParam }
  return { key_type: '', key_size: undefined, curve: undefined }
}

export const isFipsApproved = (label) => findAlgorithm(label)?.fips === true

export const isBrainpool = (label) => findAlgorithm(label)?.group === GROUP_BRAINPOOL

// SLH-DSA is read by OID only (no registry row): its API name starts 'SLH-DSA-'
export const isPostQuantum = (label) =>
  !!label && (findAlgorithm(label)?.group === GROUP_PQ || String(label).startsWith('SLH-DSA-'))

/** Export format keys a key algorithm cannot use; none when the key is unknown. */
export function exportExcludedFor(keyAlgorithm) {
  const row = findAlgorithm(keyAlgorithm)
  if (row) return row.exportExcluded
  return isPostQuantum(keyAlgorithm) ? PQ_EXPORT_EXCLUDED : []
}

export const isExportFormatAllowed = (keyAlgorithm, format) => !exportExcludedFor(keyAlgorithm).includes(format)

/** 'ML-DSA-65 (level 3)' for a post-quantum key, the name as is otherwise; null without one. */
export function keyAlgorithmLabel(name, t, securityLevel) {
  if (!name) return null
  const level = securityLevel ?? findAlgorithm(name)?.securityLevel
  return isPostQuantum(name) && level ? t('common.keyAlgorithmLevel', { name, level }) : name
}

/** Family and size of a CA key_type ('RSA 2048', 'EC secp384r1'); a post-quantum label has no size. */
export function caKeyParts(keyType) {
  if (!keyType) return { family: null, spec: null }
  const space = keyType.indexOf(' ')
  if (space < 0) return { family: keyType, spec: null }
  return { family: keyType.slice(0, space), spec: keyType.slice(space + 1) }
}

/**
 * Algorithms a form may offer. `labels` restricts and orders the list, `generate`
 * keeps keys the product creates, `provider` keeps what that HSM type can hold,
 * and FIPS mode hides what the module does not approve.
 */
export function listAlgorithms({ labels, generate = false, provider, fips = false } = {}) {
  const rows = labels ? labels.map(findAlgorithm).filter(Boolean) : KEY_ALGORITHMS
  return rows.filter(a =>
    (!generate || a.generate)
    && (!fips || a.fips)
    && (provider === undefined || a.providers == null || a.providers.includes(provider)))
}

/** Default digest for a CA key ('ECDSA' + 'secp384r1'), sha256 when unknown. */
export function defaultDigestFor(keyAlgo, keySize) {
  const row = KEY_ALGORITHMS.find(a => a.ca && a.ca[0] === keyAlgo && a.ca[1] === keySize)
  return row?.digest || 'sha256'
}

/**
 * Select options (value = label) with a group heading per family once the list spans
 * several groups. `labelOf(algo)` names one row, `valueOf(algo)` is its option value.
 */
export function groupedOptions(algorithms, t, labelOf = (a) => a.display, valueOf = (a) => a.label) {
  const groups = new Set(algorithms.map(a => a.group))
  return algorithms.map(a => ({
    value: valueOf(a),
    label: labelOf(a),
    ...(groups.size > 1 ? { group: t(KEY_GROUPS.find(g => g.id === a.group).labelKey) } : {}),
  }))
}
