/**
 * Select Component - Unified Radix Select wrapper
 * 
 * Variants:
 * - default: Form selects with label
 * - filter: Compact inline filters
 * - minimal: No background, just text
 * 
 * Sizes:
 * - sm: Compact (filters, pagination)
 * - default: Standard forms
 * - lg: Large forms (mobile)
 */
import * as SelectPrimitive from '@radix-ui/react-select'
import { CaretDown, Check } from '@phosphor-icons/react'
import { cn } from '../../lib/utils'

const sizes = {
  sm: {
    trigger: 'h-7 px-2 text-xs gap-1',
    content: 'text-xs',
    item: 'px-2 py-1 text-xs',
    icon: 12,
  },
  default: {
    trigger: 'h-8 px-2.5 text-sm gap-1.5',
    content: 'text-sm',
    item: 'px-2.5 py-1.5 text-xs',
    icon: 14,
  },
  lg: {
    trigger: 'h-11 px-3 text-sm gap-2',
    content: 'text-sm',
    item: 'px-3 py-2 text-sm',
    icon: 16,
  },
}

export function Select({ 
  label,
  options = [], 
  value, 
  onChange,
  onValueChange,
  placeholder = 'Select...',
  error,
  disabled = false,
  size = 'default',
  variant = 'default', // default, filter, minimal
  className,
  triggerClassName,
  // For filters - show "active" state when value is set
  showActiveState = false,
}) {
  const sizeConfig = sizes[size] || sizes.default
  const handleChange = onValueChange || onChange
  const hasValue = value && value !== ''
  
  const triggerStyles = cn(
    // Base styles
    'flex items-center justify-between rounded-md border',
    'focus:outline-none focus:ring-2 focus:ring-accent-primary-op30 focus:border-accent-primary',
    'disabled:opacity-50 disabled:cursor-not-allowed',
    'transition-all duration-200',
    sizeConfig.trigger,
    // Variant styles
    variant === 'filter' && [
      'bg-bg-tertiary border-border',
      'hover:bg-tertiary-op80 hover:border-text-tertiary',
      hasValue && showActiveState && 'border-accent-primary-op50 bg-accent-primary-op5',
    ],
    variant === 'default' && [
      'bg-tertiary-op80 border-border',
      'hover:bg-bg-tertiary hover:border-secondary-op50',
    ],
    variant === 'minimal' && [
      'bg-transparent border-transparent',
      'hover:bg-tertiary-op50',
    ],
    // Error state
    error && 'border-accent-danger',
    // Value state
    hasValue ? 'text-text-primary' : 'text-text-secondary',
    triggerClassName
  )

  return (
    <div className={cn(label && "space-y-1.5", className)}>
      {label && (
        <label className="block text-sm font-medium text-text-primary">
          {label}
        </label>
      )}

      <SelectPrimitive.Root value={value} onValueChange={handleChange} disabled={disabled}>
        <SelectPrimitive.Trigger className={triggerStyles}>
          <SelectPrimitive.Value placeholder={placeholder} />
          <SelectPrimitive.Icon>
            <CaretDown 
              size={sizeConfig.icon} 
              className={cn(
                "text-text-tertiary transition-transform duration-200",
                "group-data-[state=open]:rotate-180"
              )} 
            />
          </SelectPrimitive.Icon>
        </SelectPrimitive.Trigger>

        <SelectPrimitive.Portal>
          <SelectPrimitive.Content
            className={cn(
              // Glass effect
              "bg-secondary-op95 backdrop-blur-md",
              "border border-border-op50 rounded-lg",
              "shadow-xl shadow-black/20",
              "overflow-hidden",
              // Animation
              "animate-in fade-in-0 zoom-in-95",
              "data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95",
              "data-[side=bottom]:slide-in-from-top-2 data-[side=top]:slide-in-from-bottom-2",
              sizeConfig.content
            )}
            position="popper"
            sideOffset={4}
            align="start"
          >
            <SelectPrimitive.Viewport className="p-1 max-h-60 overflow-auto">
              {options.filter(opt => opt.value !== '').map(option => (
                <SelectPrimitive.Item
                  key={option.value}
                  value={option.value}
                  disabled={option.disabled}
                  className={cn(
                    "flex items-center gap-2 rounded-md cursor-pointer outline-none",
                    "transition-colors duration-100",
                    "text-text-primary",
                    "hover:bg-tertiary-op80 data-[highlighted]:bg-tertiary-op80",
                    "data-[disabled]:opacity-50 data-[disabled]:cursor-not-allowed",
                    sizeConfig.item
                  )}
                >
                  <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
                  <SelectPrimitive.ItemIndicator className="ml-auto">
                    <Check size={sizeConfig.icon} className="text-accent-primary" />
                  </SelectPrimitive.ItemIndicator>
                </SelectPrimitive.Item>
              ))}
            </SelectPrimitive.Viewport>
          </SelectPrimitive.Content>
        </SelectPrimitive.Portal>
      </SelectPrimitive.Root>

      {error && (
        <p className="text-xs status-danger-text">{error}</p>
      )}
    </div>
  )
}

/**
 * FilterSelect - Shorthand for filter variant
 * Includes "All" option automatically
 * Note: Uses '__all__' internally since Radix doesn't allow empty string values
 */
const ALL_VALUE = '__all__'

export function FilterSelect({
  options = [],
  value,
  onChange,
  placeholder = 'All',
  allLabel,
  size = 'default',
  className,
  ...props
}) {
  // Add "All" option at the beginning with special value
  const allOption = { value: ALL_VALUE, label: allLabel || placeholder }
  const fullOptions = [allOption, ...options]
  
  // Convert empty/null to ALL_VALUE, and vice versa for onChange
  const internalValue = value || ALL_VALUE
  const handleChange = (newValue) => {
    onChange(newValue === ALL_VALUE ? '' : newValue)
  }
  
  return (
    <Select
      options={fullOptions}
      value={internalValue}
      onChange={handleChange}
      placeholder={placeholder}
      variant="filter"
      size={size}
      showActiveState
      className={className}
      {...props}
    />
  )
}

/**
 * FormSelect - For forms/modals (no "All" option)
 */
export function FormSelect({
  label,
  options = [],
  value,
  onChange,
  size = 'default',
  error,
  disabled,
  className,
  ...props
}) {
  return (
    <Select
      label={label}
      options={options}
      value={value}
      onChange={onChange}
      variant="default"
      size={size}
      error={error}
      disabled={disabled}
      className={className}
      {...props}
    />
  )
}

export default Select
