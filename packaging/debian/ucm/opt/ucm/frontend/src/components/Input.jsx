/**
 * Input Component - Text input with label, error, and enhanced focus
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
    <div className={cn("space-y-1.5", className)}>
      {label && (
        <label className="block text-xs font-medium text-text-secondary">
          {label}
          {props.required && <span className="status-danger-text ml-1">*</span>}
        </label>
      )}
      
      <div className="relative">
        {icon && (
          <div className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-tertiary">
            {icon}
          </div>
        )}
        <input
          ref={ref}
          className={cn(
            "w-full px-3 py-2 bg-bg-tertiary border rounded-lg text-sm text-text-primary placeholder-text-tertiary",
            "transition-all duration-150",
            "hover:border-text-tertiary",
            "focus:outline-none focus:border-accent-primary",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            error ? "border-accent-danger" : "border-border",
            icon && "pl-9"
          )}
          style={{
            '--focus-shadow': 'color-mix(in srgb, var(--accent-primary) 15%, transparent)'
          }}
          onFocus={(e) => {
            e.target.style.boxShadow = '0 0 0 3px var(--focus-shadow), 0 1px 2px color-mix(in srgb, var(--accent-primary) 10%, transparent)';
          }}
          onBlur={(e) => {
            e.target.style.boxShadow = '';
          }}
          {...props}
        />
      </div>

      {error && (
        <p className="text-xs status-danger-text">{error}</p>
      )}
      
      {helperText && !error && (
        <p className="text-xs text-text-tertiary">{helperText}</p>
      )}
    </div>
  )
})
