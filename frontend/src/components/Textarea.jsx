/**
 * Textarea Component - the Atelier field: 12 px label, 80 px control, hint or error under it
 */
import { useId } from 'react'
import { WarningCircle } from '@phosphor-icons/react'
import { cn } from '../lib/utils'

export function Textarea({
  label,
  error,
  helperText,
  maxLength,
  showCount = false,
  className,
  value = '',
  ...props
}) {
  // The label names the field (assistive technologies, getByLabelText)
  const autoId = useId()
  const fieldId = props.id ?? autoId
  const describedBy = [error ? `${fieldId}-error` : null, !error && helperText ? `${fieldId}-help` : null, props['aria-describedby']]
    .filter(Boolean).join(' ') || undefined
  return (
    <div className={cn('ui-field', className)}>
      {label && (
        <label htmlFor={fieldId} className="ui-label">
          {label}
          {props.required && <span className="ui-required" aria-hidden="true">*</span>}
          {showCount && maxLength && (
            <span className="ui-label-side">{value.length}/{maxLength}</span>
          )}
        </label>
      )}

      <textarea
        className="ui-control"
        value={value}
        maxLength={maxLength}
        aria-invalid={error ? true : undefined}
        {...props}
        aria-describedby={describedBy}
        id={fieldId}
      />

      {error && (
        <p id={`${fieldId}-error`} className="ui-error"><WarningCircle aria-hidden="true" />{error}</p>
      )}

      {helperText && !error && (
        <p id={`${fieldId}-help`} className="ui-help">{helperText}</p>
      )}
    </div>
  )
}
