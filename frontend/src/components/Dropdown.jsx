/**
 * Dropdown Component - Radix DropdownMenu wrapper
 */
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { forwardRef } from 'react'
import { cn } from '../lib/utils'
import { Button } from './Button'

// The trigger is the Atelier button (sizes and variants map onto Button's)
const TriggerButton = forwardRef(({ children, disabled, size = 'default', variant = 'default', ...props }, ref) => (
  <Button
    ref={ref}
    disabled={disabled}
    size={size === 'sm' ? 'sm' : 'default'}
    variant={variant === 'primary' ? 'primary' : 'secondary'}
    {...props}
  >
    {children}
  </Button>
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
          className="ui-pop"
          align="end"
          sideOffset={4}
        >
          {items.map((item, index) => {
            if (item.type === 'separator') {
              return (
                <DropdownMenu.Separator
                  key={`separator-${index}`}
                  className="ui-pop-sep"
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
                className={cn('ui-pop-item', item.danger && 'is-danger')}
              >
                {item.icon && (
                  <span className="ui-pop-icon" aria-hidden="true">
                    {item.icon}
                  </span>
                )}
                <span className="ui-pop-label">{item.label}</span>
                {item.shortcut && (
                  <span className="ui-pop-hint">{item.shortcut}</span>
                )}
              </DropdownMenu.Item>
            )
          })}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}
