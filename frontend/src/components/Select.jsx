/**
 * Select Component - Radix Select wrapper
 */
import * as Select from '@radix-ui/react-select'
import { CaretDown, Check } from '@phosphor-icons/react'
import { cn } from '../lib/utils'

export function SelectComponent({ 
  label, 
  options = [], 
  value, 
  onChange, 
  placeholder = 'Select...',
  error,
  disabled = false,
  className 
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      {label && (
        <label className="block text-sm font-medium text-text-primary">
          {label}
        </label>
      )}

      <Select.Root value={value} onValueChange={onChange} disabled={disabled}>
        <Select.Trigger
          className={cn(
            "w-full flex items-center justify-between px-2.5 py-1.5 bg-bg-tertiary/80 border rounded-md text-sm",
            "focus:outline-none focus:ring-2 focus:ring-accent-primary/50 focus:border-accent-primary focus:bg-bg-tertiary",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            "transition-all duration-200",
            "hover:border-text-secondary/50 hover:bg-bg-tertiary",
            error ? "border-accent-danger" : "border-border",
            value ? "text-text-primary" : "text-text-secondary/60"
          )}
        >
          <Select.Value placeholder={placeholder} />
          <Select.Icon>
            <CaretDown size={14} className="text-text-secondary" />
          </Select.Icon>
        </Select.Trigger>

        <Select.Portal>
          <Select.Content
            className="bg-bg-secondary/95 backdrop-blur-md border border-border/50 rounded-lg shadow-xl shadow-black/30 overflow-hidden z-50 animate-scaleIn"
            position="popper"
            sideOffset={4}
          >
            <Select.Viewport className="p-1">
              {options.filter(opt => opt.value !== '').map(option => (
                <Select.Item
                  key={option.value}
                  value={option.value}
                  className="flex items-center gap-2 px-2.5 py-1.5 text-xs text-text-primary rounded-md cursor-pointer outline-none hover:bg-bg-tertiary/80 data-[highlighted]:bg-bg-tertiary/80 transition-colors duration-100"
                >
                  <Select.ItemText>{option.label}</Select.ItemText>
                  <Select.ItemIndicator className="ml-auto">
                    <Check size={14} className="text-accent-primary" />
                  </Select.ItemIndicator>
                </Select.Item>
              ))}
            </Select.Viewport>
          </Select.Content>
        </Select.Portal>
      </Select.Root>

      {error && (
        <p className="text-xs status-danger-text">{error}</p>
      )}
    </div>
  )
}
