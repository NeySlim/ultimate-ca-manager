/**
 * Select Component - Radix Select wrapper with optional searchable mode
 */
import { useState, useRef, useEffect, useCallback } from 'react'
import * as Select from '@radix-ui/react-select'
import { CaretDown, Check, MagnifyingGlass, X } from '@phosphor-icons/react'
import { cn } from '../lib/utils'

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
    <div className={cn("space-y-1.5", className)}>
      {label && (
        <label className="block text-sm font-medium text-text-primary">
          {label}
        </label>
      )}

      <Select.Root value={value} onValueChange={onChange} disabled={disabled}>
        <Select.Trigger
          className={cn(
            "w-full flex items-center justify-between px-2.5 py-1.5 bg-bg-tertiary/80 border rounded-md text-sm",
            "focus:outline-none focus:ring-2 focus:ring-accent-primary/50 focus:border-accent-primary focus:bg-bg-tertiary",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            "transition-all duration-200",
            "hover:border-text-secondary/50 hover:bg-bg-tertiary",
            error ? "border-accent-danger" : "border-border",
            value ? "text-text-primary" : "text-text-secondary/60"
          )}
        >
          <Select.Value placeholder={placeholder} />
          <Select.Icon>
            <CaretDown size={14} className="text-text-secondary" />
          </Select.Icon>
        </Select.Trigger>

        <Select.Portal>
          <Select.Content
            className="bg-bg-secondary/95 backdrop-blur-md border border-border/50 rounded-lg shadow-xl shadow-black/30 overflow-hidden z-50 animate-scaleIn"
            position="popper"
            sideOffset={4}
          >
            <Select.Viewport className="p-1">
              {options.filter(opt => opt.value !== '').map(option => (
                <Select.Item
                  key={option.value}
                  value={option.value}
                  className="flex items-center gap-2 px-2.5 py-1.5 text-xs text-text-primary rounded-md cursor-pointer outline-none hover:bg-bg-tertiary/80 data-[highlighted]:bg-bg-tertiary/80 transition-colors duration-100"
                >
                  <Select.ItemText>{option.label}</Select.ItemText>
                  <Select.ItemIndicator className="ml-auto">
                    <Check size={14} className="text-accent-primary" />
                  </Select.ItemIndicator>
                </Select.Item>
              ))}
            </Select.Viewport>
          </Select.Content>
        </Select.Portal>
      </Select.Root>

      {helperText && !error && (
        <p className="text-xs text-text-tertiary">{helperText}</p>
      )}
      {error && (
        <p className="text-xs status-danger-text">{error}</p>
      )}
    </div>
  )
}

/** Searchable combobox variant — custom dropdown with filter input */
function SearchableSelect({ label, options, value, onChange, placeholder, error, disabled, helperText, className }) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [highlightIdx, setHighlightIdx] = useState(0)
  const containerRef = useRef(null)
  const inputRef = useRef(null)
  const listRef = useRef(null)

  const selectedOption = options.find(o => o.value === value)
  const filtered = options.filter(o =>
    o.value !== '' && o.label.toLowerCase().includes(search.toLowerCase())
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
    <div className={cn("space-y-1.5", className)} ref={containerRef}>
      {label && (
        <label className="block text-sm font-medium text-text-primary">{label}</label>
      )}

      {/* Trigger / display */}
      <button
        type="button"
        disabled={disabled}
        onClick={() => { if (!disabled) { setOpen(prev => !prev); setTimeout(() => inputRef.current?.focus(), 0) } }}
        className={cn(
          "w-full flex items-center justify-between px-2.5 py-1.5 bg-bg-tertiary/80 border rounded-md text-sm text-left",
          "focus:outline-none focus:ring-2 focus:ring-accent-primary/50 focus:border-accent-primary focus:bg-bg-tertiary",
          "disabled:opacity-50 disabled:cursor-not-allowed",
          "transition-all duration-200",
          "hover:border-text-secondary/50 hover:bg-bg-tertiary",
          error ? "border-accent-danger" : "border-border",
          value ? "text-text-primary" : "text-text-secondary/60"
        )}
      >
        <span className="truncate">{selectedOption?.label || placeholder}</span>
        <CaretDown size={14} className={cn("text-text-secondary shrink-0 transition-transform", open && "rotate-180")} />
      </button>

      {/* Dropdown */}
      {open && (
        <div className="relative z-50">
          <div className="absolute top-0 left-0 w-full bg-bg-secondary/95 backdrop-blur-md border border-border/50 rounded-lg shadow-xl shadow-black/30 overflow-hidden animate-scaleIn">
            {/* Search input */}
            <div className="flex items-center gap-2 px-2.5 py-2 border-b border-border/30">
              <MagnifyingGlass size={14} className="text-text-tertiary shrink-0" />
              <input
                ref={inputRef}
                type="text"
                className="w-full bg-transparent text-sm text-text-primary placeholder:text-text-tertiary outline-none"
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
                    className={cn(
                      "w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-text-primary rounded-md cursor-pointer text-left transition-colors duration-100",
                      idx === highlightIdx && "bg-bg-tertiary/80",
                      option.value === value && "font-medium"
                    )}
                  >
                    <span className="truncate">{option.label}</span>
                    {option.value === value && (
                      <Check size={14} className="ml-auto text-accent-primary shrink-0" />
                    )}
                  </button>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {helperText && !error && (
        <p className="text-xs text-text-tertiary">{helperText}</p>
      )}
      {error && (
        <p className="text-xs status-danger-text">{error}</p>
      )}
    </div>
  )
}
