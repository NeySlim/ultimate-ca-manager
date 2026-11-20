/**
 * MultiSelectFilter - Popover with checkboxes for multi-value filter selection
 * 
 * Integrates with ResponsiveDataTable's toolbarFilters via type: 'multiSelect'
 * 
 * Usage:
 *   <MultiSelectFilter
 *     options={[{ value: 'valid', label: 'Valid' }, ...]}
 *     value={['valid', 'expired']}
 *     onChange={(values) => setFilter('status', values)}
 *     placeholder="Status"
 *   />
 */
import { useState, useRef, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { CaretDown, Check, MagnifyingGlass, X } from '@phosphor-icons/react'
import { cn } from '../../lib/utils'

export function MultiSelectFilter({
  options = [],
  value = [],
  onChange,
  placeholder = 'All',
  size = 'sm',
  searchable = false,
  className,
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const ref = useRef(null)

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        setOpen(false)
        setSearch('')
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handler = (e) => {
      if (e.key === 'Escape') {
        setOpen(false)
        setSearch('')
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open])

  const selectedSet = useMemo(() => new Set(value), [value])
  const hasSelection = value.length > 0

  const filteredOptions = useMemo(() => {
    if (!search) return options
    const q = search.toLowerCase()
    return options.filter(opt => opt.label.toLowerCase().includes(q))
  }, [options, search])

  const toggleOption = (optionValue) => {
    const newValue = selectedSet.has(optionValue)
      ? value.filter(v => v !== optionValue)
      : [...value, optionValue]
    onChange(newValue)
  }

  const selectAll = () => {
    onChange(options.map(o => o.value))
  }

  const clearAll = () => {
    onChange([])
  }

  const sizeStyles = {
    sm: {
      trigger: 'h-7 px-2 text-xs gap-1',
      content: 'text-xs',
      item: 'px-2 py-1 text-xs',
      icon: 12,
    },
    default: {
      trigger: 'h-8 px-2.5 text-sm gap-1.5',
      content: 'text-sm',
      item: 'px-2.5 py-1.5 text-xs',
      icon: 14,
    },
  }

  const s = sizeStyles[size] || sizeStyles.sm

  return (
    <div className={cn('relative', className)} ref={ref}>
      {/* Trigger */}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={cn(
          'flex items-center justify-between rounded-md border',
          'focus:outline-none focus:ring-2 focus:ring-accent-primary-op30 focus:border-accent-primary',
          'transition-all duration-200',
          s.trigger,
          'bg-bg-tertiary border-border',
          'hover:bg-tertiary-op80 hover:border-text-tertiary',
          hasSelection && 'border-accent-primary-op50 bg-accent-primary-op5',
          hasSelection ? 'text-text-primary' : 'text-text-secondary',
        )}
      >
        <span className="truncate">
          {hasSelection 
            ? `${placeholder} (${value.length})`
            : placeholder
          }
        </span>
        <CaretDown 
          size={s.icon} 
          className={cn(
            'text-text-tertiary transition-transform duration-200 shrink-0',
            open && 'rotate-180'
          )} 
        />
      </button>

      {/* Dropdown */}
      {open && (
        <div className="ui-pop absolute mt-1 max-w-[320px]">
          {/* Search within options */}
          {(searchable || options.length > 8) && (
            <div className="pb-1.5 mb-1 border-b border-border">
              <div className="relative">
                <MagnifyingGlass size={14} aria-hidden="true" className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-tertiary" />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder={t('common.search')}
                  aria-label={t('common.search')}
                  className="ui-control pl-7"
                  autoFocus
                />
              </div>
            </div>
          )}

          {/* Select All / Clear */}
          <div className="flex items-center justify-between px-2.5 pb-1 mb-1 border-b border-border">
            <button
              type="button"
              onClick={selectAll}
              className="lv-text-link"
            >
              {t('common.selectAll')}
            </button>
            {hasSelection && (
              <button
                type="button"
                onClick={clearAll}
                className="lv-text-link"
              >
                {t('common.clear')}
              </button>
            )}
          </div>

          {/* Options list */}
          <div className="max-h-72 overflow-auto">
            {filteredOptions.map(option => {
              const checked = selectedSet.has(option.value)
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => toggleOption(option.value)}
                  aria-pressed={checked}
                  className="ui-pop-item text-xs"
                >
                  <span className={cn(
                    'w-4 h-4 rounded-[3px] border flex items-center justify-center shrink-0',
                    checked
                      ? 'bg-accent-primary border-accent-primary'
                      : 'border-[color:var(--control)] bg-bg-secondary'
                  )} aria-hidden="true">
                    {checked && <Check size={11} weight="bold" className="text-on-accent" />}
                  </span>
                  <span className="truncate">{option.label}</span>
                </button>
              )
            })}
            {filteredOptions.length === 0 && (
              <div className="px-2.5 py-3 text-center text-text-tertiary text-xs">
                {t('common.noResults')}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default MultiSelectFilter
