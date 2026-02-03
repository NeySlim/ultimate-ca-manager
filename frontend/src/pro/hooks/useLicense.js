/**
 * Pro License Hook
 * Pro features are enabled if Pro module is present (no license required)
 */
import { useState, useEffect } from 'react'
import { apiClient } from '../../services/apiClient'

// Pro is enabled simply by having this module loaded
const PRO_MODULE_PRESENT = true

export function useLicense() {
  const [license, setLicense] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiClient.get('/license')
      .then(res => setLicense(res.data))
      .catch(() => setLicense({ type: 'community', features: [], pro_enabled: false }))
      .finally(() => setLoading(false))
  }, [])

  // isPro is true if Pro module is present (no license key required)
  const isPro = PRO_MODULE_PRESENT

  return {
    loading,
    isPro,
    isEnterprise: license?.type === 'enterprise',
    type: isPro ? 'pro' : (license?.type || 'community'),
    features: license?.features || [],
    expiresAt: license?.expires_at,
    licensedTo: license?.licensed_to,
    hasFeature: (feature) => isPro || license?.features?.includes(feature) || false
  }
}

export function useProFeatures() {
  const license = useLicense()
  
  // All Pro features enabled when Pro module is present
  return {
    ...license,
    canUseGroups: true,
    canUseRBAC: true,
    canUseSSO: true,
    canUseHSM: true,
    canUseAuditExport: true,
  }
}
