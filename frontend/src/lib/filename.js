/** Filename hygiene shared by downloadBlob and the export helpers. */

// Long enough for any CN (RFC 5280 caps it at 64) or ACME domain; the byte budget keeps
// name + extension inside the 255-byte limit every common filesystem enforces.
const MAX_BASENAME = 128
const MAX_BASENAME_BYTES = 200
// Characters nobody sees: fillers, variation selectors, and the ZWNJ/ZWJ format marks the server strips too
const INVISIBLE = /[\u034f\u200c\u200d\u115f\u1160\u180b-\u180d\u3164\ufe00-\ufe0f\uffa0\u{e0100}-\u{e01ef}]/gu
// Device names Windows refuses whatever follows the first dot
const WINDOWS_DEVICE = /^(con|prn|aux|nul|com[0-9\u00b9\u00b2\u00b3]|lpt[0-9\u00b9\u00b2\u00b3])$/i

/** The longest prefix of whole characters within both budgets. */
function clip(text, maxChars) {
  const encoder = new TextEncoder()
  let kept = ''
  let bytes = 0
  let chars = 0
  for (const char of text) {
    const size = encoder.encode(char).length
    if (chars >= maxChars || bytes + size > MAX_BASENAME_BYTES) break
    kept += char
    bytes += size
    chars += 1
  }
  return kept
}

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
  // Letters, marks and digits of any script stay; separators, controls and bidi marks do not
  let safe = String(name ?? '').normalize('NFC').replace(INVISIBLE, '')
    .replace(/[^\p{L}\p{M}\p{N}._-]+/gu, '_')
  // Leading dots would hide the file, "." / ".." are not names, a leading mark has no base.
  safe = clip(safe.replace(/^[.\p{M}]+/u, ''), maxLength)
  const stem = safe.split('.', 1)[0]
  if (WINDOWS_DEVICE.test(stem)) safe = `${stem}_${safe.slice(stem.length)}`
  return safe || 'export'
}

// A trailing ".xyz" is an extension only when it is short and plain ASCII; anything else
// ("example.com", "a.b/c") is part of the label and gets sanitized with it.
const EXTENSION = /^(.*)\.([A-Za-z0-9]{1,16})$/s

/**
 * Sanitize a whole download name: the base goes through sanitizeFilename, the
 * extension is split off first so clipping can never eat it. Idempotent.
 */
export function sanitizeDownloadName(filename) {
  const name = String(filename ?? '')
  const m = EXTENSION.exec(name)
  if (!m) return sanitizeFilename(name)
  return `${sanitizeFilename(m[1])}.${m[2]}`
}
