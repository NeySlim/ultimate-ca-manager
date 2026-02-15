import { useState, useRef } from 'react'
import { X } from '@phosphor-icons/react'

/**
 * TagsInput - Modern tag/chip input for multiple values (emails, etc.)
 * Type a value and press Enter/Tab/comma to add it as a tag.
 * Click the × on a tag to remove it.
 */
export default function TagsInput({ value = [], onChange, label, placeholder, validate, className = '' }) {
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
        <label className="block text-sm font-medium text-text-primary mb-1.5">{label}</label>
      )}
      <div
        className="flex flex-wrap items-center gap-1.5 min-h-[38px] px-2.5 py-1.5 rounded-lg border border-border bg-bg-primary cursor-text transition-colors focus-within:border-accent-primary focus-within:ring-1 focus-within:ring-accent-primary/30"
        onClick={() => inputRef.current?.focus()}
      >
        {value.map((tag, i) => (
          <span
            key={i}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-accent-primary/15 text-accent-primary text-sm font-medium"
          >
            {tag}
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); removeTag(i) }}
              className="hover:text-status-danger transition-colors"
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
    </div>
  )
}
