/**
 * Dropdown Component - Radix DropdownMenu wrapper
 */
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { forwardRef } from 'react'
import { cn } from '../lib/utils'

const sizes = {
  sm: 'px-2.5 py-1.5 text-xs',
  default: 'px-3 py-2 text-sm',
  lg: 'px-4 py-2.5 text-sm',
}

const variants = {
  default: 'bg-bg-tertiary hover:bg-bg-hover text-text-primary border border-border',
  primary: 'btn-gradient text-white border-0',
  secondary: 'bg-bg-secondary hover:bg-bg-tertiary text-text-primary border border-border',
}

const TriggerButton = forwardRef(({ children, disabled, size = 'default', variant = 'default', ...props }, ref) => (
  <button
    ref={ref}
    disabled={disabled}
    className={cn(
      "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium",
      sizes[size],
      variants[variant],
      "transition-all duration-200",
      "hover:scale-[1.01] active:scale-[0.99]",
      "disabled:opacity-50 disabled:cursor-not-allowed",
      variant !== 'primary' && "focus:outline-none focus:ring-1 focus:ring-accent-primary focus:ring-offset-1 focus:ring-offset-bg-primary"
    )}
    {...props}
  >
    {children}
  </button>
))
TriggerButton.displayName = 'TriggerButton'

export function Dropdown({ trigger, items, onSelect, disabled = false, size = 'default', variant = 'default' }) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <TriggerButton disabled={disabled} size={size} variant={variant}>
          {trigger}
        </TriggerButton>
      </DropdownMenu.Trigger>

      <DropdownMenu.Portal>
        <DropdownMenu.Content
          className="min-w-[180px] bg-bg-secondary border border-border rounded-lg shadow-xl p-0.5 z-50"
          sideOffset={4}
        >
          {items.map((item, index) => {
            if (item.type === 'separator') {
              return (
                <DropdownMenu.Separator
                  key={`separator-${index}`}
                  className="h-px bg-border my-0.5"
                />
              )
            }

            return (
              <DropdownMenu.Item
                key={item.id || index}
                onSelect={() => {
                  item.onClick?.()
                  onSelect?.(item)
                }}
                disabled={item.disabled}
                className={cn(
                  "flex items-center gap-2 px-2.5 py-1.5 text-xs rounded cursor-pointer outline-none transition-colors",
                  item.danger 
                    ? "status-danger-text hover:status-danger-bg" 
                    : "text-text-primary hover:bg-bg-tertiary",
                  item.disabled && "opacity-50 cursor-not-allowed"
                )}
              >
                {item.icon && (
                  <span className="flex-shrink-0 opacity-70">
                    {item.icon}
                  </span>
                )}
                <span className="flex-1">{item.label}</span>
                {item.shortcut && (
                  <span className="text-2xs text-text-secondary">{item.shortcut}</span>
                )}
              </DropdownMenu.Item>
            )
          })}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}
