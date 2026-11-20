import { isPostQuantum } from './keyAlgorithms'

// Short name for the summary chip: 'SHA256' of 'SHA256-RSA', 'RSASSA-PSS' of a PSS label,
// a post-quantum name ('ML-DSA-65') whole
export function signatureShortName(signatureAlgorithm) {
  if (!signatureAlgorithm) return '—'
  if (signatureAlgorithm.startsWith('RSASSA-PSS')) return 'RSASSA-PSS'
  if (isPostQuantum(signatureAlgorithm)) return signatureAlgorithm
  return signatureAlgorithm.split('-')[0]
}

// The hash of a signature as the Atelier detail names it: 'SHA-256' of 'SHA256-RSA',
// 'RSASSA-PSS' of a PSS label, a post-quantum name whole
export function signatureHashName(signatureAlgorithm) {
  const short = signatureShortName(signatureAlgorithm)
  const m = /^SHA(1|224|256|384|512)$/i.exec(short)
  return m ? `SHA-${m[1]}` : short
}

// HSM provider types whose keys sign RSA-PSS (Azure and Google KMS do not here)
export const PSS_HSM_TYPES = ['pkcs11', 'aws-cloudhsm', 'openbao']
