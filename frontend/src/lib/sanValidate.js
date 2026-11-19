/**
 * Client-side SAN validation (mirrors backend utils/san_parse.py).
 * Returns i18n key + params, or null if valid.
 */

const EMAIL_RE = /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/

function normalizeSanType(type) {
  const map = {
    dns: 'DNS',
    ip: 'IP',
    email: 'Email',
    uri: 'URI',
    upn: 'UPN',
  }
  const raw = (type || '').trim()
  return map[raw.toLowerCase()] || raw.toUpperCase()
}

// The shape tests these replaced accepted `999.999.999.999` and rejected
// `::ffff:192.168.1.1`, while the backend parses both properly with
// `ipaddress.ip_address`. Each mismatch was a dead end rather than a bad
// message: the IP field took `999.999.999.999` and the server sent it back
// with "use DNS type", and the DNS field then refused it with "use IP type".
// The mirror case ran the same loop for a valid IPv4-mapped address that
// only the server would have accepted. What follows is `ip_address`'s
// grammar, and contracts/san_contract.json holds the corpus both sides
// are checked against.

function looksLikeIpv4(v) {
  const parts = v.split('.')
  if (parts.length !== 4) return false
  return parts.every((part) => {
    if (!/^\d{1,3}$/.test(part)) return false
    // Python has rejected leading zeros since 3.9.5: `010.1.1.1` is not
    // octal here, it is refused.
    if (part.length > 1 && part[0] === '0') return false
    return Number(part) <= 255
  })
}

function isHexGroup(group) {
  return /^[0-9a-fA-F]{1,4}$/.test(group)
}

function looksLikeIpv6(v) {
  if (!v.includes(':')) return false

  // A zone index (`fe80::1%eth0`) is part of the address for `ip_address`.
  const zoneAt = v.indexOf('%')
  let s = zoneAt === -1 ? v : v.slice(0, zoneAt)
  if (zoneAt !== -1 && !s.includes(':')) return false
  if (zoneAt !== -1 && v.slice(zoneAt + 1) === '') return false

  // A trailing dotted quad stands for the last two groups.
  const lastColon = s.lastIndexOf(':')
  const tailPiece = s.slice(lastColon + 1)
  if (tailPiece.includes('.')) {
    if (!looksLikeIpv4(tailPiece)) return false
    s = `${s.slice(0, lastColon + 1)}0:0`
  } else if (s.includes('.')) {
    return false
  }

  const halves = s.split('::')
  if (halves.length > 2) return false
  const compressed = halves.length === 2
  const head = halves[0] === '' ? [] : halves[0].split(':')
  const tail = !compressed || halves[1] === '' ? [] : halves[1].split(':')
  if (!head.every(isHexGroup) || !tail.every(isHexGroup)) return false

  const groups = head.length + tail.length
  // `::` stands for one group at least, so a compressed address is short.
  return compressed ? groups <= 7 : groups === 8
}

function looksLikeIp(v) {
  return looksLikeIpv4(v) || looksLikeIpv6(v)
}

function isValidEmail(v) {
  return EMAIL_RE.test(v)
}

function isValidUri(v) {
  // Backend (utils/san_parse.py) accepts any RFC 3986 scheme via urlparse,
  // including authority-less URIs (urn:, mailto:, did:). It requires a
  // scheme and nothing after the colon — RFC 3986 allows an empty path —
  // so `urn:` and `mailto:` are addresses the server takes and the `.+`
  // this used to carry refused before the request left the browser.
  return /^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(v)
}

function isValidUpn(v) {
  const parts = v.split('@')
  return parts.length === 2 && parts[0] && parts[1]
}

/** CN is an RFC822 address — not a DNS hostname. */
export function isCnEmail(cn) {
  return isValidEmail((cn || '').trim())
}

// A hostname label, as the backend defines one (utils/san_parse.py): LDH,
// hyphen never at an edge, no underscore.
const HOSTNAME_LABEL = /^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$/

/** Hostname shape — ASCII only, since x509.DNSName refuses a U-label. */
export function looksLikeHostname(value) {
  let v = (value || '').trim()
  if (!v || v.length > 253) return false
  if (v.startsWith('*.')) v = v.slice(2)
  if (v.endsWith('.')) v = v.slice(0, -1)
  if (!v.includes('.')) return false
  return v.split('.').every((label) => HOSTNAME_LABEL.test(label))
}

// U-label to A-label, as the server issues it (RFC 9549); null when not convertible.
// A port, path or userinfo is refused first: URL would drop it from the hostname.
function toALabel(v) {
  if (/[:/?#%@\\\s]/.test(v)) return null
  if (/^[\x00-\x7f]*$/.test(v) && !/(^|\.)xn--/i.test(v)) return v
  try {
    return new URL(`http://${v}`).hostname
  } catch {
    return null
  }
}

/** RFC 5280 §4.2.1.6 preferred name syntax, as backend dns_name_syntax_error. */
export function isValidDnsName(value) {
  const v = (value || '').trim()
  const prefix = v.startsWith('*.') ? '*.' : ''
  const ascii = toALabel(v.slice(prefix.length))
  if (!ascii) return false
  const name = prefix + ascii
  if (name.length > 253 || name.endsWith('.')) return false
  const labels = ascii.split('.')
  // RFC 1123 §2.1: the last label is never all digits
  if (/^\d+$/.test(labels[labels.length - 1])) return false
  return labels.every((label) => HOSTNAME_LABEL.test(label))
}

/** FQDN / wildcard — excludes email and literal IP.
 *  Mirrors backend cn_looks_like_hostname: this used to be `v.includes('.')`,
 *  which previewed a DNS SAN for `Example, Inc.` that the backend then wrote
 *  into the certificate verbatim. */
export function isCnHostname(cn) {
  const v = (cn || '').trim()
  if (!v || isCnEmail(v)) return false
  if (looksLikeIp(v)) return false
  return looksLikeHostname(v)
}

/** Literal IP suitable for IP SAN when used as CN. */
export function isCnIp(cn) {
  return looksLikeIp((cn || '').trim())
}

/**
 * Auto-included SAN rows for Issue Certificate (mirrors backend auto_san_buckets_from_cn).
 * @returns {{ type: string, value: string }[]}
 */
export function getAutoSansFromCn({ cn, certType, subjectEmail }) {
  const value = (cn || '').trim()
  if (!value) return []

  const items = []
  const type = certType || 'server'

  if (['server', 'combined'].includes(type)) {
    if (isCnHostname(value)) {
      items.push({ type: 'dns', value: value.endsWith('.') ? value.slice(0, -1) : value })
    } else if (isCnIp(value)) {
      items.push({ type: 'ip', value })
    }
  }
  if (['email', 'combined'].includes(type) && isCnEmail(value)) {
    items.push({ type: 'email', value })
  }

  // RFC 5280 §4.1.2.6: the subject's address is an email SAN for every type
  const subj = (subjectEmail || '').trim()
  if (
    subj
    && isCnEmail(subj)
    && !items.some((s) => s.type === 'email' && s.value === subj)
  ) {
    items.push({ type: 'email', value: subj })
  }

  return items
}

/**
 * @param {'DNS'|'IP'|'Email'|'URI'|'UPN'|string} type
 * @param {string} value
 * @param {{ i18nNs?: 'csrs' | 'certificates' }} [options]
 * @returns {{ key: string, params?: object } | null}
 */
export function getSanValidationError(type, value, options = {}) {
  const i18nNs = options.i18nNs || 'csrs'
  const key = (name) => `${i18nNs}.${name}`
  const v = (value || '').trim()
  if (!v) return null

  switch (normalizeSanType(type)) {
    case 'IP':
      if (!looksLikeIp(v)) {
        return { key: key('sanFqdnUseDns'), params: { value: v } }
      }
      return null
    case 'DNS':
      if (v.includes('://')) {
        return { key: key('sanUriUseUri'), params: { value: v } }
      }
      if (looksLikeIp(v)) {
        return { key: key('sanIpForAddress'), params: { value: v } }
      }
      if (v.includes('@')) {
        return { key: key('sanEmailUseEmail'), params: { value: v } }
      }
      if (!isValidDnsName(v)) {
        return { key: key('sanDnsInvalid'), params: { value: v } }
      }
      return null
    case 'Email':
      if (!isValidEmail(v)) {
        return v.includes('@')
          ? { key: key('sanEmailInvalid'), params: { value: v } }
          : { key: key('sanHostnameUseDns'), params: { value: v } }
      }
      return null
    case 'URI':
      if (!isValidUri(v)) {
        return { key: key('sanUriInvalid'), params: { value: v } }
      }
      return null
    case 'UPN':
      if (!isValidUpn(v)) {
        return { key: key('sanUpnInvalid'), params: { value: v } }
      }
      return null
    default:
      return null
  }
}

const SAN_PAYLOAD_KEYS = { DNS: 'san_dns', IP: 'san_ip', EMAIL: 'san_email', URI: 'san_uri' }

/**
 * Typed SAN rows ([{ type, value }]) as the sign route's lists
 * (san_dns, san_ip, san_email, san_uri); blank rows and empty lists are left out.
 */
export function sanRowsToPayload(rows) {
  const payload = {}
  for (const { type, value } of rows || []) {
    const key = SAN_PAYLOAD_KEYS[String(type || '').toUpperCase()]
    const v = (value || '').trim()
    if (!key || !v) continue
    payload[key] = [...(payload[key] || []), v]
  }
  return payload
}
