/**
 * FilterChips - Displays active filters as removable pills
 * 
 * Shows each active filter as a labeled chip with an × button.
 * Includes "Clear all" when multiple filters are active.
 * 
 * Usage:
 *   <FilterChips
 *     filters={[
 *       { key: 'status', label: 'Status', value: 'valid', displayValue: 'Valid' },
 *       { key: 'ca', label: 'CA', value: ['ca1', 'ca2'], displayValue: '2 selected' },
 *     ]}
 *     onRemove={(key, value) => clearFilter(key, value)}
 *     onClearAll={() => clearAllFilters()}
 *   />
 */
import { X } from '@phosphor-icons/react'
import { useTranslation } from 'react-i18next'
import { cn } from '../../lib/utils'

export function FilterChips({ filters = [], onRemove, onClearAll, className }) {
  const { t } = useTranslation()
  
  // Only show chips for active filters
  const activeFilters = filters.filter(f => {
    if (Array.isArray(f.value)) return f.value.length > 0
    return f.value !== '' && f.value !== null && f.value !== undefined
  })

  if (activeFilters.length === 0) return null

  return (
    <div className={cn('flex flex-wrap items-center gap-1.5 px-4 py-1.5 border-b border-border-op30 bg-secondary-op10', className)}>
      {activeFilters.map(filter => {
        // For multi-select arrays, show each value as a chip
        if (Array.isArray(filter.value)) {
          return filter.value.map(val => {
            const displayVal = filter.options?.[val] || filter.optionLabels?.[val] || val
            return (
              <Chip
                key={`${filter.key}-${val}`}
                label={filter.label}
                value={displayVal}
                onRemove={() => onRemove(filter.key, val)}
              />
            )
          })
        }
        // Single value chip
        return (
          <Chip
            key={filter.key}
            label={filter.label}
            value={filter.displayValue || filter.options?.[filter.value] || filter.value}
            onRemove={() => onRemove(filter.key)}
          />
        )
      })}
      {activeFilters.length > 1 && (
        <button
          type="button"
          onClick={onClearAll}
          className="text-2xs text-text-tertiary hover:text-accent-primary transition-colors ml-1"
        >
          {t('table.clearFilters')}
        </button>
      )}
    </div>
  )
}

function Chip({ label, value, onRemove }) {
  return (
    <span className={cn(
      'inline-flex items-center gap-1 px-2 py-0.5 rounded-full',
      'text-2xs font-medium',
      'bg-accent-primary-op10 text-accent-primary border border-accent-primary-op20'
    )}>
      <span className="text-text-tertiary">{label}:</span>
      <span>{value}</span>
      <button
        type="button"
        onClick={onRemove}
        className="ml-0.5 hover:bg-accent-primary-op20 rounded-full p-0.5 transition-colors"
        aria-label={`Remove ${label}: ${value}`}
      >
        <X size={10} weight="bold" />
      </button>
    </span>
  )
}

export default FilterChips
