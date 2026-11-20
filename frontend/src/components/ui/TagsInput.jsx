import { useState, useRef } from 'react'
import { X } from '@phosphor-icons/react'
import { useTranslation } from 'react-i18next'

/**
 * TagsInput - Modern tag/chip input for multiple values (emails, etc.)
 * Type a value and press Enter/Tab/comma to add it as a tag.
 * Click the × on a tag to remove it.
 */
export default function TagsInput({ value = [], onChange, label, placeholder, helperText, validate, className = '' }) {
  const { t } = useTranslation()
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
    <div className={`ui-field ${className}`}>
      {label && (
        <span className="ui-label">{label}</span>
      )}
      <div
        className="ui-control flex flex-wrap items-center gap-1.5 cursor-text"
        onClick={() => inputRef.current?.focus()}
      >
        {value.map((tag, i) => (
          <span
            key={i}
            className="lv-chip"
          >
            {tag}
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); removeTag(i) }}
              aria-label={`${t('common.remove')} ${tag}`}
            >
              <X aria-hidden="true" />
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
          aria-label={typeof label === 'string' ? label : undefined}
          className="flex-1 min-w-[120px] bg-transparent border-none outline-none text-xs text-text-primary placeholder:text-text-tertiary"
        />
      </div>
      {helperText && (
        <p className="ui-help">{helperText}</p>
      )}
    </div>
  )
}
