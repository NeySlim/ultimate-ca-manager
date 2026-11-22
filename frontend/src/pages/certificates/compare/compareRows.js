/**
 * The lines of a comparison of certificates, read from what the inspector loads (GET
 * /certificates/:id): subject, issuer, validity, key, names, usages, fingerprints, serial, then
 * every other extension. Each line has one value per certificate and says whether they differ.
 */
import { formatDate } from '../../../lib/utils'
import { certificateKeyLabel, extensionRows, serialHex } from '../../../lib/certificateDetail'

const ABSENT = '—'
// Extensions with a line of their own above: not repeated among the others
const OWN_LINES = new Set(['subject_alt_names', 'key_usage', 'extended_key_usage'])

const day = (d) => (d ? formatDate(d, { time: false }) : '')
const lines = (values) => (values.length ? values.join('\n') : ABSENT)

function extensionsOf(cert) {
  return Object.fromEntries(extensionRows(cert.extensions, cert.san_combined).map((r) => [r.key, r]))
}

export function compareRows(certs, t) {
  const exts = certs.map(extensionsOf)
  const ext = (i, key) => exts[i][key]?.values || []
  const fixed = [
    ['subject', t('common.subject'), (c) => c.subject || ABSENT],
    ['issuer', t('common.issuer'), (c) => c.issuer || ABSENT],
    ['validity', t('common.validity'), (c) => [day(c.valid_from), day(c.valid_to)].filter(Boolean).join(' – ') || ABSENT],
    ['key', t('compare.key'), (c) => certificateKeyLabel(c, t) || ABSENT],
    ['san', 'SAN', (c, i) => lines(ext(i, 'subject_alt_names'))],
    ['usages', t('compare.usages'), (c, i) => lines([...ext(i, 'key_usage'), ...ext(i, 'extended_key_usage')])],
    ['sha1', `${t('common.fingerprints')} SHA-1`, (c) => c.thumbprint_sha1 || ABSENT],
    ['sha256', `${t('common.fingerprints')} SHA-256`, (c) => c.thumbprint_sha256 || ABSENT],
    ['serial', t('inspector.cert.serial'), (c) => serialHex(c.serial_number) || ABSENT],
  ].map(([key, label, value]) => ({ key, label, values: certs.map((c, i) => value(c, i)) }))

  // Every other extension any of them carries, in the order the first one that has it lists it
  const seen = new Map()
  exts.forEach((byKey) => Object.values(byKey).forEach((r) => { if (!OWN_LINES.has(r.key) && !seen.has(r.key)) seen.set(r.key, r) }))
  const others = [...seen.values()].map((r) => ({
    key: r.key,
    label: r.label,
    values: exts.map((byKey) => {
      const own = byKey[r.key]
      if (!own) return ABSENT
      return lines(own.values) + (own.critical ? ` (${t('inspector.cert.critical')})` : '')
    }),
  }))

  return [...fixed, ...others].map((row) => ({ ...row, differs: new Set(row.values).size > 1 }))
}
