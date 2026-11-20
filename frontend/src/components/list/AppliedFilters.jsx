/**
 * Active filters of a list, under its toolbar: a label, one square chip per value
 * with its own remove button, then an optional note on what the filters leave out.
 */
import { useTranslation } from 'react-i18next'
import { X } from '@phosphor-icons/react'
import { FilterIcon } from './atelierIcons'
import './list.css'

/**
 * @param {Array<{key: string, label: string, value: string|string[], optionLabels?: object}>} filters
 * @param {(key: string, value?: string) => void} onRemove
 * @param {() => void} [onClearAll]  shown when more than one chip is on screen
 * @param {string} [note]
 * @param {() => void} [onRemoveNote]  the note stands for a filter: it gets its own remove button
 */
export function AppliedFilters({ filters = [], onRemove, onClearAll, note, onRemoveNote }) {
  const { t } = useTranslation()
  const chips = []
  for (const f of filters) {
    const values = Array.isArray(f.value) ? f.value : [f.value]
    for (const v of values) {
      if (v === '' || v === null || v === undefined) continue
      const text = t('table.filterChip', { label: f.label, value: f.optionLabels?.[v] ?? v })
      chips.push({ id: `${f.key}-${v}`, key: f.key, text, remove: () => onRemove(f.key, Array.isArray(f.value) ? v : undefined) })
    }
  }
  if (!chips.length && !note) return null
  return (
    <div className="lv-applied" role="group" aria-label={t('table.activeFilters')} data-testid="applied-filters">
      <span className="lv-applied-label"><FilterIcon size={13} />{t('table.activeFilters')}</span>
      {chips.map((c) => (
        <span key={c.id} className="lv-chip" data-filter={c.key}>
          {c.text}
          <button type="button" onClick={c.remove} aria-label={t('table.removeFilter', { label: c.text })} title={t('table.removeThisFilter')}>
            <X aria-hidden="true" />
          </button>
        </span>
      ))}
      {note && (
        <span className="lv-applied-note" data-filter={onRemoveNote ? 'note' : undefined}>
          {note}
          {onRemoveNote && (
            <button type="button" className="lv-icon-btn" onClick={onRemoveNote}
              aria-label={t('table.removeFilter', { label: note })} title={t('table.removeThisFilter')}>
              <X aria-hidden="true" />
            </button>
          )}
        </span>
      )}
      {onClearAll && chips.length > 1 && (
        <button type="button" className="lv-text-link" onClick={onClearAll}>{t('table.clearFilters')}</button>
      )}
    </div>
  )
}

export default AppliedFilters
