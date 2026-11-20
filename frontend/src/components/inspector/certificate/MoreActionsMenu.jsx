/**
 * The « ⋯ » menu of an inspector heading: the object's actions that are not
 * buttons of their own. Items come already filtered by permission and state.
 */
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { DotsThree } from '@phosphor-icons/react'
import { cn } from '../../../lib/utils'

/** @param {{ items: Array<{ id, label, icon, onClick, danger?, separatorBefore? }>, label: string }} props */
export function MoreActionsMenu({ items, label }) {
  if (!items.length) return null
  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger asChild>
        <button type="button" className="ins-icon-btn is-quiet" aria-label={label} title={label} data-testid="inspector-more-actions">
          <DotsThree size={18} weight="bold" aria-hidden="true" />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content className="ins-pop" align="end" sideOffset={4} collisionPadding={8} aria-label={label}>
          {items.map((a) => {
            const Icon = a.icon
            return [
              a.separatorBefore && <DropdownMenu.Separator key={`${a.id}-sep`} className="ins-menu-sep" />,
              <DropdownMenu.Item key={a.id} className={cn('ins-menu-item', a.danger && 'is-danger')} onSelect={() => a.onClick?.()}>
                {Icon && <Icon size={15} aria-hidden="true" />}
                {a.label}
              </DropdownMenu.Item>,
            ]
          })}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}
