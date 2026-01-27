/**
 * Dropdown Component - Radix DropdownMenu wrapper
 */
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { cn } from '../lib/utils'

export function Dropdown({ trigger, items, onSelect }) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        {trigger}
      </DropdownMenu.Trigger>

      <DropdownMenu.Portal>
        <DropdownMenu.Content
          className="min-w-[200px] bg-bg-secondary border border-border rounded-xl shadow-2xl p-1 z-50"
          sideOffset={5}
        >
          {items.map((item, index) => {
            if (item.type === 'separator') {
              return (
                <DropdownMenu.Separator
                  key={`separator-${index}`}
                  className="h-px bg-border my-1"
                />
              )
            }

            return (
              <DropdownMenu.Item
                key={item.id || index}
                onClick={() => onSelect?.(item)}
                disabled={item.disabled}
                className={cn(
                  "flex items-center gap-3 px-3 py-2 text-sm rounded-lg cursor-pointer outline-none transition-colors",
                  item.danger 
                    ? "text-red-500 hover:bg-red-500/10" 
                    : "text-text-primary hover:bg-bg-tertiary",
                  item.disabled && "opacity-50 cursor-not-allowed"
                )}
              >
                {item.icon && (
                  <span className="flex-shrink-0">
                    {item.icon}
                  </span>
                )}
                <span className="flex-1">{item.label}</span>
                {item.shortcut && (
                  <span className="text-xs text-text-secondary">{item.shortcut}</span>
                )}
              </DropdownMenu.Item>
            )
          })}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}
