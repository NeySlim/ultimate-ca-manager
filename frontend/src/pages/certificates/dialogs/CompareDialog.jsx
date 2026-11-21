/**
 * The mockup's compare(): the two ticked certificates side by side, the rows that differ marked,
 * and « Fermer la comparaison ». Every property is read from the rows of the list.
 */
import { useTranslation } from 'react-i18next'
import { AtelierDialog } from '../../../components/atelier'
import { formatDate } from '../../../lib/utils'
import { certificateKeyLabel } from '../../../lib/certificateDetail'
import { sourceLabel, sourceOf } from '../certificateSources'
import { issuerOf } from '../certificateRows'
import { stateOf } from '../certState'

const STATE_KEYS = { valid: 'common.valid', expiring: 'certificates.views.expiring', expired: 'common.expired', revoked: 'common.revoked' }
const sans = (r) => (r.san_combined ? r.san_combined.split(',').map((s) => s.trim()).filter(Boolean).join(', ') : '')

export function CompareDialog({ pair, onClose }) {
  const { t } = useTranslation()
  const none = t('inspector.cert.none')
  const rows = [
    [t('certificates.state'), (r) => t(STATE_KEYS[stateOf(r)] || 'common.unknown')],
    [t('common.description'), (r) => r.subtitle || none],
    [t('compare.authority'), (r) => issuerOf(r) || '—'],
    [t('common.keyAlgorithm'), (r) => certificateKeyLabel(r, t) || '—'],
    [t('certificates.expiry'), (r) => (r.valid_to ? formatDate(r.valid_to, { time: false }) : '—')],
    [t('certificates.source'), (r) => sourceLabel(sourceOf(r), t)],
    [t('certificates.template'), (r) => r.template_name || none],
    ['SAN', (r) => sans(r) || none],
    [t('common.privateKey'), (r) => (r.has_private_key ? t('compare.keyHeld') : t('compare.keyAbsent'))],
  ]
  return (
    <AtelierDialog title={t('compare.twoTitle')} size="wide" onClose={onClose} testId="compare-dialog">
      <p className="muted small" style={{ marginBottom: 16 }}>{t('compare.lead')}</p>
      <div className="compare-scroll">
        <table className="compare-table">
          <thead><tr><th scope="col">{t('compare.property')}</th>{pair.map((r) => <th key={r.id} scope="col">{r.cn}</th>)}</tr></thead>
          <tbody>
            {rows.map(([label, value]) => (
              <tr key={label} className={value(pair[0]) !== value(pair[1]) ? 'different' : undefined}>
                <th scope="row">{label}</th>{pair.map((r) => <td key={r.id}>{value(r)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="modal-actions"><button type="button" className="btn primary" data-write="false" data-action="close-modal" onClick={onClose}>{t('compare.close')}</button></div>
    </AtelierDialog>
  )
}

export default CompareDialog
