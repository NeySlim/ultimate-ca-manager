/**
 * Filters the toolbar has no room for, in a dialog on the mockup's gabarits: dates, user and
 * result (form-fields), the action codes as check lines (the column chooser), two shortcuts, the saved
 * filter sets, Effacer les filtres and Terminé. Every change applies at once, as the column chooser.
 */
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AtelierDialog } from '../../components/atelier/AtelierDialog'
import { Icon } from '../../components/atelier/Icon'
import { actionsOfType, actionLabel } from './activityTypes'

export function FiltersDialog({
  actions, type, chosen, usernames, username, onUsername, result, onResult, dateFrom, dateTo, onDateFrom, onDateTo, onActions, onQuick, quick,
  presets, onApplyPreset, onDeletePreset, onSavePreset, canSave, narrowed, onClear, onClose,
}) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  // A chosen type narrows the list to its actions; a chosen action stays listed
  const list = useMemo(() => {
    const base = type ? actionsOfType(actions, type) : (actions || [])
    return [...new Set([...base, ...chosen])]
  }, [actions, type, chosen])
  const picked = new Set(chosen)
  const toggle = (a) => onActions(picked.has(a) ? chosen.filter((x) => x !== a) : [...chosen, a])
  const save = () => { if (!name.trim()) return; onSavePreset(name.trim()); setName('') }

  return (
    <AtelierDialog title={t('audit.filtersTitle')} onClose={onClose} testId="audit-filters-dialog">
      <p className="small muted" style={{ marginBottom: 17 }}>{t('audit.filtersIntro')}</p>
      <div className="form-fields">
        <label className="field">{t('audit.dateFrom')}
          <input type="date" name="dateFrom" value={dateFrom} max={dateTo || undefined} onChange={(e) => onDateFrom(e.target.value)} />
        </label>
        <label className="field">{t('audit.dateTo')}
          <input type="date" name="dateTo" value={dateTo} min={dateFrom || undefined} onChange={(e) => onDateTo(e.target.value)} />
        </label>
        <label className="field">{t('audit.colUser')}
          <select name="username" value={username} onChange={(e) => onUsername(e.target.value)}>
            <option value="">{t('audit.allUsers')}</option>
            {usernames.map((u) => <option key={u} value={u}>{u}</option>)}
          </select>
        </label>
        <label className="field">{t('audit.colResult')}
          <select name="result" value={result} onChange={(e) => onResult(e.target.value)}>
            <option value="">{t('audit.allResults')}</option>
            <option value="true">{t('audit.resultsOk')}</option>
            <option value="false">{t('audit.resultsFailed')}</option>
          </select>
        </label>
        <fieldset className="field full">
          <legend>{t('audit.actionsLegend', { count: chosen.length })}</legend>
          <div className="columns-list compare-scroll" style={{ maxHeight: 220 }}>
            {list.map((a) => (
              <label key={a} className="checkbox-line">
                <input type="checkbox" checked={picked.has(a)} onChange={() => toggle(a)} />{actionLabel(a, t)}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="field full">
          <span>{t('audit.shortcuts')}</span>
          <div className="actions">
            <button type="button" className="btn" aria-pressed={quick.failedLogins} onClick={() => onQuick('failedLogins')}><Icon name="lock" />{t('common.failedLogins')}</button>
            <button type="button" className="btn" aria-pressed={quick.failures} onClick={() => onQuick('failures')}><Icon name="warning" />{t('common.allFailures')}</button>
          </div>
        </div>
        <div className="field full">
          <span>{t('audit.savedFilters')}</span>
          {presets.length ? (
            <div className="columns-list">
              {presets.map((p) => (
                <div key={p.id} className="checkbox-line">
                  <button type="button" className="btn" onClick={() => onApplyPreset(p)}><Icon name="filter" />{p.name}</button>
                  <button type="button" className="icon-btn quiet" aria-label={t('audit.deletePreset', { name: p.name })} title={t('audit.deletePreset', { name: p.name })} onClick={() => onDeletePreset(p.id)}><Icon name="close" /></button>
                </div>
              ))}
            </div>
          ) : <small>{t('audit.noSavedFilters')}</small>}
          {canSave && (
            <div className="checkbox-line">
              <input type="text" name="presetName" value={name} placeholder={t('audit.presetName')} aria-label={t('audit.presetName')}
                onChange={(e) => setName(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); save() } }} />
              <button type="button" className="btn" disabled={!name.trim()} onClick={save}>{t('audit.savePreset')}</button>
            </div>
          )}
        </div>
      </div>
      <div className="modal-actions">
        {narrowed && <button type="button" className="btn quiet" data-action="reset-filters" onClick={onClear}>{t('audit.resetFilters')}</button>}
        <button type="button" className="btn primary" data-action="close-modal" onClick={onClose}>{t('audit.done')}</button>
      </div>
    </AtelierDialog>
  )
}

export default FiltersDialog
