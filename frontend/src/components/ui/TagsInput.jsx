import { useState, useRef } from 'react'
import { X } from '@phosphor-icons/react'

/**
 * TagsInput - Modern tag/chip input for multiple values (emails, etc.)
 * Type a value and press Enter/Tab/comma to add it as a tag.
 * Click the × on a tag to remove it.
 */
export default function TagsInput({ value = [], onChange, label, placeholder, helperText, validate, className = '' }) {
  const [input, setInput] = useState('')
  const inputRef = useRef(null)

  const addTag = (raw) => {
    const tag = raw.trim()
    if (!tag) return
    if (value.includes(tag)) { setInput(''); return }
    if (validate && !validate(tag)) return
    onChange([...value, tag])
    setInput('')
  }

  const removeTag = (idx) => {
    onChange(value.filter((_, i) => i !== idx))
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === 'Tab' || e.key === ',') {
      e.preventDefault()
      addTag(input)
    }
    if (e.key === 'Backspace' && !input && value.length > 0) {
      removeTag(value.length - 1)
    }
  }

  const handlePaste = (e) => {
    e.preventDefault()
    const text = e.clipboardData.getData('text')
    const items = text.split(/[,;\s]+/).filter(Boolean)
    const newTags = items.filter(t => !value.includes(t) && (!validate || validate(t)))
    if (newTags.length) onChange([...value, ...newTags])
  }

  return (
    <div className={className}>
      {label && (
        <label className="block text-xs font-medium text-text-secondary mb-1">{label}</label>
      )}
      <div
        className="flex flex-wrap items-center gap-2 min-h-[38px] px-2.5 py-1.5 rounded-lg border border-border bg-bg-tertiary cursor-text transition-colors focus-within:border-accent-primary focus-within:ring-1 focus-within:ring-accent-primary"
        onClick={() => inputRef.current?.focus()}
      >
        {value.map((tag, i) => (
          <span
            key={i}
            className="inline-flex items-center gap-1.5 pl-2.5 pr-1.5 py-1 rounded-md bg-bg-secondary text-accent-primary text-sm font-medium border border-border"
          >
            {tag}
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); removeTag(i) }}
              className="p-0.5 rounded hover:bg-bg-tertiary hover:text-status-danger transition-colors"
            >
              <X size={12} weight="bold" />
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          onBlur={() => addTag(input)}
          placeholder={value.length === 0 ? placeholder : ''}
          className="flex-1 min-w-[120px] bg-transparent border-none outline-none text-sm text-text-primary placeholder:text-text-tertiary"
        />
      </div>
      {helperText && (
        <p className="text-xs text-text-tertiary mt-1">{helperText}</p>
      )}
    </div>
  )
}
