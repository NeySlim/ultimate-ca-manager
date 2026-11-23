/**
 * Dialogs of the journal's page actions, on the mockup's gabarits: the export (format cards of
 * exportDialog), the actions menu (the button column of certMenu) and the clean-up confirmation
 * (warning notice, one field and a danger button, as revokeDialog).
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AtelierDialog } from '../../components/atelier/AtelierDialog'
import { Icon } from '../../components/atelier/Icon'

const FORMATS = ['csv', 'json']

export function ExportDialog({ count, onExport, onClose }) {
  const { t } = useTranslation()
  const [format, setFormat] = useState('csv')
  const [busy, setBusy] = useState(false)
  const run = async () => { setBusy(true); try { await onExport(format) } finally { setBusy(false) } }
  return (
    <AtelierDialog title={t('audit.exportJournal')} onClose={onClose} testId="audit-export-dialog">
      <p className="small muted">{t('audit.exportScope', { count: Number(count || 0) })}</p>
      <div className="format-grid">
        {FORMATS.map((f) => (
          <label key={f} className="format-option">
            <input type="radio" name="format" value={f} checked={format === f} onChange={() => setFormat(f)} />
            <span>{f.toUpperCase()}<small>{t(`audit.format_${f}`)}</small></span>
          </label>
        ))}
      </div>
      <div className="modal-actions">
        <button type="button" className="btn" data-action="close-modal" onClick={onClose}>{t('common.cancel')}</button>
        <button type="button" className="btn primary" disabled={busy} onClick={run}>
          <Icon name="download" />{t('audit.download')}
        </button>
      </div>
    </AtelierDialog>
  )
}

export function ActionsDialog({ canClean, verifying, onExport, onVerify, onClean, onClose }) {
  const { t } = useTranslation()
  return (
    <AtelierDialog title={t('audit.journalActions')} size="narrow" onClose={onClose} testId="audit-actions-dialog">
      <div className="columns-list">
        <button type="button" className="btn" onClick={onExport}><Icon name="download" />{t('audit.exportJournal')}</button>
        <button type="button" className="btn" disabled={verifying} onClick={onVerify}><Icon name="shield" />{t('audit.verifyIntegrity')}</button>
        {canClean && <button type="button" className="btn danger" onClick={onClean}><Icon name="block" />{t('audit.cleanupLogsEllipsis')}</button>}
      </div>
      <p className="small muted" style={{ marginTop: 14 }}>{t('audit.integrityNote')}</p>
    </AtelierDialog>
  )
}

export function CleanupDialog({ loading, onConfirm, onClose }) {
  const { t } = useTranslation()
  const [days, setDays] = useState('90')
  // The retention sent is the one typed, never lowered: out of the server's 30 to 3650, nothing is sent
  const retention = /^\d+$/.test(days.trim()) ? parseInt(days, 10) : NaN
  const valid = retention >= 30 && retention <= 3650
  return (
    <AtelierDialog title={t('audit.cleanupLogs')} size="narrow" onClose={onClose} testId="audit-cleanup-dialog">
      <div className="notice warn"><Icon name="warning" />{t('audit.cleanupWarning')}</div>
      <label className="field">{t('audit.retentionDays')}
        <input type="number" name="retentionDays" min={30} max={3650} value={days} aria-describedby="retention-bounds"
          aria-invalid={valid ? undefined : 'true'} onChange={(e) => setDays(e.target.value)} />
      </label>
      <p id="retention-bounds" className={valid ? 'small muted' : 'field-error'} style={{ marginTop: 14 }}>{t('audit.retentionMinimum')}</p>
      <div className="modal-actions">
        <button type="button" className="btn" data-action="close-modal" onClick={onClose}>{t('common.cancel')}</button>
        <button type="button" className="btn danger" data-write="" disabled={loading || !valid} onClick={() => onConfirm(retention)}>{t('audit.deleteOldLogs')}</button>
      </div>
    </AtelierDialog>
  )
}
