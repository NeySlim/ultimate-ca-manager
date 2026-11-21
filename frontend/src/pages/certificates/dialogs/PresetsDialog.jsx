/**
 * The saved filters of the list (the product's; the mockup has none): the column chooser's frame,
 * one line per saved set (apply it, delete it), then a name to save the current search and filters.
 * Same storage and format as before (`ucm-certs-presets`).
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AtelierDialog, Icon } from '../../../components/atelier'

export function PresetsDialog({ presets, canSave, onApply, onDelete, onSave, onClose }) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const save = () => { if (!name.trim()) return; onSave(name.trim()); setName('') }
  return (
    <AtelierDialog title={t('certificates.presets.title')} size="narrow" onClose={onClose} testId="presets-dialog">
      <p className="small muted" style={{ marginBottom: 17 }}>{t('certificates.presets.note')}</p>
      {presets.length ? (
        <div className="columns-list">
          {presets.map((p) => (
            <div key={p.id} className="checkbox-line">
              <button type="button" className="btn" onClick={() => onApply(p)}><Icon name="filter" />{p.name}</button>
              <span className="spacer" />
              <button type="button" className="icon-btn quiet" aria-label={t('table.deletePreset', { name: p.name })} title={t('table.deletePreset', { name: p.name })} onClick={() => onDelete(p.id)}><Icon name="close" /></button>
            </div>
          ))}
        </div>
      ) : <p className="small muted">{t('table.noPresets')}</p>}
      {canSave && (
        <div className="checkbox-line">
          <input type="text" name="presetName" value={name} placeholder={t('table.presetName')} aria-label={t('table.presetName')} data-autofocus
            onChange={(e) => setName(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); save() } }} />
          <button type="button" className="btn" disabled={!name.trim() || undefined} onClick={save}>{t('table.saveFilters')}</button>
        </div>
      )}
      <div className="modal-actions"><button type="button" className="btn primary" data-write="false" data-action="close-modal" onClick={onClose}>{t('table.done')}</button></div>
    </AtelierDialog>
  )
}

export default PresetsDialog
