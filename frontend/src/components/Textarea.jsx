/**
 * Textarea Component
 */
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
  return (
    <div className={cn("space-y-1.5", className)}>
      {label && (
        <div className="flex items-center justify-between">
          <label className="block text-sm font-medium text-text-primary">
            {label}
            {props.required && <span className="status-danger-text ml-1">*</span>}
          </label>
          {showCount && maxLength && (
            <span className="text-xs text-text-secondary">
              {value.length}/{maxLength}
            </span>
          )}
        </div>
      )}
      
      <textarea
        className={cn(
          "w-full px-3 py-2 bg-tertiary-op80 border rounded-md text-sm text-text-primary placeholder-text-secondary-op60",
          "focus:outline-none focus:ring-2 focus:ring-accent-primary-op50 focus:border-accent-primary focus:bg-bg-tertiary",
          "disabled:opacity-50 disabled:cursor-not-allowed",
          "transition-all duration-200 resize-y",
          "hover:border-secondary-op50 hover:bg-bg-tertiary",
          error && "border-accent-danger focus:ring-accent-danger-op50",
          !error && "border-border"
        )}
        value={value}
        maxLength={maxLength}
        {...props}
      />

      {error && (
        <p className="text-xs status-danger-text">{error}</p>
      )}
      
      {helperText && !error && (
        <p className="text-xs text-text-secondary">{helperText}</p>
      )}
    </div>
  )
}
