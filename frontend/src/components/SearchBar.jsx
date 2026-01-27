/**
 * SearchBar Component - Search with debounce
 */
import { useState, useEffect } from 'react'
import { MagnifyingGlass, X } from '@phosphor-icons/react'
import { cn } from '../lib/utils'

export function SearchBar({ 
  placeholder = 'Search...', 
  value = '', 
  onChange, 
  onClear,
  debounce = 300,
  className 
}) {
  const [internalValue, setInternalValue] = useState(value)

  useEffect(() => {
    setInternalValue(value)
  }, [value])

  useEffect(() => {
    const timer = setTimeout(() => {
      if (internalValue !== value) {
        onChange?.(internalValue)
      }
    }, debounce)

    return () => clearTimeout(timer)
  }, [internalValue, debounce])

  const handleClear = () => {
    setInternalValue('')
    onChange?.('')
    onClear?.()
  }

  return (
    <div className={cn("relative", className)}>
      <MagnifyingGlass 
        size={14} 
        className="absolute left-2 top-1/2 -translate-y-1/2 text-text-secondary" 
      />
      <input
        type="text"
        value={internalValue}
        onChange={(e) => setInternalValue(e.target.value)}
        placeholder={placeholder}
        className="w-full pl-7 pr-7 py-1 bg-bg-tertiary border border-border rounded-sm text-sm text-text-primary placeholder-text-secondary focus:outline-none focus:ring-1 focus:ring-accent-primary focus:border-transparent transition-all"
      />
      {internalValue && (
        <button
          onClick={handleClear}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-text-secondary hover:text-text-primary transition-colors"
        >
          <X size={14} />
        </button>
      )}
    </div>
  )
}
