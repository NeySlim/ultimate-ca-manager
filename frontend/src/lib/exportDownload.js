/**
 * Turning an export response into a file on disk — once, for every surface.
 *
 * Five handlers used to do this by hand (certificates list, certificate row,
 * floating detail window, account mTLS, user certificates), each with its own
 * copy of the format→extension table and its own anchor plumbing. The tables
 * had already drifted apart; this is the one they now share.
 *
 * Callers keep their own wording for the success and failure toasts, and their
 * own way of naming the file, because those are page-level decisions.
 */
import { downloadBlob } from './utils'

// The formats ExportModal can ask for, plus the pfx alias some callers pass.
export const EXPORT_EXTENSIONS = {
  pem: 'pem',
  der: 'der',
  pkcs7: 'p7b',
  pkcs12: 'p12',
  pfx: 'pfx',
  jks: 'jks',
  key: 'key',
  'hybrid-bundle': 'zip',
}

// Long enough for any CN (RFC 5280 caps it at 64) or ACME domain, short
// enough that name + extension stays well inside the 255-byte limit every
// common filesystem enforces.
const MAX_BASENAME = 128

/**
 * Make a caller-supplied label safe to use as a filename.
 *
 * The label is a CN, an ACME domain or a CA description, and none of those are
 * the operator's own text: they ride in on externally submitted CSRs, ACME
 * orders, SCEP/EST enrolments and discovery scans. RFC 5280 happily allows
 * `/`, `\`, `:`, `..` and control characters in a CN, while several of the
 * files named here contain a private key.
 *
 * @param {string} name - the untrusted label
 * @param {number} [maxLength] - cap for the returned base name
 * @returns {string} a single path segment, never empty, never "." or ".."
 */
export function sanitizeFilename(name, maxLength = MAX_BASENAME) {
  let safe = String(name ?? '').replace(/[^A-Za-z0-9._-]+/g, '_')
  // Leading dots would hide the file, and "." / ".." are not names at all.
  safe = safe.replace(/^\.+/, '')
  if (safe.length > maxLength) safe = safe.slice(0, maxLength)
  return safe || 'export'
}

/**
 * The filename a given export should land under.
 *
 * The naming convention itself (date-stamped or bare) stays with the caller;
 * only the untrusted part is scrubbed, and the extension is appended after.
 *
 * @param {string} name - already resolved by the caller (CN, description, …)
 * @param {string} format - an ExportModal format key
 */
export function exportFileName(name, format) {
  return `${sanitizeFilename(name)}.${EXPORT_EXTENSIONS[format] || format}`
}

/**
 * Await an export request and save the result.
 *
 * Services answer with a Blob when asked for one; a couple of older paths hand
 * back the envelope instead, so both are accepted rather than left to produce
 * a file containing "[object Object]".
 *
 * @param {Promise} request - the service call, already invoked
 * @param {{format: string, name: string}} opts
 */
export async function downloadExport(request, { format, name }) {
  const res = await request
  const blob = res instanceof Blob
    ? res
    : new Blob([res?.data ?? res], { type: 'application/octet-stream' })
  downloadBlob(blob, exportFileName(name, format))
  return blob
}
