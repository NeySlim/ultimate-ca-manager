/**
 * Compliance profiles (ANSSI, BSI, EU ACM): what each leaves a form to offer,
 * and the global default new CAs receive. Failed lookups leave a form
 * unrestricted: the server enforces the profile anyway.
 */
import { useEffect, useState } from 'react'
import { settingsService, systemService } from '../services'
import { extractData } from './utils'

export const COMPLIANCE_PROFILE_NAMES = ['anssi', 'bsi', 'eu-acm']

/** `{ name: { title, reference, allowed_key_types, ... } }` once loaded, {} before or on failure. */
export function useComplianceProfiles({ enabled = true } = {}) {
  const [profiles, setProfiles] = useState({})
  useEffect(() => {
    if (!enabled) return undefined
    let cancelled = false
    Promise.resolve()
      .then(() => systemService.getComplianceProfiles())
      .then((res) => {
        if (cancelled) return
        const list = extractData(res)
        setProfiles(Array.isArray(list) ? Object.fromEntries(list.map((p) => [p.name, p])) : {})
      })
      .catch(() => { if (!cancelled) setProfiles({}) })
    return () => { cancelled = true }
  }, [enabled])
  return profiles
}

/** The profile new CAs receive when none is named, '' when unset or unreadable. */
export function useComplianceDefault({ enabled = true } = {}) {
  const [value, setValue] = useState('')
  useEffect(() => {
    if (!enabled) return undefined
    let cancelled = false
    Promise.resolve()
      .then(() => settingsService.getAll())
      .then((res) => {
        const name = (extractData(res) || {}).compliance_profile_default
        if (!cancelled) setValue(COMPLIANCE_PROFILE_NAMES.includes(name) ? name : '')
      })
      .catch(() => { if (!cancelled) setValue('') })
    return () => { cancelled = true }
  }, [enabled])
  return value
}

const intersect = (a, b) => (a == null ? b : b == null ? a : a.filter((x) => b.includes(x)))

/**
 * The key types and digests of `base` ({ allowedKeyTypes, allowedDigests }, null = unrestricted)
 * narrowed by `profile`, plus the signature schemes, date horizons and HSM rule it adds.
 */
export function limitsWithProfile(base, profile) {
  return {
    allowedKeyTypes: intersect(base.allowedKeyTypes, profile?.allowed_key_types ?? null),
    allowedDigests: intersect(base.allowedDigests, profile?.allowed_digests ?? null),
    allowedSchemes: profile?.allowed_signature_schemes ?? null,
    horizons: profile?.key_type_horizons ?? {},
    requireHsm: profile?.require_hsm_ca_key === true,
  }
}
