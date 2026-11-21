/**
 * The mockup's bulkExportDialog(): what goes out (every result of the query, or the certificates
 * ticked on this page), what the file holds, Annuler and « Exporter N certificats ». The product
 * offers its formats as the export dialog's cards: the certificates in PEM, or their metadata in
 * CSV or JSON.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AtelierDialog, Icon } from '../../../components/atelier'

/** all: every result (the toolbar's export, or « Sélectionner les N résultats »); count: how many; onExport(format). */
export function BulkExportDialog({ all, count, pageCount, query, onExport, onClose }) {
  const { t } = useTranslation()
  const [format, setFormat] = useState(all ? 'csv' : 'pem')
  const [busy, setBusy] = useState(false)
  const formats = [['pem', 'PEM', 'certificates.bulkExport.pemDesc'], ['csv', 'CSV', 'certificates.bulkExport.csvDesc'], ['json', 'JSON', 'certificates.bulkExport.jsonDesc']]
  const go = async () => {
    setBusy(true)
    try { await onExport(format) } finally { setBusy(false) }
  }
  const strong = (key, values) => {
    const [a, b] = String(t(key, { ...values, n: '\u0000' })).split('\u0000')
    return b === undefined ? a : <>{a}<strong>{t('certificates.bulkExport.certificates', { count })}</strong>{b}</>
  }
  return (
    <AtelierDialog title={t('certificates.bulkExport.title')} size="narrow" onClose={onClose} testId="bulk-export-dialog">
      <p className="event-detail" id="bulk-count">
        {all ? strong(query ? 'certificates.bulkExport.allQuery' : 'certificates.bulkExport.all', { query, page: pageCount }) : strong('certificates.bulkExport.page', {})}
      </p>
      <div className="format-grid" role="radiogroup" aria-label={t('export.format')}>
        {formats.map(([v, label, desc]) => (
          <label key={v} className="format-option">
            <input type="radio" name="bulk-format" value={v} checked={format === v} onChange={() => setFormat(v)} />
            <span>{label}<small>{t(desc)}</small></span>
          </label>
        ))}
      </div>
      <p className="small muted">{t('certificates.bulkExport.note')}</p>
      <div className="modal-actions">
        <button type="button" className="btn" data-action="close-modal" onClick={onClose}>{t('common.cancel')}</button>
        <button type="button" className="btn primary" id="bulk-export-confirm" data-write="false" disabled={busy || undefined} onClick={go}>
          <Icon name="download" />{t('certificates.bulkExport.confirm', { count })}
        </button>
      </div>
    </AtelierDialog>
  )
}

export default BulkExportDialog
