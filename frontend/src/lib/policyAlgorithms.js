/**
 * Key types and signature hashes the active policies allow (#397).
 * `null` means unrestricted, an empty list means nothing is allowed.
 */
import { useEffect, useState } from 'react'
import { policiesService } from '../services'
import { extractData } from './utils'

export const POLICY_DIGESTS = ['sha256', 'sha384', 'sha512']

export function isAllowed(allowed, value) {
  return allowed == null || allowed.includes(value)
}

// Issue form fields ('rsa' + '2048', 'ecdsa' + '384') <-> policy labels
const ISSUE_EC_SIZES = { '256': 'P256', '384': 'P384', '521': 'P521' }
export const ISSUE_KEY_CHOICES = [
  ['rsa', '2048'], ['rsa', '3072'], ['rsa', '4096'],
  ['ecdsa', '256'], ['ecdsa', '384'], ['ecdsa', '521'],
]

export function issueKeyLabel(keyType, keySize) {
  if (keyType === 'rsa') return `RSA-${keySize}`
  if (keyType === 'ecdsa') return ISSUE_EC_SIZES[keySize] ? `EC-${ISSUE_EC_SIZES[keySize]}` : null
  return null
}

// CA form fields ('RSA' + '2048', 'ECDSA' + 'secp384r1') <-> policy labels
const CA_EC_CURVES = { prime256v1: 'P256', secp384r1: 'P384', secp521r1: 'P521' }
export const CA_KEY_CHOICES = [
  ['RSA', '2048'], ['RSA', '3072'], ['RSA', '4096'],
  ['ECDSA', 'prime256v1'], ['ECDSA', 'secp384r1'], ['ECDSA', 'secp521r1'],
]

export function caKeyLabel(keyAlgo, keySize) {
  if (keyAlgo === 'RSA') return `RSA-${keySize}`
  if (keyAlgo === 'ECDSA') return CA_EC_CURVES[keySize] ? `EC-${CA_EC_CURVES[keySize]}` : null
  return null
}

/**
 * Effective policy restrictions for a CA (none = root, global policies) and a template.
 * A failed lookup leaves the form unrestricted: the server enforces the rules anyway.
 */
export function useEffectiveAlgorithms({ caId, templateId, enabled = true }) {
  const [state, setState] = useState({ allowedKeyTypes: null, allowedDigests: null })
  useEffect(() => {
    if (!enabled) return undefined
    let cancelled = false
    Promise.resolve()
      .then(() => policiesService.getEffective({ ca_id: caId || undefined, template_id: templateId || undefined }))
      .then((res) => {
        if (cancelled) return
        const data = extractData(res) || {}
        setState({
          allowedKeyTypes: Array.isArray(data.allowed_key_types) ? data.allowed_key_types : null,
          allowedDigests: Array.isArray(data.allowed_digests) ? data.allowed_digests : null,
        })
      })
      .catch(() => {
        if (!cancelled) setState({ allowedKeyTypes: null, allowedDigests: null })
      })
    return () => { cancelled = true }
  }, [caId, templateId, enabled])
  return state
}
