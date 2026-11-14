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

// Key types the server's FIPS module approves, null when the server does not say
const fipsKeyTypes = (data) => (Array.isArray(data.fips_key_types) ? data.fips_key_types : null)

/**
 * Effective policy restrictions for a CA (none = root, global policies) and a template.
 * A failed lookup leaves the form unrestricted: the server enforces the rules anyway.
 */
export function useEffectiveAlgorithms({ caId, templateId, enabled = true }) {
  const [state, setState] = useState({ allowedKeyTypes: null, allowedDigests: null, fips: false, fipsKeys: null, mldsa: true, pqStandalone: false, defaultKeyType: null })
  useEffect(() => {
    if (!enabled) return undefined
    let cancelled = false
    // The previous pair's default is stale until this pair answers
    setState((prev) => (prev.defaultKeyType === null ? prev : { ...prev, defaultKeyType: null }))
    Promise.resolve()
      .then(() => policiesService.getEffective({ ca_id: caId || undefined, template_id: templateId || undefined }))
      .then((res) => {
        if (cancelled) return
        const data = extractData(res) || {}
        setState({
          allowedKeyTypes: Array.isArray(data.allowed_key_types) ? data.allowed_key_types : null,
          allowedDigests: Array.isArray(data.allowed_digests) ? data.allowed_digests : null,
          fips: data.fips === true,
          fipsKeys: fipsKeyTypes(data),
          mldsa: data.ml_dsa !== false,
          pqStandalone: data.pq_standalone === true,
          // The server's own default key; its baseline stands in when only that came back
          defaultKeyType: data.default_key_type ?? (data.default_key_error ? null : data.baseline_key_type ?? null),
        })
      })
      .catch(() => {
        if (!cancelled) setState({ allowedKeyTypes: null, allowedDigests: null, fips: false, fipsKeys: null, mldsa: true, pqStandalone: false, defaultKeyType: null })
      })
    return () => { cancelled = true }
  }, [caId, templateId, enabled])
  return state
}

/**
 * What the server can use, from the effective policy: `fips` (FIPS mode, #399), `fipsKeys`
 * (what its FIPS module approves) and `mldsa` (this build has ML-DSA). A failed lookup offers
 * everything: the server refuses anyway.
 */
export function useKeyPlatform() {
  const [platform, setPlatform] = useState({ fips: false, fipsKeys: null, mldsa: true, defaultKeyType: null })
  useEffect(() => {
    let cancelled = false
    Promise.resolve()
      .then(() => policiesService.getEffective())
      .then((res) => {
        if (cancelled) return
        const data = extractData(res) || {}
        // default_key_type: what the server issues for a request that names no key
        setPlatform({
          fips: data.fips === true, fipsKeys: fipsKeyTypes(data), mldsa: data.ml_dsa !== false,
          defaultKeyType: data.default_key_type ?? null,
        })
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])
  return platform
}

export const useFipsMode = () => useKeyPlatform().fips

// SSH key types FIPS mode allows only when the module approves Ed25519, and the default it takes instead
export const SSH_EDDSA_KEY_TYPES = ['ed25519']
export const SSH_FIPS_DEFAULT_KEY_TYPE = 'ecdsa-p256'

/** Whether FIPS mode leaves out Ed25519 SSH keys: on, and its module does not approve Ed25519. */
export const sshEddsaRefused = (fips, fipsKeys = null) =>
  !!fips && !(Array.isArray(fipsKeys) && fipsKeys.includes('ED25519'))

export function sshKeyOptions(options, fips, fipsKeys = null) {
  return sshEddsaRefused(fips, fipsKeys) ? options.filter(o => !SSH_EDDSA_KEY_TYPES.includes(o.value)) : options
}
