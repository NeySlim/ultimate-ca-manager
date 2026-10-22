/**
 * Key types and signature hashes the active policies allow (#397).
 * `null` means unrestricted, an empty list means nothing is allowed.
 */
import { useEffect, useState } from 'react'
import { policiesService } from '../services'
import { extractData } from './utils'
import { KEY_ALGORITHMS } from './keyAlgorithms'

export const POLICY_DIGESTS = ['sha256', 'sha384', 'sha512']

export function isAllowed(allowed, value) {
  return allowed == null || allowed.includes(value)
}

// Issue form fields ('rsa' + '2048', 'ecdsa' + '384') <-> policy labels
export const ISSUE_KEY_CHOICES = KEY_ALGORITHMS.filter(a => a.issue).map(a => a.issue)

export function issueKeyLabel(keyType, keySize) {
  return KEY_ALGORITHMS.find(a => a.issue && a.issue[0] === keyType && a.issue[1] === keySize)?.label ?? null
}

// CA form fields ('RSA' + '2048', 'ECDSA' + 'secp384r1') <-> policy labels
export const CA_KEY_CHOICES = KEY_ALGORITHMS.filter(a => a.ca).map(a => a.ca)

export function caKeyLabel(keyAlgo, keySize) {
  return KEY_ALGORITHMS.find(a => a.ca && a.ca[0] === keyAlgo && a.ca[1] === keySize)?.label ?? null
}

/**
 * Effective policy restrictions for a CA (none = root, global policies) and a template.
 * A failed lookup leaves the form unrestricted: the server enforces the rules anyway.
 */
export function useEffectiveAlgorithms({ caId, templateId, enabled = true }) {
  const [state, setState] = useState({ allowedKeyTypes: null, allowedDigests: null, fips: false })
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
          fips: data.fips === true,
        })
      })
      .catch(() => {
        if (!cancelled) setState({ allowedKeyTypes: null, allowedDigests: null, fips: false })
      })
    return () => { cancelled = true }
  }, [caId, templateId, enabled])
  return state
}

/**
 * Whether the server runs in FIPS mode (#399), read from the effective policy.
 * A failed lookup reads as false: the server refuses what FIPS mode forbids anyway.
 */
export function useFipsMode() {
  const [fips, setFips] = useState(false)
  useEffect(() => {
    let cancelled = false
    Promise.resolve()
      .then(() => policiesService.getEffective())
      .then((res) => { if (!cancelled) setFips((extractData(res) || {}).fips === true) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])
  return fips
}

// SSH key types outside the FIPS module, and the default FIPS mode takes instead
export const SSH_EDDSA_KEY_TYPES = ['ed25519']
export const SSH_FIPS_DEFAULT_KEY_TYPE = 'ecdsa-p256'

export function sshKeyOptions(options, fips) {
  return fips ? options.filter(o => !SSH_EDDSA_KEY_TYPES.includes(o.value)) : options
}
