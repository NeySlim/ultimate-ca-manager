/**
 * Dialog of the Atelier layout: a centred frame with a heading, a close button and
 * a body; focus is held inside and returns to the opening control on close (Radix).
 */
import * as Dialog from '@radix-ui/react-dialog'
import { X } from '@phosphor-icons/react'
import { useTranslation } from 'react-i18next'
import { cn } from '../../lib/utils'
import './list.css'

// Initial focus, as the mockup: an element marked data-autofocus (the safe action of a confirmation),
// else the first field of the body, else Radix's default (the close button)
const FIELDS = 'input:not([type="hidden"]):not([disabled]):not([readonly]):not([tabindex="-1"]), select:not([disabled]), textarea:not([disabled]):not([readonly])'
function focusFirstField(event) {
  const body = event.currentTarget?.querySelector('.lv-dialog-body')
  if (!body || body.contains(document.activeElement)) return
  for (const el of [...body.querySelectorAll('[data-autofocus]'), ...body.querySelectorAll(FIELDS)]) {
    if (el.closest('[hidden], .hidden, .sr-only')) continue
    el.focus()
    if (document.activeElement === el) { event.preventDefault(); return }
  }
}

/** narrow: 520 px (default); wide: 920 px, as the mockup's dialog.wide; neither: 760 px. */
export function ListDialog({ open, onOpenChange, title, subtitle, narrow = true, wide = false, closable = true, children, className, testId }) {
  const { t } = useTranslation()
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="lv-dialog-backdrop" />
        <Dialog.Content className={cn('lv-dialog', wide ? 'is-wide' : narrow && 'is-narrow', className)} data-testid={testId}
          aria-describedby={undefined} onOpenAutoFocus={focusFirstField}>
          <header className="lv-dialog-head">
            <div>
              <Dialog.Title asChild><h2>{title}</h2></Dialog.Title>
              {subtitle && <p>{subtitle}</p>}
            </div>
            {closable && (
              <Dialog.Close className="lv-btn is-icon is-quiet" aria-label={t('common.closeWindow')}>
                <X size={16} aria-hidden="true" />
              </Dialog.Close>
            )}
          </header>
          <div className="lv-dialog-body">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

export default ListDialog
