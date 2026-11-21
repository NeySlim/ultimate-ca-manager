/**
 * The « ⋯ » of an inspector heading: the mockup's certMenu() dialog of the object's actions that
 * are not buttons of their own, one full-width button each, the destructive ones in red.
 * Items come already filtered by permission and state; choosing one closes it.
 */
import { useState } from 'react'
import { DotsThree } from '@phosphor-icons/react'
import { AtelierDialog } from '../../atelier'

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
      {open && (
        <AtelierDialog title={title} size="narrow" onClose={() => setOpen(false)} testId="inspector-actions-dialog">
          <p className="muted" style={{ marginBottom: 20 }}>{name}</p>
          <div className="columns-list">
            {items.map((a) => {
              const Glyph = a.icon
              return (
                <button key={a.id} type="button" className={a.danger ? 'btn danger' : 'btn'} data-write={a.danger ? '' : undefined}
                  onClick={() => { setOpen(false); a.onClick?.() }}>
                  {Glyph && <Glyph className="icon" aria-hidden="true" />}
                  {a.label}
                </button>
              )
            })}
          </div>
        </AtelierDialog>
      )}
    </>
  )
}
