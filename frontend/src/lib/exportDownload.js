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
import { sanitizeFilename } from './filename'

export { sanitizeFilename }

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
