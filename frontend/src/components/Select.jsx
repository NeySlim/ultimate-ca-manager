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
            "w-full flex items-center justify-between px-2 py-1 bg-bg-tertiary border rounded-sm text-sm",
            "focus:outline-none focus:ring-1 focus:ring-accent-primary focus:border-transparent",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            "transition-all",
            error ? "border-red-500" : "border-border",
            value ? "text-text-primary" : "text-text-secondary"
          )}
        >
          <Select.Value placeholder={placeholder} />
          <Select.Icon>
            <CaretDown size={14} className="text-text-secondary" />
          </Select.Icon>
        </Select.Trigger>

        <Select.Portal>
          <Select.Content
            className="bg-bg-secondary border border-border rounded-lg shadow-xl overflow-hidden z-50"
            position="popper"
            sideOffset={4}
          >
            <Select.Viewport className="p-0.5">
              {options.filter(opt => opt.value !== '').map(option => (
                <Select.Item
                  key={option.value}
                  value={option.value}
                  className="flex items-center gap-2 px-2.5 py-1.5 text-xs text-text-primary rounded cursor-pointer outline-none hover:bg-bg-tertiary data-[highlighted]:bg-bg-tertiary transition-colors"
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
        <p className="text-xs text-red-500">{error}</p>
      )}
    </div>
  )
}
