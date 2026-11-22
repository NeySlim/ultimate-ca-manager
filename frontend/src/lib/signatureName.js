import { isPostQuantum } from './keyAlgorithms'

// Short name for the summary chip: 'SHA256' of 'SHA256-RSA', 'RSASSA-PSS' of a PSS label,
// a post-quantum name ('ML-DSA-65') whole
export function signatureShortName(signatureAlgorithm) {
  if (!signatureAlgorithm) return '—'
  if (signatureAlgorithm.startsWith('RSASSA-PSS')) return 'RSASSA-PSS'
  if (isPostQuantum(signatureAlgorithm)) return signatureAlgorithm
  return signatureAlgorithm.split('-')[0]
}

// A SHA-2 or SHA-1 hash named in a classical signature: 'SHA256-RSA', 'ECDSA-SHA384', a CA's OID name
// ('sha256WithRSAEncryption', 'ecdsa-with-SHA384') or its hash alone ('SHA-512')
const CLASSICAL_HASH = /^(?:sha-?(1|224|256|384|512)(?:-?rsa|-?ecdsa|withrsaencryption)?|(?:ecdsa-(?:with-)?)sha-?(1|224|256|384|512))$/i

// The hash of a signature as the Atelier detail names it: 'SHA-256' of 'SHA256-RSA' or of a CA's
// 'sha256WithRSAEncryption', 'RSASSA-PSS' of a PSS label, a post-quantum or EdDSA name whole
export function signatureHashName(signatureAlgorithm) {
  const classical = CLASSICAL_HASH.exec(signatureAlgorithm || '')
  if (classical) return `SHA-${classical[1] || classical[2]}`
  return signatureShortName(signatureAlgorithm)
}

// HSM provider types whose keys sign RSA-PSS (Azure and Google KMS do not here)
export const PSS_HSM_TYPES = ['pkcs11', 'aws-cloudhsm', 'openbao']
