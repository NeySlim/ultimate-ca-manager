/**
 * Client-side SAN validation for Generate CSR (mirrors backend utils/san_parse.py).
 * Returns i18n key + params, or null if valid.
 */

const EMAIL_RE = /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/

function looksLikeIpv4(v) {
  return /^(?:\d{1,3}\.){3}\d{1,3}$/.test(v)
}

function looksLikeIp(v) {
  return looksLikeIpv4(v) || v.includes(':')
}

function isValidEmail(v) {
  return EMAIL_RE.test(v)
}

function isValidUri(v) {
  return /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(v)
}

function isValidUpn(v) {
  const parts = v.split('@')
  return parts.length === 2 && parts[0] && parts[1]
}

/**
 * @param {'DNS'|'IP'|'Email'|'URI'|'UPN'} type
 * @param {string} value
 * @returns {{ key: string, params?: object } | null}
 */
export function getSanValidationError(type, value) {
  const v = (value || '').trim()
  if (!v) return null

  switch (type) {
    case 'IP':
      if (!looksLikeIp(v)) {
        return { key: 'csrs.sanFqdnUseDns', params: { value: v } }
      }
      return null
    case 'DNS':
      if (looksLikeIp(v)) {
        return { key: 'csrs.sanIpForAddress', params: { value: v } }
      }
      if (v.includes('@')) {
        return { key: 'csrs.sanEmailUseEmail', params: { value: v } }
      }
      if (v.includes('://')) {
        return { key: 'csrs.sanUriUseUri', params: { value: v } }
      }
      return null
    case 'Email':
      if (!isValidEmail(v)) {
        return v.includes('@')
          ? { key: 'csrs.sanEmailInvalid', params: { value: v } }
          : { key: 'csrs.sanHostnameUseDns', params: { value: v } }
      }
      return null
    case 'URI':
      if (!isValidUri(v)) {
        return { key: 'csrs.sanUriInvalid', params: { value: v } }
      }
      return null
    case 'UPN':
      if (!isValidUpn(v)) {
        return { key: 'csrs.sanUpnInvalid', params: { value: v } }
      }
      return null
    default:
      return null
  }
}
