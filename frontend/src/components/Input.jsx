/**
 * Input Component - Text input with label and error
 */
import { forwardRef } from 'react'
import { cn } from '../lib/utils'

export const Input = forwardRef(function Input({ 
  label, 
  error, 
  helperText,
  icon,
  className,
  ...props 
}, ref) {
  return (
    <div className={cn("space-y-1", className)}>
      {label && (
        <label className="block text-xs font-medium text-text-primary">
          {label}
          {props.required && <span className="text-red-500 ml-1">*</span>}
        </label>
      )}
      
      <div className="relative">
        {icon && (
          <div className="absolute left-2 top-1/2 -translate-y-1/2 text-text-secondary">
            {icon}
          </div>
        )}
        <input
          ref={ref}
          className={cn(
            "w-full px-2 py-1 bg-bg-tertiary border rounded-sm text-sm text-text-primary placeholder-text-secondary",
            "focus:outline-none focus:ring-1 focus:ring-accent-primary focus:border-transparent",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            "transition-all",
            error && "border-red-500 focus:ring-red-500",
            !error && "border-border",
            icon && "pl-7"
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
})
