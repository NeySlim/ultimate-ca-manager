/**
 * The « ⋯ » of an inspector heading: a dialog of the object's actions that are not
 * buttons of their own, one full-width button each, the destructive ones in red.
 * Items come already filtered by permission and state; choosing one closes it.
 */
import { useState } from 'react'
import { DotsThree } from '@phosphor-icons/react'
import { cn } from '../../../lib/utils'
import { ListDialog } from '../../list/ListDialog'

/** @param {{ items: Array<{ id, label, icon, onClick, danger? }>, label: string, title: string, name: string }} props */
export function MoreActionsMenu({ items, label, title, name }) {
  const [open, setOpen] = useState(false)
  if (!items.length) return null
  return (
    <>
      <button type="button" className="ins-icon-btn is-quiet" aria-label={label} title={label} aria-haspopup="dialog"
        data-testid="inspector-more-actions" onClick={() => setOpen(true)}>
        <DotsThree size={16} weight="bold" aria-hidden="true" />
      </button>
      <ListDialog open={open} onOpenChange={setOpen} title={title} testId="inspector-actions-dialog">
        <p className="ins-muted lv-dialog-lead">{name}</p>
        <div className="lv-dialog-list">
          {items.map((a) => {
            const Icon = a.icon
            return (
              <button key={a.id} type="button" className={cn('lv-btn', a.danger && 'is-danger')}
                onClick={() => { setOpen(false); a.onClick?.() }}>
                {Icon && <Icon size={17} aria-hidden="true" />}
                {a.label}
              </button>
            )
          })}
        </div>
      </ListDialog>
    </>
  )
}
