/**
 * Key algorithm registry: one row per key the product can generate or accept.
 * Forms read their lists from here; mirror of backend utils/key_algorithms.py.
 */

export const GROUP_RSA = 'rsa'
export const GROUP_NIST = 'nist'
export const GROUP_BRAINPOOL = 'brainpool'
export const GROUP_EDDSA = 'eddsa'

// Heading of each group, as an i18n key
export const KEY_GROUPS = [
  { id: GROUP_RSA, labelKey: 'common.keyGroups.rsa' },
  { id: GROUP_NIST, labelKey: 'common.keyGroups.nist' },
  { id: GROUP_BRAINPOOL, labelKey: 'common.keyGroups.brainpool' },
  { id: GROUP_EDDSA, labelKey: 'common.keyGroups.eddsa' },
]

const rsa = (bits) => ({
  label: `RSA-${bits}`, bits, family: 'RSA', group: GROUP_RSA, display: `RSA ${bits}`,
  digest: 'sha256', fips: true, generate: true, providers: null,
  issue: ['rsa', String(bits)], ca: ['RSA', String(bits)], csr: `RSA ${bits}`,
  curveParam: null, i18nKey: `common.keyTypes.rsa${bits}`,
  sizeKey: `certificates.keySizeRsa${bits}`, csrKey: `csrs.keyRsa${bits}`,
})

const nist = (bits, curve, digest) => ({
  label: `EC-P${bits}`, bits, family: 'EC', group: GROUP_NIST, display: `ECDSA P-${bits}`,
  digest, fips: true, generate: true, providers: null,
  issue: ['ecdsa', String(bits)], ca: ['ECDSA', curve], csr: `EC P-${bits}`,
  curveParam: `P-${bits}`, i18nKey: `common.keyTypes.ecdsaP${bits}`,
  sizeKey: `certificates.keyCurveNistP${bits}`, csrKey: `csrs.keyCurveNistP${bits}`,
})

// Brainpool: provider-side generation is PKCS#11 only
const brainpool = (bits) => ({
  label: `EC-BP${bits}`, bits, family: 'EC', group: GROUP_BRAINPOOL, display: `Brainpool P${bits}r1`,
  digest: `sha${bits}`, fips: false, generate: true, providers: ['pkcs11'],
  issue: ['ecdsa', `brainpoolP${bits}r1`], ca: ['ECDSA', `brainpoolP${bits}r1`], csr: `EC-BP${bits}`,
  curveParam: `brainpoolP${bits}r1`, i18nKey: null, sizeKey: null, csrKey: null,
})

// EdDSA keys only arrive through CSRs and enrollment protocols (generate: false)
const eddsa = (label, i18nKey) => ({
  label, bits: null, family: 'EDDSA', group: GROUP_EDDSA, display: label === 'ED25519' ? 'Ed25519' : 'Ed448',
  digest: null, fips: false, generate: false, providers: null,
  issue: null, ca: null, csr: null, curveParam: null, i18nKey, sizeKey: null, csrKey: null,
})

export const KEY_ALGORITHMS = [
  rsa(2048), rsa(3072), rsa(4096),
  nist(256, 'prime256v1', 'sha256'), nist(384, 'secp384r1', 'sha384'), nist(521, 'secp521r1', 'sha512'),
  brainpool(256), brainpool(384), brainpool(512),
  eddsa('ED25519', 'common.keyTypes.ed25519'), eddsa('ED448', 'common.keyTypes.ed448'),
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
  return a.family === 'RSA'
    ? { key_type: 'RSA', key_size: String(a.bits), curve: undefined }
    : { key_type: 'EC', key_size: undefined, curve: a.curveParam }
}

export const isFipsApproved = (label) => findAlgorithm(label)?.fips === true

export const isBrainpool = (label) => findAlgorithm(label)?.group === GROUP_BRAINPOOL

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
