/**
 * The mockup's appliedFilters(): under the toolbar, a label, one chip per active filter with its
 * own remove button, then a note on what the filters leave out. Nothing is drawn without a chip
 * or a note. With `onClearAll`, a link clears them all once more than one chip is on screen.
 */
import { useTranslation } from 'react-i18next'
import { Icon } from './Icon'

/** @param {Array<{key: string, label: string, onRemove: () => void}>} chips */
export function AppliedFilters({ chips = [], note, onClearAll }) {
  const { t } = useTranslation()
  if (!chips.length && !note) return null
  return (
    <div className="applied-filters" role="group" aria-label={t('table.activeFilters')}>
      <span className="applied-label"><Icon name="filter" />{t('table.activeFilters')}</span>
      {chips.map((c) => (
        <span key={c.key} className="chip filter-chip">{c.label}
          <button type="button" className="icon-btn" id={`clear-${c.key}`} data-clear-filter={c.key}
            aria-label={t('table.removeFilter', { label: c.label })} title={t('table.removeThisFilter')} onClick={c.onRemove}>
            <Icon name="close" />
          </button>
        </span>
      ))}
      {note && <span className="muted">{note}</span>}
      {onClearAll && chips.length > 1 && (
        <button type="button" className="text-link" data-action="clear-filters" onClick={onClearAll}>{t('table.clearFilters')}</button>
      )}
    </div>
  )
}

export default AppliedFilters
