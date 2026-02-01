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
          {props.required && <span className="status-danger-text ml-1">*</span>}
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
            "w-full px-2.5 py-1.5 bg-bg-secondary border rounded-md text-sm text-text-primary placeholder-text-secondary/60",
            "focus:outline-none focus:ring-2 focus:ring-accent-primary/50 focus:border-accent-primary focus:bg-bg-secondary",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            "transition-all duration-200",
            "hover:border-text-secondary/50",
            error && "border-accent-danger focus:ring-accent-danger/50 focus:border-accent-danger",
            !error && "border-border",
            icon && "pl-8"
          )}
          {...props}
        />
      </div>

      {error && (
        <p className="text-xs status-danger-text">{error}</p>
      )}
      
      {helperText && !error && (
        <p className="text-xs text-text-secondary">{helperText}</p>
      )}
    </div>
  )
})
