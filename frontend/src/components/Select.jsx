/**
 * Select Component - Radix Select wrapper with optional searchable mode
 */
import { useState, useRef, useEffect, useCallback, useId } from 'react'
import * as Select from '@radix-ui/react-select'
import { CaretDown, Check, MagnifyingGlass, WarningCircle, X } from '@phosphor-icons/react'
import { cn } from '../lib/utils'

// Radix Select forbids value="" on an Item; the old workaround filtered
// empty-value options out and silently hid options like "No template"
// (#303). Empty values are mapped to a sentinel internally; callers keep
// the plain '' contract.
const EMPTY_VALUE = '__empty__'
const toInternal = (v) => (v === '' ? EMPTY_VALUE : v)
const fromInternal = (v) => (v === EMPTY_VALUE ? '' : v)

export function SelectComponent({ 
  label, 
  options = [], 
  value, 
  onChange, 
  placeholder = 'Select...',
  error,
  disabled = false,
  searchable = false,
  helperText,
  className 
}) {
  // Radix fires onValueChange when the selected item unmounts, e.g. a caller
  // swaps the options list out from under it (the key type driving the key
  // size list in the issue / Create CA forms). That is not a user choice, so
  // ignore any value that isn't a current option and would silently blank the
  // field. This relies on `options` being the post-swap list at the time Radix
  // fires (it is: the reset runs after that commit) (#318).
  // The label names the trigger (assistive technologies, getByLabelText)
  const fieldId = useId()
  const handleValueChange = onChange
    ? (v) => {
        const next = fromInternal(v)
        if (options.some((o) => o.value === next)) onChange(next)
      }
    : undefined

  if (searchable) {
    return (
      <SearchableSelect
        label={label}
        options={options}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        error={error}
        disabled={disabled}
        helperText={helperText}
        className={className}
      />
    )
  }

  return (
    <div className={cn('ui-field', className)}>
      {label && (
        <label htmlFor={fieldId} className="ui-label">
          {label}
        </label>
      )}

      <Select.Root value={value == null ? value : toInternal(value)} onValueChange={handleValueChange} disabled={disabled}>
        <Select.Trigger
          id={fieldId}
          className="ui-select-trigger"
          aria-invalid={error ? true : undefined}
        >
          <span><Select.Value placeholder={placeholder} /></span>
          <Select.Icon>
            <CaretDown aria-hidden="true" />
          </Select.Icon>
        </Select.Trigger>

        <Select.Portal>
          <Select.Content
            className="ui-pop"
            position="popper"
            sideOffset={4}
          >
            <Select.Viewport className="max-h-72">
              {options.map(option => (
                <Select.Item
                  key={toInternal(option.value)}
                  value={toInternal(option.value)}
                  className="ui-pop-item"
                >
                  <span className="ui-pop-label"><Select.ItemText>{option.label}</Select.ItemText></span>
                  <Select.ItemIndicator className="ui-pop-check">
                    <Check aria-hidden="true" />
                  </Select.ItemIndicator>
                </Select.Item>
              ))}
            </Select.Viewport>
          </Select.Content>
        </Select.Portal>
      </Select.Root>

      {helperText && !error && (
        <p className="ui-help">{helperText}</p>
      )}
      {error && (
        <p className="ui-error"><WarningCircle aria-hidden="true" />{error}</p>
      )}
    </div>
  )
}

/** Searchable combobox variant — custom dropdown with filter input */
function SearchableSelect({ label, options, value, onChange, placeholder, error, disabled, helperText, className }) {
  const fieldId = useId()
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [highlightIdx, setHighlightIdx] = useState(0)
  const containerRef = useRef(null)
  const inputRef = useRef(null)
  const listRef = useRef(null)

  const selectedOption = options.find(o => o.value === value)
  // Empty-value options are legitimate here (custom dropdown, no Radix
  // constraint) — only labels are matched against the search text.
  const filtered = options.filter(o =>
    String(o.label).toLowerCase().includes(search.toLowerCase())
  )

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false)
        setSearch('')
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  // Reset highlight when filter changes
  useEffect(() => { setHighlightIdx(0) }, [search])

  // Scroll highlighted item into view
  useEffect(() => {
    if (!open || !listRef.current) return
    const item = listRef.current.children[highlightIdx]
    if (item) item.scrollIntoView({ block: 'nearest' })
  }, [highlightIdx, open])

  const handleSelect = useCallback((val) => {
    onChange(val)
    setOpen(false)
    setSearch('')
  }, [onChange])

  const handleKeyDown = (e) => {
    if (!open) {
      if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        setOpen(true)
        return
      }
    }
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setHighlightIdx(i => Math.min(i + 1, filtered.length - 1))
        break
      case 'ArrowUp':
        e.preventDefault()
        setHighlightIdx(i => Math.max(i - 1, 0))
        break
      case 'Enter':
        e.preventDefault()
        if (filtered[highlightIdx]) handleSelect(filtered[highlightIdx].value)
        break
      case 'Escape':
        setOpen(false)
        setSearch('')
        break
    }
  }

  return (
    <div className={cn('ui-field', className)} ref={containerRef}>
      {label && (
        <label htmlFor={fieldId} className="ui-label">{label}</label>
      )}

      {/* Trigger / display */}
      <button
        id={fieldId}
        type="button"
        disabled={disabled}
        onClick={() => { if (!disabled) { setOpen(prev => !prev); setTimeout(() => inputRef.current?.focus(), 0) } }}
        className="ui-select-trigger"
        data-placeholder={selectedOption ? undefined : ''}
        aria-invalid={error ? true : undefined}
      >
        <span>{selectedOption?.label || placeholder}</span>
        <CaretDown aria-hidden="true" className={cn(open && "rotate-180")} />
      </button>

      {/* Dropdown */}
      {open && (
        <div className="relative z-50">
          <div className="ui-pop absolute top-1 left-0 w-full">
            {/* Search input */}
            <div className="flex items-center gap-2 px-2.5 py-2 border-b border-border-op30">
              <MagnifyingGlass size={14} className="text-text-tertiary shrink-0" />
              <input
                ref={inputRef}
                type="text"
                className="w-full bg-transparent text-xs text-text-primary placeholder:text-text-tertiary outline-none"
                placeholder={`Search...`}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onKeyDown={handleKeyDown}
                autoComplete="off"
              />
              {search && (
                <button type="button" onClick={() => setSearch('')} className="text-text-tertiary hover:text-text-primary">
                  <X size={12} />
                </button>
              )}
            </div>

            {/* Options list */}
            <div ref={listRef} className="max-h-48 overflow-y-auto p-1">
              {filtered.length === 0 ? (
                <div className="px-2.5 py-2 text-xs text-text-tertiary text-center">No results</div>
              ) : (
                filtered.map((option, idx) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => handleSelect(option.value)}
                    onMouseEnter={() => setHighlightIdx(idx)}
                    className="ui-pop-item"
                    data-highlighted={idx === highlightIdx ? '' : undefined}
                    data-state={option.value === value ? 'checked' : undefined}
                  >
                    <span className="ui-pop-label truncate">{option.label}</span>
                    {option.value === value && (
                      <span className="ui-pop-check"><Check aria-hidden="true" /></span>
                    )}
                  </button>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {helperText && !error && (
        <p className="ui-help">{helperText}</p>
      )}
      {error && (
        <p className="ui-error"><WarningCircle aria-hidden="true" />{error}</p>
      )}
    </div>
  )
}
