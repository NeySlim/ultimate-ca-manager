/**
 * DatePicker Component - Simple date input (can be enhanced with a calendar library)
 */
import { Calendar } from '@phosphor-icons/react'
import { cn } from '../lib/utils'

export function DatePicker({ 
  label, 
  value, 
  onChange, 
  error,
  min,
  max,
  className,
  ...props 
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      {label && (
        <label className="block text-sm font-medium text-text-primary">
          {label}
          {props.required && <span className="text-red-500 ml-1">*</span>}
        </label>
      )}
      
      <div className="relative">
        <Calendar 
          size={16} 
          className="absolute left-3 top-1/2 -translate-y-1/2 text-text-secondary pointer-events-none" 
        />
        <input
          type="date"
          value={value}
          onChange={(e) => onChange?.(e.target.value)}
          min={min}
          max={max}
          className={cn(
            "w-full pl-9 pr-3 py-2 bg-bg-tertiary border rounded-lg text-sm text-text-primary",
            "focus:outline-none focus:ring-2 focus:ring-accent-primary focus:border-transparent",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            "transition-all",
            error ? "border-red-500 focus:ring-red-500" : "border-border",
            "[color-scheme:dark]" // Makes the date picker dark mode friendly
          )}
          {...props}
        />
      </div>

      {error && (
        <p className="text-xs text-red-500">{error}</p>
      )}
    </div>
  )
}
