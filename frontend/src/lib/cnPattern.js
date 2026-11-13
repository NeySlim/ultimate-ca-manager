// Variables of a common name pattern by subject source (backend services/wstep/cn_pattern.py)
const CN_PATTERN_MACHINE_TYPES = ['web_server', 'vpn_server', 'vpn_client', 'ocsp_signing']
export const CN_PATTERN_VARIABLES = {
  machine: ['hostname', 'fqdn', 'domain', 'realm'],
  directory: ['username', 'upn', 'mail', 'displayName', 'givenName', 'surname', 'domain', 'realm'],
}
const CN_PATTERN_NON_UNIQUE = ['displayName', 'givenName', 'surname', 'mail']

export function cnPatternSource(templateType, adDerivedSubject) {
  if (CN_PATTERN_MACHINE_TYPES.includes(templateType)) return 'machine'
  return adDerivedSubject ? 'directory' : 'request'
}

// The non-unique variables a pattern names, written as in the pattern
export function cnPatternNonUnique(pattern) {
  const named = new Set([...(pattern || '').replace(/\{\{|\}\}/g, '').matchAll(/\{([^{}]+)\}/g)].map(m => m[1]))
  return CN_PATTERN_NON_UNIQUE.filter(v => named.has(v)).map(v => `{${v}}`)
}
