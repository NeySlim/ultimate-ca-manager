/**
 * Custom X.509 extensions (#437): rows of the editor to the API payload
 * `[{oid, critical, value}]`, the value being the DER bytes in hex.
 * The server refuses the OIDs UCM sets itself; this only checks the shape.
 */

const OID_RE = /^[0-2](\.(0|[1-9][0-9]*))+$/
const SEPARATORS = /[\s:]/g

export const isDottedOid = (oid) => {
  const v = String(oid ?? '').trim()
  if (!OID_RE.test(v)) return false
  const [first, second] = v.split('.').map(Number)
  return first === 2 || second < 40
}

export const normalizeHex = (value) => String(value ?? '').replace(SEPARATORS, '').toLowerCase()

export const isEvenHex = (value) => {
  const v = normalizeHex(value)
  return v.length > 0 && v.length % 2 === 0 && /^[0-9a-f]+$/.test(v)
}

export const emptyExtensionRow = () => ({ oid: '', critical: false, value: '' })

/** Editor rows from a stored list (template or request). */
export const rowsFromStored = (stored) =>
  (Array.isArray(stored) ? stored : []).map(e => ({
    oid: e?.oid || '', critical: e?.critical === true, value: e?.value || '',
  }))

const isBlank = (row) => !String(row.oid || '').trim() && !normalizeHex(row.value)

/** i18n key of the row's problem, or null; *others* are the rows before it. */
export function rowError(row, others = []) {
  if (isBlank(row)) return null
  const oid = String(row.oid || '').trim()
  if (!isDottedOid(oid)) return 'customExtensions.invalidOid'
  if (!normalizeHex(row.value)) return 'customExtensions.emptyValue'
  if (!isEvenHex(row.value)) return 'customExtensions.invalidHex'
  if (others.some(o => String(o.oid || '').trim() === oid)) return 'customExtensions.duplicateOid'
  return null
}

/** `{ entries, errors }`: the payload, and one error key (or null) per row. */
export function customExtensionsPayload(rows) {
  const list = Array.isArray(rows) ? rows : []
  const errors = list.map((row, i) => rowError(row, list.slice(0, i).filter(r => !isBlank(r))))
  const entries = list
    .filter((row, i) => !isBlank(row) && !errors[i])
    .map(row => ({ oid: row.oid.trim(), critical: row.critical === true, value: normalizeHex(row.value) }))
  return { entries, errors, valid: errors.every(e => !e) }
}

/** First characters of a long hex value, for display. */
export const truncateHex = (hex, max = 48) => {
  const v = String(hex || '')
  return v.length > max ? `${v.slice(0, max)}…` : v
}
