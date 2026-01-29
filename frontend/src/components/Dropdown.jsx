/**
 * Dropdown Component - Radix DropdownMenu wrapper
 */
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { forwardRef } from 'react'
import { cn } from '../lib/utils'

const sizes = {
  sm: 'px-2 py-0.5 text-xs',
  default: 'px-2.5 py-1 text-sm',
  lg: 'px-3 py-1.5 text-sm',
}

const TriggerButton = forwardRef(({ children, disabled, size = 'default', ...props }, ref) => (
  <button
    ref={ref}
    disabled={disabled}
    className={cn(
      "inline-flex items-center justify-center gap-1 rounded-sm font-medium",
      sizes[size],
      "bg-gradient-to-r from-bg-tertiary to-bg-secondary hover:from-bg-secondary hover:to-border",
      "text-text-primary border border-border/50",
      "transition-all duration-200",
      "hover:scale-[1.01] active:scale-[0.99]",
      "disabled:opacity-50 disabled:cursor-not-allowed",
      "focus:outline-none focus:ring-1 focus:ring-accent-primary focus:ring-offset-1 focus:ring-offset-bg-primary"
    )}
    {...props}
  >
    {children}
  </button>
))
TriggerButton.displayName = 'TriggerButton'

export function Dropdown({ trigger, items, onSelect, disabled = false, size = 'default' }) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <TriggerButton disabled={disabled} size={size}>
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
                    ? "text-red-500 hover:bg-red-500/10" 
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
                  <span className="text-[10px] text-text-secondary">{item.shortcut}</span>
                )}
              </DropdownMenu.Item>
            )
          })}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}
