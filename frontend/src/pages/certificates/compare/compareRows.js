/**
 * The lines of a comparison of certificates, read from what the inspector loads (GET
 * /certificates/:id): subject, issuer, validity, key, names, usages, fingerprints, serial, then
 * every other extension. Each line has one value per certificate and says whether they differ; a
 * list (names, usages, extensions) is compared element by element.
 */
import { formatDate } from '../../../lib/utils'
import { certificateKeyLabel, extensionRows, serialHex } from '../../../lib/certificateDetail'

export const ABSENT = '—'
// Extensions with a line of their own above: not repeated among the others
const OWN_LINES = new Set(['subject_alt_names', 'key_usage', 'extended_key_usage'])

const day = (d) => (d ? formatDate(d, { time: false }) : '')

function extensionsOf(cert) {
  return Object.fromEntries(extensionRows(cert.extensions, cert.san_combined).map((r) => [r.key, r]))
}

// A list equals another when it holds the same elements, in any order
const setKey = (list) => [...new Set(list)].sort().join('\u0000')

/**
 * `values` per certificate; a list line also gets `items`, each element common to all certificates or
 * not, and `byElement` when one certificate holds several: a single value differs as a whole.
 */
function finish(row) {
  if (!row.list) return { ...row, differs: new Set(row.values).size > 1 }
  const sets = row.values.map((v) => new Set(v))
  const items = row.values.map((v) => v.map((value) => ({ value, common: sets.every((s) => s.has(value)) })))
  const byElement = row.values.some((v) => v.length > 1)
  return { ...row, items, byElement, differs: new Set(row.values.map(setKey)).size > 1 }
}

export function compareRows(certs, t) {
  const exts = certs.map(extensionsOf)
  const ext = (i, key) => exts[i][key]?.values || []
  const scalar = (key, label, value) => ({ key, label, values: certs.map(value) })
  const list = (key, label, value) => ({ key, label, list: true, values: certs.map((c, i) => value(i)) })
  const fixed = [
    scalar('subject', t('common.subject'), (c) => c.subject || ABSENT),
    scalar('issuer', t('common.issuer'), (c) => c.issuer || ABSENT),
    scalar('validity', t('common.validity'), (c) => [day(c.valid_from), day(c.valid_to)].filter(Boolean).join(' – ') || ABSENT),
    scalar('key', t('compare.key'), (c) => certificateKeyLabel(c, t) || ABSENT),
    list('san', 'SAN', (i) => ext(i, 'subject_alt_names')),
    // Key usages read one by one (the inspector joins them on one line), so the one a certificate adds stands out
    list('usages', t('compare.usages'), (i) => [...ext(i, 'key_usage').flatMap((v) => v.split(', ')), ...ext(i, 'extended_key_usage')]),
    scalar('sha1', `${t('common.fingerprints')} SHA-1`, (c) => c.thumbprint_sha1 || ABSENT),
    scalar('sha256', `${t('common.fingerprints')} SHA-256`, (c) => c.thumbprint_sha256 || ABSENT),
    scalar('serial', t('inspector.cert.serial'), (c) => serialHex(c.serial_number) || ABSENT),
  ]

  // Every other extension any of them carries, in the order the first one that has it lists it;
  // its critical flag is an element of its own, so a flag alone shows as the difference
  const seen = new Map()
  exts.forEach((byKey) => Object.values(byKey).forEach((r) => { if (!OWN_LINES.has(r.key) && !seen.has(r.key)) seen.set(r.key, r) }))
  const critical = `(${t('inspector.cert.critical')})`
  const others = [...seen.values()].map((r) => list(r.key, r.label, (i) => {
    const own = exts[i][r.key]
    return own ? [...own.values, ...(own.critical ? [critical] : [])] : []
  }))

  return [...fixed, ...others].map(finish)
}
