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
            "w-full flex items-center justify-between px-3 py-2 bg-bg-tertiary border rounded-lg text-sm",
            "focus:outline-none focus:ring-2 focus:ring-accent-primary focus:border-transparent",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            "transition-all",
            error ? "border-red-500" : "border-border",
            value ? "text-text-primary" : "text-text-secondary"
          )}
        >
          <Select.Value placeholder={placeholder} />
          <Select.Icon>
            <CaretDown size={16} className="text-text-secondary" />
          </Select.Icon>
        </Select.Trigger>

        <Select.Portal>
          <Select.Content
            className="bg-bg-secondary border border-border rounded-lg shadow-2xl overflow-hidden z-50"
            position="popper"
            sideOffset={4}
          >
            <Select.Viewport className="p-1">
              {options.filter(opt => opt.value !== '').map(option => (
                <Select.Item
                  key={option.value}
                  value={option.value}
                  className="flex items-center gap-2 px-3 py-2 text-sm text-text-primary rounded cursor-pointer outline-none hover:bg-bg-tertiary data-[highlighted]:bg-bg-tertiary transition-colors"
                >
                  <Select.ItemText>{option.label}</Select.ItemText>
                  <Select.ItemIndicator className="ml-auto">
                    <Check size={16} className="text-accent-primary" />
                  </Select.ItemIndicator>
                </Select.Item>
              ))}
            </Select.Viewport>
          </Select.Content>
        </Select.Portal>
      </Select.Root>

      {error && (
        <p className="text-xs text-red-500">{error}</p>
      )}
    </div>
  )
}
