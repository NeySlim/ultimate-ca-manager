/**
 * The list's other filters (the product's; the mockup has none), in the frame of the Activity
 * filters (the column chooser's dialog, the issue form's fields): the template filter, then the
 * saved filters, one line per set (apply it, delete it), and a name to save the current search,
 * state and filters. Same storage and format as before (`ucm-certs-presets`).
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AtelierDialog, Icon } from '../../../components/atelier'

export function FiltersDialog({ template, onTemplate, presets, canSave, onApply, onDelete, onSave, onClose }) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const save = () => { if (!name.trim()) return; onSave(name.trim()); setName('') }
  return (
    <AtelierDialog title={t('certificates.filters.title')} size="narrow" onClose={onClose} testId="filters-dialog">
      <div className="form-fields">
        <label className="field full">{t('certificates.template')}
          <select id="template-filter" value={template} onChange={(e) => onTemplate(e.target.value)} data-autofocus>
            <option value="">{t('certificates.allTemplates')}</option>
            <option value="modified">{t('certificates.modifiedFromTemplate')}</option>
          </select>
        </label>
        <div className="field full">
          <span>{t('certificates.presets.title')}</span>
          <small>{t('certificates.presets.note')}</small>
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
          ) : <small>{t('table.noPresets')}</small>}
          {canSave && (
            <div className="checkbox-line">
              <input type="text" name="presetName" value={name} placeholder={t('table.presetName')} aria-label={t('table.presetName')}
                onChange={(e) => setName(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); save() } }} />
              <button type="button" className="btn" disabled={!name.trim() || undefined} onClick={save}>{t('table.saveFilters')}</button>
            </div>
          )}
        </div>
      </div>
      <div className="modal-actions"><button type="button" className="btn primary" data-write="false" data-action="close-modal" onClick={onClose}>{t('table.done')}</button></div>
    </AtelierDialog>
  )
}

export default FiltersDialog
