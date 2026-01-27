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
            {props.required && <span className="text-red-500 ml-1">*</span>}
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
          "w-full px-3 py-2 bg-bg-tertiary border rounded-lg text-sm text-text-primary placeholder-text-secondary",
          "focus:outline-none focus:ring-2 focus:ring-accent-primary focus:border-transparent",
          "disabled:opacity-50 disabled:cursor-not-allowed",
          "transition-all resize-y",
          error && "border-red-500 focus:ring-red-500",
          !error && "border-border"
        )}
        value={value}
        maxLength={maxLength}
        {...props}
      />

      {error && (
        <p className="text-xs text-red-500">{error}</p>
      )}
      
      {helperText && !error && (
        <p className="text-xs text-text-secondary">{helperText}</p>
      )}
    </div>
  )
}
