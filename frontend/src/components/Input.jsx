/**
 * Input Component - Text input with label and error
 */
import { cn } from '../lib/utils'

export function Input({ 
  label, 
  error, 
  helperText,
  icon: Icon,
  className,
  ...props 
}) {
  return (
    <div className={cn("space-y-1", className)}>
      {label && (
        <label className="block text-xs font-medium text-text-primary">
          {label}
          {props.required && <span className="text-red-500 ml-1">*</span>}
        </label>
      )}
      
      <div className="relative">
        {Icon && (
          <div className="absolute left-2 top-1/2 -translate-y-1/2 text-text-secondary">
            <Icon size={14} />
          </div>
        )}
        <input
          className={cn(
            "w-full px-2 py-1 bg-bg-tertiary border rounded-sm text-sm text-text-primary placeholder-text-secondary",
            "focus:outline-none focus:ring-1 focus:ring-accent-primary focus:border-transparent",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            "transition-all",
            error && "border-red-500 focus:ring-red-500",
            !error && "border-border",
            Icon && "pl-7"
          )}
          {...props}
        />
      </div>

      {error && (
        <p className="text-xs text-red-500">{error}</p>
      )}
      
      {helperText && !error && (
        <p className="text-xs text-text-secondary">{helperText}</p>
      )}
    </div>
  )
}
