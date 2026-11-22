/**
 * A certificate as the mockup's tableView() draws it: the columns of its table (same ids, so the
 * same `col-*` classes), the phone record, the state badge and the expiry cell. The product's own
 * columns (linked pair, creation date) come last, hidden by default.
 */
import { Icon } from '../../components/atelier'
import { CertBadge, ExpiryCell } from './CertBadge'
import { GRADE_TONES, SOURCE_ICONS } from './certState'
import { extractCN, formatDate } from '../../lib/utils'
import { certificateKeyLabel } from '../../lib/certificateDetail'
import { sourceOf, sourceLabel } from './certificateSources'

export const issuerOf = (row) => extractCN(row?.issuer) || row?.issuer_name || ''
export const sourceIconOf = (row) => SOURCE_ICONS[sourceOf(row)] || 'cert'

const roleKey = (row) => ({ classical: 'certificates.hybrid.roleClassical', pq: 'certificates.hybrid.rolePq' }[row.hybrid_role] || 'certificates.hybrid.relatedCertificate')

/** Marks after the name: the key held by UCM (the mockup's), then the product's linked pair, orphan and archived. */
function marks(row, t) {
  const mark = (key, icon, label, text) => (
    <span key={key} className="key-presence" role="img" title={label} aria-label={label}><Icon name={icon} />{text}</span>
  )
  return (
    <>
      {row.has_private_key && mark('key', 'key', t('certificates.keyHeld'))}
      {row.related_certificate_id != null && mark('pair', 'link', t(roleKey(row)))}
      {row.isOrphan && mark('orphan', 'warning', t('certificates.orphanDescription'))}
      {row.archived && mark('archived', 'archive', t('certificates.archivedMark'))}
    </>
  )
}

/** The columns of the certificates table (the column contract of DataTable); `sort` names the server order a header asks for. */
export function certificateColumns(t) {
  return [
    { id: 'name', label: t('common.commonName'), sort: 'name', kind: 'entity', priority: 1, always: true, icon: () => 'cert', cell: (r) => r.cn,
      extra: (r) => marks(r, t), skeleton: { base: 55, spread: 35 } },
    { id: 'description', label: t('common.description'), sort: 'description', kind: 'text', priority: 4, grow: true, tone: 'muted', cell: (r) => r.subtitle || '',
      title: (r) => r.subtitle || '', skeleton: { base: 45, spread: 40 } },
    { id: 'status', label: t('certificates.state'), sort: 'status', kind: 'fit', priority: 1, always: true, cell: (r) => <CertBadge cert={r} t={t} />, skeleton: { width: '74px', kind: 'pill' } },
    { id: 'ca', label: t('common.issuer'), sort: 'ca', kind: 'text', priority: 2, tone: 'muted', cell: (r) => issuerOf(r) || '—', title: (r) => issuerOf(r), skeleton: { base: 50, spread: 40 } },
    { id: 'source', label: t('certificates.source'), kind: 'fit', priority: 3, cell: (r) => <span className="source-label"><Icon name={sourceIconOf(r)} />{sourceLabel(sourceOf(r), t)}</span>, skeleton: { width: '52px' } },
    { id: 'expiry', label: t('certificates.expiry'), sort: 'days', kind: 'fit', priority: 2, cell: (r) => <ExpiryCell row={r} t={t} />, skeleton: { width: '92px' } },
    { id: 'key', label: t('common.keyAlgorithm'), sort: 'key', kind: 'fit', priority: 3, tone: ['small', 'muted'], cell: (r) => certificateKeyLabel(r, t) || '—', skeleton: { width: '70px' } },
    { id: 'grade', label: t('certificates.complianceColumn'), sort: 'grade', kind: 'fit', priority: 3, defaultHidden: true, skeleton: { width: '20px' },
      cell: (r) => {
        const grade = GRADE_TONES[r.compliance_grade] ? r.compliance_grade : 'F'
        return <span className={`grade ${GRADE_TONES[grade]}`} title={`${r.compliance_score ?? 0}/100`}>{grade}</span>
      } },
    { id: 'pair', label: t('certificates.hybrid.column'), kind: 'fit', priority: 3, defaultHidden: true, tone: 'muted', skeleton: { width: '40px' },
      cell: (r) => (r.related_certificate_id == null ? '—' : <span title={t(roleKey(r))}>{t('certificates.hybrid.linked')}</span>) },
    { id: 'created', label: t('certificates.creationColumn'), sort: 'created', kind: 'fit', priority: 3, defaultHidden: true, tone: ['small', 'muted'], skeleton: { width: '70px' },
      cell: (r) => formatDate(r.created_at, { time: false }) },
  ]
}

// The header's order and the server's field
export const SORT_FIELDS = { name: 'subject', description: 'descr', status: 'status', ca: 'issuer', days: 'valid_to', key: 'key_algo', grade: 'compliance_grade', created: 'created_at' }

/** The phone record: description, issuer, source, the key note, then the state and the expiry date. */
export function certificateCard(t) {
  return (row) => ({
    description: row.subtitle || '',
    meta: [issuerOf(row), sourceLabel(sourceOf(row), t)],
    note: (row.has_private_key || row.isOrphan) && (
      <>
        {row.has_private_key && <span className="key-note"><Icon name="key" />{t('certificates.keyInUcm')}</span>}
        {row.isOrphan && <span className="key-note"><Icon name="warning" />{t('certificates.orphan')}</span>}
      </>
    ),
    status: <CertBadge cert={row} t={t} />,
    end: row.valid_to ? formatDate(row.valid_to, { time: false }) : undefined,
  })
}
